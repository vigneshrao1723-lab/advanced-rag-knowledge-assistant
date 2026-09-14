from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace_member import WorkspaceMember, WorkspaceRole


def get_membership(
    db: Session, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember | None:
    return db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).scalar_one_or_none()


def add_member(
    db: Session, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole
) -> WorkspaceMember:
    member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
    db.add(member)
    db.flush()
    db.refresh(member)
    return member


def remove_member(db: Session, member: WorkspaceMember) -> None:
    db.delete(member)
    db.flush()


def update_role(db: Session, member: WorkspaceMember, *, role: WorkspaceRole) -> WorkspaceMember:
    member.role = role
    db.flush()
    db.refresh(member)
    return member


def list_for_workspace(db: Session, workspace_id: uuid.UUID) -> list[tuple[WorkspaceMember, User]]:
    rows = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at.asc())
    ).all()
    return [(member, user) for member, user in rows]


def list_workspace_ids_for_user(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id)
        )
        .scalars()
        .all()
    )


def count_owners(db: Session, workspace_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WorkspaceRole.OWNER,
        )
    ).scalar_one()
