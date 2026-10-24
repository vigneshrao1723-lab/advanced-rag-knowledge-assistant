from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus

_FILENAME_MIN_LENGTH = 1
_FILENAME_MAX_LENGTH = 255


class DocumentRename(BaseModel):
    filename: str = Field(min_length=_FILENAME_MIN_LENGTH, max_length=_FILENAME_MAX_LENGTH)


class DocumentRead(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    status: DocumentStatus
    page_count: int | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class DocumentChunkRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    page: int | None
    section: str | None
    content: str
