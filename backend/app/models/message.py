"""The `messages` entity (docs/DATA_MODEL.md) — individual messages within
a conversation (GitHub Issue #4, Slice 4.1).

`role` uses a native Postgres enum, matching `WorkspaceMember.role`'s
convention (`workspace_role`): a fixed, closed set (`USER`/`ASSISTANT`)
defined once by the project specification (docs/REQUIREMENTS.md "Chat" —
"Individual messages within a conversation (user + assistant)"), not an
open-ended taxonomy like `AuditLog.event_type`.

`workspace_id` is intentionally denormalized here even though it's
reachable via `conversation_id`, matching `DocumentChunk.workspace_id`'s
own precedent exactly: every workspace-scoped retrieval/security query
needs to filter messages by workspace without an extra join, closing an
entire class of cross-workspace-access risk at the query level.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageRole(enum.StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", native_enum=True), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
