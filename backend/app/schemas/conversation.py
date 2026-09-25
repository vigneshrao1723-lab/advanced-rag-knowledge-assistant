from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.message import MessageRole


class ConversationRead(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class CitationRead(BaseModel):
    document_id: uuid.UUID
    page: int | None
    section: str | None
    rank: int


class MessageRead(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime
    citations: list[CitationRead]


class MessageCreate(BaseModel):
    # Bounded to a sane maximum: this becomes the retrieval/generation
    # query text, not stored document content, so there is no ingestion-
    # style large-input case to support here.
    content: str = Field(min_length=1, max_length=4000)
