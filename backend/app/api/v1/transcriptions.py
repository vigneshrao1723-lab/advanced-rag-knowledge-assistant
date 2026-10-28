"""Speech-to-text as its own step (ADR 0010): upload a recording, get the
transcript back for review. Asking the assistant is a separate, explicit
action (the ordinary message endpoint)."""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.dependencies import WorkspaceContext, require_workspace_role
from app.core.rate_limit import enforce_voice_message_rate_limit
from app.core.redis_client import get_redis_client
from app.models.workspace_member import WorkspaceRole
from app.schemas.transcription import TranscriptionRead
from app.services import transcription_service
from app.voice.stt_provider import SpeechToTextProvider, get_speech_to_text_provider

router = APIRouter(prefix="/workspaces", tags=["voice"])


@router.post(
    "/{workspace_id}/transcriptions",
    response_model=TranscriptionRead,
    status_code=status.HTTP_200_OK,
)
async def create_transcription(
    request: Request,
    audio: UploadFile = File(...),
    language: str | None = Form(default=None, max_length=12),
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
    stt_provider: SpeechToTextProvider = Depends(get_speech_to_text_provider),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> TranscriptionRead:
    enforce_voice_message_rate_limit(request, user_id=ctx.user.id, redis_client=redis_client)
    return await transcription_service.transcribe_upload(
        audio,
        db=db,
        workspace_id=ctx.workspace.id,
        stt_provider=stt_provider,
        max_audio_size_bytes=get_settings().max_voice_audio_size_bytes,
        language=language,
    )
