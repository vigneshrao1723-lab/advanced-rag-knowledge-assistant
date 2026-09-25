"""The `conversations` entity (docs/DATA_MODEL.md) — a chat session within
a workspace (GitHub Issue #4, Slice 4.1).

Only the minimal shape Issue #4 needs to persist a generation result
somewhere is added here — rename/delete/search/regenerate/feedback (the
richer conversation-management surface, docs/REQUIREMENTS.md "Chat") are
Issue #5's job, built on top of this schema without needing to change it.

`created_by` uses `ON DELETE SET NULL`, matching `Document.uploaded_by`'s
precedent (Issue #3) for the same reason: a conversation (and the
messages/citations under it) should outlive the account that started it,
not disappear or cascade-delete when a user is removed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Nullable: a conversation may not have a title yet (e.g. auto-titling
    # from the first message is a later, UX-layer decision -- Issue #5).
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
