"""Workspace CRUD, membership, and role management.

Role matrix (docs/REQUIREMENTS.md names the four roles but does not fully
specify the edges between them; this is the conservative, documented
resolution — see docs/API_CONTRACT.md "Workspace authorization matrix"):

- OWNER: full control (rename, delete, add/remove any member, change any
  role) — except a workspace may never be left with zero OWNERs.
- ADMIN: rename the workspace; add/remove MEMBER/VIEWER members; change
  roles only between MEMBER and VIEWER. Cannot touch OWNER/ADMIN
  membership, promote anyone to OWNER/ADMIN, or delete the workspace.
- MEMBER / VIEWER: read-only on the workspace and its membership. (No
  workspace-owned resources exist yet to further differentiate them —
  that distinction becomes meaningful starting with Issue #3.)

Every function here assumes the caller has already been authenticated and
that basic membership/role gating for the endpoint has been enforced by
`app.core.dependencies.require_workspace_role` — this module additionally
enforces the finer-grained edges above that a single min-role check can't
express.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession

from app.core.audit import AuditEvent
from app.core.audit import record as record_audit_event
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.repositories import user_repository, workspace_member_repository, workspace_repository
from app.schemas.workspace import MemberRead, WorkspaceRead

_ADMIN_ASSIGNABLE_ROLES = {WorkspaceRole.MEMBER, WorkspaceRole.VIEWER}


def _to_workspace_read(workspace: Workspace, *, my_role: WorkspaceRole) -> WorkspaceRead:
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        my_role=my_role,
    )


def create_workspace(
    db: DbSession, *, owner_id: uuid.UUID, name: str, ip_address: str | None = None
) -> WorkspaceRead:
    workspace = workspace_repository.create(db, name=name)
    workspace_member_repository.add_member(
        db, workspace_id=workspace.id, user_id=owner_id, role=WorkspaceRole.OWNER
    )
    record_audit_event(
        db,
        event_type=AuditEvent.WORKSPACE_CREATED,
        user_id=owner_id,
        workspace_id=workspace.id,
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(workspace)
    return _to_workspace_read(workspace, my_role=WorkspaceRole.OWNER)


def list_workspaces_for_user(db: DbSession, *, user_id: uuid.UUID) -> list[WorkspaceRead]:
    workspace_ids = workspace_member_repository.list_workspace_ids_for_user(db, user_id)
    results = []
    for workspace_id in workspace_ids:
        workspace = workspace_repository.get_by_id(db, workspace_id)
        membership = workspace_member_repository.get_membership(
            db, workspace_id=workspace_id, user_id=user_id
        )
        if workspace is not None and membership is not None:
            results.append(_to_workspace_read(workspace, my_role=membership.role))
    return results


def get_workspace(db: DbSession, *, workspace: Workspace, my_role: WorkspaceRole) -> WorkspaceRead:
    return _to_workspace_read(workspace, my_role=my_role)


def update_workspace(
    db: DbSession, *, workspace: Workspace, name: str, my_role: WorkspaceRole
) -> WorkspaceRead:
    workspace_repository.update_name(db, workspace, name=name)
    db.commit()
    return _to_workspace_read(workspace, my_role=my_role)


def delete_workspace(
    db: DbSession,
    *,
    workspace: Workspace,
    deleted_by_user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> None:
    # Audit event recorded (and committed) *before* the delete — the audit
    # repository commits immediately, and this row's `workspace_id` FK must
    # still be valid at that point. `ON DELETE SET NULL` then nulls it out
    # when the workspace is actually deleted next, which is the intended,
    # documented behavior (the audit trail outlives the workspace).
    record_audit_event(
        db,
        event_type=AuditEvent.WORKSPACE_DELETED,
        user_id=deleted_by_user_id,
        workspace_id=workspace.id,
        ip_address=ip_address,
    )
    workspace_repository.delete(db, workspace)
    db.commit()


def _to_member_read(user: User, member: WorkspaceMember) -> MemberRead:
    return MemberRead(
        user_id=user.id, email=user.email, role=member.role, created_at=member.created_at
    )


def list_members(db: DbSession, *, workspace_id: uuid.UUID) -> list[MemberRead]:
    rows = workspace_member_repository.list_for_workspace(db, workspace_id)
    return [_to_member_read(user, member) for member, user in rows]


def add_member(
    db: DbSession,
    *,
    workspace_id: uuid.UUID,
    acting_role: WorkspaceRole,
    acting_user_id: uuid.UUID | None = None,
    email: str,
    role: WorkspaceRole,
    ip_address: str | None = None,
) -> MemberRead:
    _check_role_assignable(acting_role, role)

    target_user = user_repository.get_by_email(db, email)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No user with that email."
        )

    if workspace_member_repository.get_membership(
        db, workspace_id=workspace_id, user_id=target_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this workspace.",
        )

    member = workspace_member_repository.add_member(
        db, workspace_id=workspace_id, user_id=target_user.id, role=role
    )
    record_audit_event(
        db,
        event_type=AuditEvent.WORKSPACE_MEMBER_ADDED,
        user_id=acting_user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={"target_user_id": str(target_user.id), "role": role.value},
    )
    db.commit()
    return _to_member_read(target_user, member)


def update_member_role(
    db: DbSession,
    *,
    workspace_id: uuid.UUID,
    acting_role: WorkspaceRole,
    acting_user_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID,
    new_role: WorkspaceRole,
    ip_address: str | None = None,
) -> MemberRead:
    member = workspace_member_repository.get_membership(
        db, workspace_id=workspace_id, user_id=target_user_id
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    _check_role_assignable(acting_role, member.role)
    _check_role_assignable(acting_role, new_role)

    if member.role == WorkspaceRole.OWNER and new_role != WorkspaceRole.OWNER:
        _guard_last_owner(db, workspace_id)

    previous_role = member.role
    workspace_member_repository.update_role(db, member, role=new_role)
    record_audit_event(
        db,
        event_type=AuditEvent.WORKSPACE_MEMBER_ROLE_CHANGED,
        user_id=acting_user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={
            "target_user_id": str(target_user_id),
            "previous_role": previous_role.value,
            "new_role": new_role.value,
        },
    )
    db.commit()

    target_user = user_repository.get_by_id(db, target_user_id)
    assert target_user is not None
    return _to_member_read(target_user, member)


def remove_member(
    db: DbSession,
    *,
    workspace_id: uuid.UUID,
    acting_role: WorkspaceRole,
    acting_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
    ip_address: str | None = None,
) -> None:
    member = workspace_member_repository.get_membership(
        db, workspace_id=workspace_id, user_id=target_user_id
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    is_self_leave = acting_user_id == target_user_id
    if not is_self_leave:
        _check_role_assignable(acting_role, member.role)

    if member.role == WorkspaceRole.OWNER:
        _guard_last_owner(db, workspace_id)

    record_audit_event(
        db,
        event_type=AuditEvent.WORKSPACE_MEMBER_REMOVED,
        user_id=acting_user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={"target_user_id": str(target_user_id), "self_leave": is_self_leave},
    )
    workspace_member_repository.remove_member(db, member)
    db.commit()


def _check_role_assignable(acting_role: WorkspaceRole, role: WorkspaceRole) -> None:
    """Enforce the role matrix documented at the top of this module."""
    if acting_role == WorkspaceRole.OWNER:
        return
    if acting_role == WorkspaceRole.ADMIN and role in _ADMIN_ASSIGNABLE_ROLES:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to assign or modify that role.",
    )


def _guard_last_owner(db: DbSession, workspace_id: uuid.UUID) -> None:
    if workspace_member_repository.count_owners(db, workspace_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workspace must always have at least one owner.",
        )


__all__ = [
    "create_workspace",
    "list_workspaces_for_user",
    "get_workspace",
    "update_workspace",
    "delete_workspace",
    "list_members",
    "add_member",
    "update_member_role",
    "remove_member",
]
