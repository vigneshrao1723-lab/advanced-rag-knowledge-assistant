"""Registration, login, refresh, logout, and session management.

Security notes:
- Login failures always return the same generic message regardless of
  whether the email exists, to resist user enumeration via the login
  endpoint (docs/SECURITY.md; this issue's "user enumeration
  considerations"). Registration still reports a duplicate email as a
  conflict — that is a deliberate, narrower tradeoff: without an email
  verification flow (out of scope here), silently accepting a duplicate
  registration would leave a legitimate user unable to understand why they
  can never log in with "their" account.
- Raw access tokens, raw refresh tokens, and passwords are never logged —
  only IDs and outcomes (see the `logger.info` calls below).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_secret,
    parse_refresh_token,
    verify_password,
)
from app.models.user import User
from app.repositories import session_repository, user_repository
from app.schemas.auth import SessionRead, TokenResponse
from app.schemas.user import UserRead

logger = logging.getLogger("app.auth")

_GENERIC_LOGIN_ERROR = "Incorrect email or password."


def register(
    db: DbSession, *, email: str, password: str, device_label: str | None
) -> TokenResponse:
    if user_repository.get_by_email(db, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = user_repository.create(db, email=email, password_hash=hash_password(password))
    tokens = _issue_tokens(db, user, device_label=device_label)
    db.commit()
    logger.info("user_registered", extra={"user_id": str(user.id)})
    return tokens


def login(db: DbSession, *, email: str, password: str, device_label: str | None) -> TokenResponse:
    user = user_repository.get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        logger.info("login_failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_ERROR)

    tokens = _issue_tokens(db, user, device_label=device_label)
    db.commit()
    logger.info("login_succeeded", extra={"user_id": str(user.id)})
    return tokens


def refresh(db: DbSession, *, raw_refresh_token: str) -> TokenResponse:
    parsed = parse_refresh_token(raw_refresh_token)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token."
        )
    session_id, secret = parsed

    session = session_repository.get_by_id(db, session_id)
    if session is None or session.is_revoked or session.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token."
        )

    if session.refresh_token_hash != hash_refresh_secret(secret):
        # Reuse of a rotated-out refresh token: treat the session as
        # compromised and revoke it immediately (ADR 0003's open item,
        # resolved here as "revoke just the one session").
        session_repository.revoke(db, session, when=datetime.now(UTC))
        db.commit()
        logger.info("refresh_token_reuse_detected", extra={"session_id": str(session_id)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token."
        )

    user = user_repository.get_by_id(db, session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token."
        )

    settings = get_settings()
    now = datetime.now(UTC)
    new_refresh = generate_refresh_token(session_id=session.id)
    session_repository.rotate(
        db,
        session,
        new_refresh_token_hash=new_refresh.secret_hash,
        new_expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        when=now,
    )
    access_token, expires_at = create_access_token(user.id, session.id)
    db.commit()
    logger.info("refresh_succeeded", extra={"user_id": str(user.id), "session_id": str(session.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh.encode(),
        expires_in=int((expires_at - now).total_seconds()),
        user=UserRead.model_validate(user),
    )


def logout(db: DbSession, *, raw_refresh_token: str) -> None:
    parsed = parse_refresh_token(raw_refresh_token)
    if parsed is None:
        return
    session_id, _ = parsed

    session = session_repository.get_by_id(db, session_id)
    if session is None or session.is_revoked:
        return

    session_repository.revoke(db, session, when=datetime.now(UTC))
    db.commit()
    logger.info("logout_succeeded", extra={"session_id": str(session_id)})


def list_sessions(
    db: DbSession, *, user_id: uuid.UUID, current_session_id: uuid.UUID | None
) -> list[SessionRead]:
    sessions = session_repository.list_for_user(db, user_id)
    return [
        SessionRead(
            id=s.id,
            device_label=s.device_label,
            created_at=s.created_at,
            last_used_at=s.last_used_at,
            expires_at=s.expires_at,
            is_current=s.id == current_session_id,
        )
        for s in sessions
    ]


def revoke_session(db: DbSession, *, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    session = session_repository.get_by_id(db, session_id)
    if session is None or session.user_id != user_id:
        # Same 404 whether it doesn't exist or belongs to someone else —
        # never confirm another user's session IDs exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    session_repository.revoke(db, session, when=datetime.now(UTC))
    db.commit()


def _issue_tokens(db: DbSession, user: User, *, device_label: str | None) -> TokenResponse:
    settings = get_settings()
    now = datetime.now(UTC)
    new_refresh = generate_refresh_token()

    session_repository.create(
        db,
        id=new_refresh.session_id,
        user_id=user.id,
        refresh_token_hash=new_refresh.secret_hash,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        device_label=device_label,
    )
    access_token, expires_at = create_access_token(user.id, new_refresh.session_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh.encode(),
        expires_in=int((expires_at - now).total_seconds()),
        user=UserRead.model_validate(user),
    )


__all__ = [
    "register",
    "login",
    "refresh",
    "logout",
    "list_sessions",
    "revoke_session",
]
