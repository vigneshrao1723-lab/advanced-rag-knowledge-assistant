from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.document import DocumentRead

_NAME_MIN_LENGTH = 1
_NAME_MAX_LENGTH = 200
_DESCRIPTION_MAX_LENGTH = 2000


class CollectionCreate(BaseModel):
    name: str = Field(min_length=_NAME_MIN_LENGTH, max_length=_NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)


class CollectionUpdate(BaseModel):
    # Full-replace PATCH semantics, matching `WorkspaceUpdate`'s own
    # convention: `name` is always required (a collection must have a
    # name), `description` is always required-but-nullable (an explicit
    # `null` clears it) -- this avoids the ambiguity a partial-update
    # schema would have between "field omitted" and "field cleared".
    name: str = Field(min_length=_NAME_MIN_LENGTH, max_length=_NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX_LENGTH)


class CollectionRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    document_count: int


class CollectionDocumentAdd(BaseModel):
    document_id: uuid.UUID


class CollectionWithDocumentsRead(CollectionRead):
    documents: list[DocumentRead]
