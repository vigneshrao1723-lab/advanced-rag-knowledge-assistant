"""FastAPI dependencies for authentication and workspace authorization.

`require_workspace_role` is the single, reusable server-side authorization
gate every workspace-scoped endpoint uses — per this issue's explicit
requirement, a `workspace_id` from the client is never trusted without
verifying the authenticated user is actually a member of that workspace.

Non-members and non-existent workspaces both produce a 404 (not 403) —
membership is confirmed *before* any role check, so a 404 never leaks
whether a workspace exists to someone who isn't a member of it (IDOR
defense; see this issue's security-testing requirements).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import AccessTokenClaims, decode_access_token
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceRole, role_at_least
from app.repositories import user_repository, workspace_member_repository, workspace_repository

_bearer_scheme = HTTPBearer(auto_error=False)

_INVALID_TOKEN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired access token.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_token_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AccessTokenClaims:
    if credentials is None:
        raise _INVALID_TOKEN_ERROR
    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise _INVALID_TOKEN_ERROR
    return claims


def get_current_user(
    claims: AccessTokenClaims = Depends(get_current_token_claims),
    db: Session = Depends(get_db),
) -> User:
    user = user_repository.get_by_id(db, claims.user_id)
    if user is None:
        raise _INVALID_TOKEN_ERROR
    return user


@dataclass
class WorkspaceContext:
    workspace: Workspace
    role: WorkspaceRole
    user: User


def require_workspace_role(
    minimum: WorkspaceRole,
) -> Callable[..., WorkspaceContext]:
    def dependency(
        workspace_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> WorkspaceContext:
        workspace = workspace_repository.get_by_id(db, workspace_id)
        membership = (
            workspace_member_repository.get_membership(
                db, workspace_id=workspace_id, user_id=user.id
            )
            if workspace is not None
            else None
        )
        if workspace is None or membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found."
            )
        if not role_at_least(membership.role, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return WorkspaceContext(workspace=workspace, role=membership.role, user=user)

    return dependency
