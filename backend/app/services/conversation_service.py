"""Conversation orchestration (Issue #4, Slice 4.3): creating a
conversation, and posting a message that runs the full retrieval ->
generation -> citation pipeline and persists the result.

This is the first slice to compose Issue #3's ingestion output
(`document_chunks`, `READY` documents) with Issue #4's retrieval
(Slice 4.2) and generation (this slice) modules into one demonstrable
"question -> grounded answer with citations" flow.
"""

from __future__ import annotations

import asyncio
import io
import uuid
import wave

from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.generation.citation_engine import create_citations
from app.generation.context_builder import BuiltContext
from app.generation.llm_provider import LLMProvider
from app.generation.service import generate_answer
from app.ingestion.embedding import EmbeddingProvider
from app.models.citation import Citation
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.repositories import citation_repository, conversation_repository, message_repository
from app.retrieval.reranker import Reranker
from app.retrieval.service import hybrid_search
from app.retrieval.types import RetrievalCandidate
from app.schemas.conversation import (
    CitationRead,
    ConversationRead,
    MessageCreate,
    MessageRead,
    VoiceMessageRead,
)
from app.voice.stt_provider import (
    SpeechToTextError,
    SpeechToTextProvider,
    UnsupportedAudioFormatError,
)
from app.voice.tts_provider import TextToSpeechError, TextToSpeechProvider

# Bounded independently of `max_voice_audio_size_bytes` (a byte-size
# cap) -- this bounds wall-clock audio length directly, since a highly
# compressed or low-bitrate file could otherwise pass the size check
# while still describing an unreasonably long recording. 120s is
# generous for a spoken chat question (`MessageCreate.content`'s own
# 4000-character cap is the tighter bound in practice once transcribed).
_MAX_VOICE_AUDIO_DURATION_SECONDS = 120.0
_VOICE_UPLOAD_CHUNK_SIZE = 1024 * 1024


def _conversation_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "conversation_not_found", "message": "Conversation not found."},
    )


def _to_conversation_read(conversation: Conversation) -> ConversationRead:
    return ConversationRead(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _to_message_read(message: Message, citations: list[CitationRead]) -> MessageRead:
    return MessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        citations=citations,
    )


def _to_citation_read(citation: Citation) -> CitationRead:
    return CitationRead(
        document_id=citation.document_id,
        page=citation.page,
        section=citation.section,
        rank=citation.rank,
    )


def create_conversation(
    db: Session, *, workspace_id: uuid.UUID, created_by: uuid.UUID
) -> ConversationRead:
    conversation = conversation_repository.create(
        db, workspace_id=workspace_id, created_by=created_by
    )
    db.commit()
    return _to_conversation_read(conversation)


def list_conversations(db: Session, *, workspace_id: uuid.UUID) -> list[ConversationRead]:
    conversations = conversation_repository.list_for_workspace(db, workspace_id=workspace_id)
    return [_to_conversation_read(conversation) for conversation in conversations]


def list_messages(
    db: Session, *, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[MessageRead]:
    conversation = conversation_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, conversation_id=conversation_id
    )
    if conversation is None:
        raise _conversation_not_found_error()

    messages = message_repository.list_for_conversation(db, conversation_id=conversation.id)
    citations_by_message = citation_repository.list_for_messages(
        db, message_ids=[message.id for message in messages]
    )
    return [
        _to_message_read(
            message,
            [_to_citation_read(citation) for citation in citations_by_message.get(message.id, [])],
        )
        for message in messages
    ]


def _run_retrieval_and_generation(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query: str,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    llm_provider: LLMProvider,
    conversation_id: uuid.UUID,
    user_message_id: uuid.UUID,
) -> tuple[str, BuiltContext]:
    """Synchronous: runs the retrieval SQL queries and the (CPU-bound)
    generation call in one plain function, deliberately, so it can be
    run via `asyncio.to_thread()` in `post_message()` below -- matching
    the established pattern for every other CPU/IO-bound pipeline stage
    in this codebase (extraction, cleaning, chunking, embedding, Issue
    #3). `db` is used only inside this function's single call, from one
    thread, sequentially -- never touched by the calling coroutine again
    until `asyncio.to_thread()` returns control to it, so there is no
    concurrent cross-thread access to the same `Session` at any point
    (the specific hazard the Issue #3 Slice 3.4 review flagged was
    genuinely *concurrent* access from two threads at once, not this
    sequential hand-off-and-return pattern).
    """
    candidates: list[RetrievalCandidate] = hybrid_search(
        db,
        workspace_id=workspace_id,
        query_text=query,
        embedding_provider=embedding_provider,
        reranker=reranker,
        conversation_id=conversation_id,
        message_id=user_message_id,
    )
    return generate_answer(query=query, candidates=candidates, llm_provider=llm_provider)


async def post_message(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    content: str,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    llm_provider: LLMProvider,
) -> MessageRead:
    """Persists the user's message, runs retrieval + generation off the
    event loop, then persists the assistant's answer and its citations
    together in one final transaction -- a crash between generating the
    answer and committing it loses only that in-flight answer (the user
    message the question is already recorded), never leaves a citation
    without its message or vice versa.
    """
    conversation = conversation_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, conversation_id=conversation_id
    )
    if conversation is None:
        raise _conversation_not_found_error()

    user_message = message_repository.create(
        db,
        conversation_id=conversation.id,
        workspace_id=workspace_id,
        role=MessageRole.USER,
        content=content,
    )
    db.commit()

    answer, context = await asyncio.to_thread(
        _run_retrieval_and_generation,
        db,
        workspace_id=workspace_id,
        query=content,
        embedding_provider=embedding_provider,
        reranker=reranker,
        llm_provider=llm_provider,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
    )

    assistant_message = message_repository.create(
        db,
        conversation_id=conversation.id,
        workspace_id=workspace_id,
        role=MessageRole.ASSISTANT,
        content=answer,
    )
    citations = create_citations(
        db, message_id=assistant_message.id, workspace_id=workspace_id, context=context
    )
    db.commit()

    citation_reads = [_to_citation_read(citation) for citation in citations]
    return _to_message_read(assistant_message, citation_reads)


def _voice_audio_too_large_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={
            "code": "voice_audio_too_large",
            "message": "The uploaded audio exceeds the maximum allowed size or duration.",
        },
    )


def _unsupported_audio_format_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "unsupported_audio_format",
            "message": "This audio format is not supported. Upload WAV audio.",
        },
    )


def _transcription_failed_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "transcription_failed",
            "message": "The uploaded audio could not be transcribed.",
        },
    )


def _empty_transcript_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "empty_transcript",
            "message": "No speech was detected in the uploaded audio.",
        },
    )


def _message_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "message_not_found", "message": "Message not found."},
    )


def _audio_synthesis_failed_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": "audio_synthesis_failed",
            "message": "The answer's audio could not be synthesized.",
        },
    )


async def _read_and_validate_voice_upload(upload: UploadFile, *, max_size_bytes: int) -> bytes:
    """Streams the upload in bounded chunks -- never buffers an
    arbitrarily large payload first and checks its length afterward.
    Mirrors `document_service._read_and_validate_size()`'s identical
    pattern."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_VOICE_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise _voice_audio_too_large_error()
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_wav_duration(audio_bytes: bytes, *, max_duration_seconds: float) -> None:
    """A lightweight header-only check (no full decode). A file that
    fails to parse as WAV here is deliberately let through unrejected --
    `SpeechToTextProvider.transcribe()` is the single source of truth
    for "is this genuinely valid, readable audio," so a malformed file
    fails there with the correct `transcription_failed` outcome instead
    of a misleading `voice_audio_too_large` one."""
    try:
        with wave.open(io.BytesIO(audio_bytes)) as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return
            duration = wav_file.getnframes() / frame_rate
    except (wave.Error, EOFError):
        return
    if duration > max_duration_seconds:
        raise _voice_audio_too_large_error()


async def transcribe_and_post_voice_message(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    upload: UploadFile,
    stt_provider: SpeechToTextProvider,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    llm_provider: LLMProvider,
    max_audio_size_bytes: int,
) -> VoiceMessageRead:
    """Transcribes the uploaded audio, then hands the transcript to the
    *exact same* `post_message()` the text-chat flow uses (Issue #6's
    explicit requirement: voice must never fork the retrieval/generation
    pipeline). The only voice-specific work here is audio validation and
    transcription; everything after that point is indistinguishable from
    a typed question.

    Checks the conversation exists *before* doing any audio validation
    or transcription work -- matching `post_message()`'s own ordering
    (existence/authorization before expensive work), so a bad
    `conversation_id` gets its correct `404` rather than a misleading
    transcription-related error from work that should never have started.
    `post_message()` re-checks this itself too (it's a public entry point
    in its own right) -- a small, harmless, zero-trust-between-layers
    redundancy, not a bug.
    """
    if (
        conversation_repository.get_by_id_for_workspace(
            db, workspace_id=workspace_id, conversation_id=conversation_id
        )
        is None
    ):
        raise _conversation_not_found_error()

    audio_bytes = await _read_and_validate_voice_upload(
        upload, max_size_bytes=max_audio_size_bytes
    )
    _validate_wav_duration(audio_bytes, max_duration_seconds=_MAX_VOICE_AUDIO_DURATION_SECONDS)

    mime_type = upload.content_type or "audio/wav"
    try:
        transcript = await asyncio.to_thread(
            stt_provider.transcribe, audio_bytes, mime_type=mime_type
        )
    except UnsupportedAudioFormatError as exc:
        raise _unsupported_audio_format_error() from exc
    except SpeechToTextError as exc:
        raise _transcription_failed_error() from exc

    try:
        validated = MessageCreate(content=transcript)
    except ValidationError as exc:
        # Empty (no speech detected) and over-length transcripts both
        # land here -- `MessageCreate`'s own bounds are the single
        # source of truth for "a valid message," matching the text-chat
        # endpoint exactly, so voice can never bypass a validation rule
        # typed messages are held to.
        if not transcript.strip():
            raise _empty_transcript_error() from exc
        raise _transcription_failed_error() from exc

    message = await post_message(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        content=validated.content,
        embedding_provider=embedding_provider,
        reranker=reranker,
        llm_provider=llm_provider,
    )
    return VoiceMessageRead(transcript=validated.content, message=message)


async def synthesize_message_audio(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    tts_provider: TextToSpeechProvider,
) -> bytes:
    """Synthesizes audio on demand from a persisted assistant message's
    text -- no audio is ever stored; this is a pure, cheap-to-regenerate
    transform of already-persisted text, matching `document_chunks`'
    own "don't persist what's cheaply re-derivable" precedent (Issue #3
    Slice 3.6). Only `ASSISTANT` messages have anything meant to be
    played back; a `USER` message or one from another conversation/
    workspace is `404`, matching every other workspace-scoped lookup's
    non-leaking shape."""
    conversation = conversation_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, conversation_id=conversation_id
    )
    if conversation is None:
        raise _conversation_not_found_error()

    message = message_repository.get_by_id_for_conversation(
        db, conversation_id=conversation.id, message_id=message_id
    )
    if message is None or message.role != MessageRole.ASSISTANT:
        raise _message_not_found_error()

    try:
        return await asyncio.to_thread(tts_provider.synthesize, message.content)
    except TextToSpeechError as exc:
        raise _audio_synthesis_failed_error() from exc


__all__ = [
    "create_conversation",
    "list_conversations",
    "list_messages",
    "post_message",
    "synthesize_message_audio",
    "transcribe_and_post_voice_message",
]
