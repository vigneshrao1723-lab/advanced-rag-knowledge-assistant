"""Password recovery: forgot-password request and reset.

Security requirements this implements (Issue #2 extended scope):
- Reset tokens are cryptographically random, hashed at rest (never stored
  or logged raw — see `app/core/security.py`), expiring, and single-use
  (`used_at`).
- `request_password_reset` always performs the same outward response
  regardless of whether the email exists — the caller (API layer) returns
  one generic message either way (docs/SECURITY.md; this issue's
  enumeration-protection requirement). The not-found path also burns
  comparable CPU time to the found-user path (a dummy Argon2 verification)
  to narrow, though not perfectly close, the timing gap between the two.
- A successful reset invalidates *every* existing session for that user —
  they must re-authenticate everywhere, on every device (ADR 0003).
- Reset-token validation failures are distinguished (invalid / expired /
  already-used) for the frontend's benefit — this does not weaken
  enumeration resistance, since reaching this endpoint at all requires
  already possessing a token value from the user's inbox (or one's own,
  now-stale token), not a guess about which email exists.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession

from app.core.audit import AuditEvent
from app.core.audit import record as record_audit_event
from app.core.config import get_settings
from app.core.security import (
    generate_password_reset_token,
    hash_password,
    hash_password_reset_token,
    verify_password,
)
from app.repositories import password_reset_token_repository, session_repository, user_repository
from app.services.email_provider import get_email_provider

logger = logging.getLogger("app.password_reset")

# A fixed, valid Argon2 hash used only to burn comparable CPU time when no
# real user exists for the requested email — see module docstring.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization-only")


def request_password_reset(db: DbSession, *, email: str, ip_address: str | None) -> None:
    user = user_repository.get_by_email(db, email)

    if user is None:
        verify_password("irrelevant", _DUMMY_PASSWORD_HASH)
        logger.info("password_reset_requested_unknown_email")
        return

    settings = get_settings()
    raw_token = generate_password_reset_token()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.password_reset_token_expire_minutes
    )
    password_reset_token_repository.create(
        db, user_id=user.id, token_hash=hash_password_reset_token(raw_token), expires_at=expires_at
    )
    record_audit_event(
        db, event_type=AuditEvent.PASSWORD_RESET_REQUESTED, user_id=user.id, ip_address=ip_address
    )
    db.commit()

    reset_link = f"{settings.frontend_url}/reset-password?token={raw_token}"
    get_email_provider().send(
        to=user.email,
        subject="Reset your password",
        text_body=(
            "Someone requested a password reset for your account.\n\n"
            f"Reset your password: {reset_link}\n\n"
            f"This link expires in {settings.password_reset_token_expire_minutes} minutes. "
            "If you didn't request this, you can safely ignore this email."
        ),
    )
    logger.info("password_reset_requested", extra={"user_id": str(user.id)})


def _reset_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message}
    )


def reset_password(
    db: DbSession, *, raw_token: str, new_password: str, ip_address: str | None
) -> None:
    token_hash = hash_password_reset_token(raw_token)
    token = password_reset_token_repository.get_by_hash(db, token_hash)

    if token is None:
        raise _reset_error("reset_token_invalid", "This reset link is invalid.")
    if token.is_used:
        raise _reset_error("reset_token_already_used", "This reset link has already been used.")
    if token.expires_at < datetime.now(UTC):
        raise _reset_error("reset_token_expired", "This reset link has expired.")

    user = user_repository.get_by_id(db, token.user_id)
    if user is None:
        raise _reset_error("reset_token_invalid", "This reset link is invalid.")

    now = datetime.now(UTC)
    user.password_hash = hash_password(new_password)
    password_reset_token_repository.mark_used(db, token, when=now)
    session_repository.revoke_all_for_user(db, user.id, when=now)
    record_audit_event(
        db, event_type=AuditEvent.PASSWORD_RESET_SUCCEEDED, user_id=user.id, ip_address=ip_address
    )
    db.commit()
    logger.info("password_reset_succeeded", extra={"user_id": str(user.id)})


__all__ = ["request_password_reset", "reset_password"]
