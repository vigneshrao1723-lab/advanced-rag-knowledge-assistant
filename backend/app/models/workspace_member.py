"""The `workspace_members` entity (docs/DATA_MODEL.md) — membership + role
linking users to workspaces."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkspaceRole(enum.StrEnum):
    """String values match docs/REQUIREMENTS.md / docs/DATA_MODEL.md's
    convention (uppercase) so API responses read the same as the docs."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


# Ordering used for authorization comparisons (app/core/dependencies.py):
# higher index = more privileged.
_ROLE_RANK = {
    WorkspaceRole.VIEWER: 0,
    WorkspaceRole.MEMBER: 1,
    WorkspaceRole.ADMIN: 2,
    WorkspaceRole.OWNER: 3,
}


def role_at_least(role: WorkspaceRole, minimum: WorkspaceRole) -> bool:
    return _ROLE_RANK[role] >= _ROLE_RANK[minimum]


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(WorkspaceRole, name="workspace_role", native_enum=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
