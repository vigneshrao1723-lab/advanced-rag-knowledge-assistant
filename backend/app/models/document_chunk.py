"""The `document_chunks` entity (docs/DATA_MODEL.md) — chunked units of a
document, used for retrieval once the retrieval pipeline (Issue #4) exists.

Slice 3.1 (GitHub Issue #3) creates only the chunk metadata/content
structure docs/DATA_MODEL.md and docs/RAG_DESIGN.md already specify
(`document_id`, `page`, `section`, `chunk_index`, `content`) — deliberately
**without** an embedding column. Choosing a pgvector `VECTOR(n)` column now
would lock the schema to an embedding model/dimension before the provider
abstraction (`EmbeddingProvider`) is designed in a later slice; adding that
column then is a small, additive migration, not a breaking one, since
`document_chunks` rows will already exist for it to populate.

`workspace_id` is intentionally denormalized here even though it's
reachable via `document_id` — every future workspace-scoped
retrieval/security query (docs/SECURITY.md's multi-tenancy requirements)
needs to filter chunks by workspace without an extra join, closing an
entire class of cross-workspace-access risk at the query level. Do not
remove it on the grounds that `document_id` already implies it.

`ON DELETE CASCADE` from `documents` matches the project's existing
"child records die with their owning row" convention already used for
`sessions`/`workspace_members` (Issue #2) — deleting a document removes its
chunks, unlike `audit_logs`, which deliberately outlives what it describes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
