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

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.audit import AuditEvent
from app.core.audit import record as record_audit_event
from app.core.cookies import ACCESS_TOKEN_COOKIE
from app.core.db import get_db
from app.core.rate_limit import client_ip
from app.core.security import AccessTokenClaims, decode_access_token
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceRole, role_at_least
from app.repositories import user_repository, workspace_member_repository, workspace_repository

_INVALID_TOKEN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired access token.",
)


def get_current_token_claims(request: Request) -> AccessTokenClaims:
    """Reads the access token from its HttpOnly cookie — never a header,
    never JavaScript-accessible (ADR 0005)."""
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token is None:
        raise _INVALID_TOKEN_ERROR
    claims = decode_access_token(token)
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
        request: Request,
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
            # Audited server-side even though the client only ever sees a
            # generic 404 — this is exactly the "repeated cross-workspace
            # access attempts" signal docs/SECURITY.md's audit log and the
            # future abuse-detection layer rely on. Can't use the FK
            # `workspace_id` column when the workspace itself doesn't
            # exist (it would violate the FK constraint); the attempted ID
            # goes in `metadata` instead in that case.
            record_audit_event(
                db,
                event_type=AuditEvent.AUTHORIZATION_DENIED,
                user_id=user.id,
                workspace_id=workspace.id if workspace is not None else None,
                ip_address=client_ip(request),
                metadata={
                    "reason": "not_a_member" if workspace is not None else "workspace_not_found",
                    "attempted_workspace_id": str(workspace_id),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found."
            )
        if not role_at_least(membership.role, minimum):
            record_audit_event(
                db,
                event_type=AuditEvent.AUTHORIZATION_DENIED,
                user_id=user.id,
                workspace_id=workspace.id,
                ip_address=client_ip(request),
                metadata={
                    "reason": "insufficient_role",
                    "my_role": membership.role.value,
                    "required_minimum": minimum.value,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return WorkspaceContext(workspace=workspace, role=membership.role, user=user)

    return dependency
