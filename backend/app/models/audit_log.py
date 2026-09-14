"""Security-relevant audit log (docs/SECURITY.md "Audit logging").

`event_type` is a plain indexed string, not a Postgres native enum:
the taxonomy of auditable events will keep growing across future issues
(document access, ingestion, retrieval, etc.), and a native enum would
require a migration for every new event type. `app/core/audit.py` defines
the closed, typed set of event names the application actually emits.

`user_id`/`workspace_id` use `ON DELETE SET NULL`, not CASCADE — an audit
trail is a security record and should outlive the account or workspace it
describes, not disappear when either is deleted.

Never write passwords, raw tokens, session secrets, or cookies into
`metadata_`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Event-specific, non-secret detail only (e.g. target user/role for a
    # membership change) — see the module docstring.
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
