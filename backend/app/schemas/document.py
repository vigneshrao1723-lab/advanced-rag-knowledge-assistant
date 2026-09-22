from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.document import DocumentStatus


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
