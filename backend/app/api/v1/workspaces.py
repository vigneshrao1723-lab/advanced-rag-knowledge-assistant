"""Workspace CRUD and membership endpoints.

Every route below a bare `/workspaces` create/list resolves `workspace_id`
through `require_workspace_role`, which verifies the authenticated caller is
actually a member of that workspace before anything else runs — a
`workspace_id` from the client is never trusted on its own (see
app/core/dependencies.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.dependencies import WorkspaceContext, get_current_user, require_workspace_role
from app.models.user import User
from app.models.workspace_member import WorkspaceRole
from app.schemas.workspace import (
    MemberAdd,
    MemberRead,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services import workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> WorkspaceRead:
    return workspace_service.create_workspace(db, owner_id=user.id, name=body.name)


@router.get("", response_model=list[WorkspaceRead])
def list_workspaces(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[WorkspaceRead]:
    return workspace_service.list_workspaces_for_user(db, user_id=user.id)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> WorkspaceRead:
    return workspace_service.get_workspace(db, workspace=ctx.workspace, my_role=ctx.role)


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(
    body: WorkspaceUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.ADMIN)),
    db: Session = Depends(get_db),
) -> WorkspaceRead:
    return workspace_service.update_workspace(
        db, workspace=ctx.workspace, name=body.name, my_role=ctx.role
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.OWNER)),
    db: Session = Depends(get_db),
) -> None:
    workspace_service.delete_workspace(db, workspace=ctx.workspace)


@router.get("/{workspace_id}/members", response_model=list[MemberRead])
def list_members(
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> list[MemberRead]:
    return workspace_service.list_members(db, workspace_id=ctx.workspace.id)


@router.post(
    "/{workspace_id}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED
)
def add_member(
    body: MemberAdd,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.ADMIN)),
    db: Session = Depends(get_db),
) -> MemberRead:
    return workspace_service.add_member(
        db, workspace_id=ctx.workspace.id, acting_role=ctx.role, email=body.email, role=body.role
    )


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberRead)
def update_member_role(
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.ADMIN)),
    db: Session = Depends(get_db),
) -> MemberRead:
    return workspace_service.update_member_role(
        db,
        workspace_id=ctx.workspace.id,
        acting_role=ctx.role,
        target_user_id=user_id,
        new_role=body.role,
    )


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> None:
    workspace_service.remove_member(
        db,
        workspace_id=ctx.workspace.id,
        acting_role=ctx.role,
        acting_user_id=ctx.user.id,
        target_user_id=user_id,
    )
