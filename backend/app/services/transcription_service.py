"""Transcription-only service: recorded audio -> text, nothing more. The
transcript is returned to the user to review/edit and is only sent to the
assistant if they submit it (the normal `post_message()` path), so a
mis-heard word never silently becomes a question. Audio and transcript text
are never logged."""

from __future__ import annotations

import asyncio
import re
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.schemas.transcription import TranscriptionRead
from app.voice.audio_upload import (
    MAX_VOICE_AUDIO_DURATION_SECONDS,
    read_and_validate_voice_upload,
    validate_wav_duration,
)
from app.voice.stt_provider import (
    SpeechToTextError,
    SpeechToTextProvider,
    SpeechToTextUnavailableError,
    UnsupportedAudioFormatError,
)
from app.voice.vocabulary import build_vocabulary_hint

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
_MAX_TRANSCRIPT_CHARS = 4000


def normalize_language(language: str | None) -> str | None:
    """"" / "auto" -> None (auto-detect); otherwise a bare language code."""
    if language is None:
        return None
    value = language.strip().lower()
    if value in ("", "auto"):
        return None
    if not _LANGUAGE_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_language", "message": "The language code is not valid."},
        )
    return value


async def transcribe_upload(
    upload: UploadFile,
    *,
    db: Session | None = None,
    workspace_id: uuid.UUID | None = None,
    stt_provider: SpeechToTextProvider,
    max_audio_size_bytes: int,
    language: str | None,
) -> TranscriptionRead:
    chosen_language = normalize_language(language)
    audio_bytes = await read_and_validate_voice_upload(upload, max_size_bytes=max_audio_size_bytes)
    validate_wav_duration(audio_bytes, max_duration_seconds=MAX_VOICE_AUDIO_DURATION_SECONDS)
    mime_type = upload.content_type or "audio/wav"
    # Titles and filenames from this workspace help with terms like
    # "bubble sort" or "MPI_Reduce" that a speech model otherwise mishears.
    hint = build_vocabulary_hint(db, workspace_id=workspace_id) if db and workspace_id else None
    try:
        transcript = await asyncio.to_thread(
            stt_provider.transcribe_detailed,
            audio_bytes,
            mime_type=mime_type,
            language=chosen_language,
            vocabulary_hint=hint,
        )
    except UnsupportedAudioFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unsupported_audio_format",
                "message": "This audio format is not supported. Upload WAV audio.",
            },
        ) from exc
    except SpeechToTextUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "stt_unavailable", "message": exc.message},
        ) from exc
    except SpeechToTextError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "transcription_failed",
                "message": "The recording could not be transcribed.",
            },
        ) from exc

    return TranscriptionRead(
        transcript=transcript.text[:_MAX_TRANSCRIPT_CHARS],
        language=transcript.language,
        duration_seconds=transcript.duration_seconds,
        provider=stt_provider.provider_name,
        model=stt_provider.model_name,
    )


__all__ = ["normalize_language", "transcribe_upload"]
