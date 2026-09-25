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
import uuid

from fastapi import HTTPException, status
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
from app.schemas.conversation import CitationRead, ConversationRead, MessageRead


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


__all__ = ["create_conversation", "list_conversations", "list_messages", "post_message"]
