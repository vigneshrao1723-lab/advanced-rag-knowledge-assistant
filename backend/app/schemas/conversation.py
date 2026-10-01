from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.message import MessageFeedback, MessageRole


class ConversationRead(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationRename(BaseModel):
    # Nullable -- an explicit `{"title": null}` clears a conversation
    # back to untitled, a valid state (ConversationRead.title is itself
    # nullable). Bounded the same way MessageCreate.content is -- a
    # title is short, user-authored text, not stored document content.
    title: str | None = Field(default=None, max_length=200)


class CitationRead(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    page: int | None
    section: str | None
    rank: int


class MessageRead(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime
    citations: list[CitationRead]
    feedback: MessageFeedback | None


class MessageCreate(BaseModel):
    # Bounded to a sane maximum: this becomes the retrieval/generation
    # query text, not stored document content, so there is no ingestion-
    # style large-input case to support here.
    content: str = Field(min_length=1, max_length=4000)


class MessageFeedbackUpdate(BaseModel):
    # Nullable -- an explicit `{"feedback": null}` clears previously
    # given feedback, a valid, idempotent transition.
    feedback: MessageFeedback | None


class VoiceMessageRead(BaseModel):
    """Response for a posted voice message (GitHub Issue #6) — the
    transcript produced by speech-to-text, plus the same `MessageRead`
    shape the text-message endpoint returns (grounded answer +
    citations), since voice reuses that exact flow rather than a
    separate one."""

    transcript: str
    message: MessageRead
