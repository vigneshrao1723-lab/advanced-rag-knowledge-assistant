"""Registration, login, refresh, logout, and session/device management.

Per docs/API_CONTRACT.md, `/api/v1/auth` is one of the two namespaces
(alongside `/api/v1/health`) that never requires a session to reach it —
except the session-listing/revocation endpoints, which obviously require an
authenticated caller.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.dependencies import get_current_token_claims, get_current_user
from app.core.rate_limit import (
    enforce_login_rate_limit,
    enforce_refresh_rate_limit,
    enforce_register_rate_limit,
)
from app.core.security import AccessTokenClaims
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    SessionRead,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_DEVICE_LABEL_MAX_LENGTH = 255


def _device_label(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    if not user_agent:
        return None
    return user_agent[:_DEVICE_LABEL_MAX_LENGTH]


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
def register(
    request: Request, body: RegisterRequest, db: Session = Depends(get_db)
) -> TokenResponse:
    return auth_service.register(
        db, email=body.email, password=body.password, device_label=_device_label(request)
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return auth_service.login(
        db, email=body.email, password=body.password, device_label=_device_label(request)
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_refresh_rate_limit)],
)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return auth_service.refresh(db, raw_refresh_token=body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutRequest, db: Session = Depends(get_db)) -> None:
    auth_service.logout(db, raw_refresh_token=body.refresh_token)


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(
    user: User = Depends(get_current_user),
    claims: AccessTokenClaims = Depends(get_current_token_claims),
    db: Session = Depends(get_db),
) -> list[SessionRead]:
    return auth_service.list_sessions(db, user_id=user.id, current_session_id=claims.session_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    auth_service.revoke_session(db, user_id=user.id, session_id=session_id)
