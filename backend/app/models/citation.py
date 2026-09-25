"""The `citations` entity (docs/DATA_MODEL.md) — links between a
generated answer/message and the evidence (chunk) it cites (GitHub
Issue #4, Slice 4.1).

`ON DELETE CASCADE` from both `messages` and `document_chunks`: a
citation has no independent meaning once either its message or the
chunk it points to is gone, matching the project's existing "child
records die with their owning row" convention (`document_chunks` from
`documents`, Issue #3). `document_id`/`page`/`section` are captured
redundantly at citation-creation time (copied from the cited chunk) so
`docs/REQUIREMENTS.md`'s "each citation references document, page, and
section" requirement is answerable directly from this row, without a
join through `document_chunks` on every citation read. `workspace_id`
is denormalized too, matching `DocumentChunk.workspace_id`'s own
precedent, for the same workspace-scoped-query-safety reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 0-based position of this citation within its message's citation
    # list, e.g. as referenced by an inline [1]/[2] marker in `content` --
    # deterministic ordering for display, not a relevance score (the
    # underlying chunk's retrieval/rerank score lives on `retrieval_events`).
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
