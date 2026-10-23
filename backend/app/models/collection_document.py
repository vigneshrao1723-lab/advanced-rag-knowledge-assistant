"""The `collection_documents` entity (docs/DATA_MODEL.md) — the many-to-
many link between a collection and the documents it groups.

`workspace_id` is intentionally denormalized here even though it's
reachable via either `collection_id` or `document_id`, matching
`DocumentChunk.workspace_id`/`Message.workspace_id`'s own precedent
exactly: every workspace-scoped query can filter without an extra join.
A surrogate UUID primary key (not a composite key on
`(collection_id, document_id)`) matches this codebase's existing
convention for every other table, including other many-to-many-shaped
ones like `workspace_members`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CollectionDocument(Base):
    __tablename__ = "collection_documents"
    __table_args__ = (
        UniqueConstraint("collection_id", "document_id", name="uq_collection_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
