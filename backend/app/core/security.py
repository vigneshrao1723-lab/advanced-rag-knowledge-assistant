"""Password hashing, access-token (JWT), and refresh-token primitives.

Password hashing: Argon2id via `argon2-cffi` — see
docs/DECISIONS/0004-password-hashing-argon2id.md.

Access tokens: short-lived, signature-based JWTs (HS256) validated without a
database round-trip, per ADR 0003.

Refresh tokens: opaque, high-entropy random strings formatted as
`<session_id>.<secret>`. Only a SHA-256 hash of `<secret>` is ever persisted
(app/models/session.py) — the raw token is never stored, logged, or
returned in error responses.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_password_hasher = PasswordHasher()

_JWT_ALGORITHM = "HS256"
_JWT_SUBJECT_CLAIM = "sub"
_JWT_TYPE_CLAIM = "type"
_ACCESS_TOKEN_TYPE = "access"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


_SESSION_ID_CLAIM = "sid"


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        _JWT_SUBJECT_CLAIM: str(user_id),
        _SESSION_ID_CLAIM: str(session_id),
        _JWT_TYPE_CLAIM: _ACCESS_TOKEN_TYPE,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> AccessTokenClaims | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    if payload.get(_JWT_TYPE_CLAIM) != _ACCESS_TOKEN_TYPE:
        return None

    try:
        user_id = uuid.UUID(str(payload.get(_JWT_SUBJECT_CLAIM)))
        session_id = uuid.UUID(str(payload.get(_SESSION_ID_CLAIM)))
    except (ValueError, TypeError):
        return None

    return AccessTokenClaims(user_id=user_id, session_id=session_id)


@dataclass(frozen=True)
class RefreshToken:
    session_id: uuid.UUID
    secret: str

    def encode(self) -> str:
        return f"{self.session_id}.{self.secret}"

    @property
    def secret_hash(self) -> str:
        return hash_refresh_secret(self.secret)


def generate_refresh_token(session_id: uuid.UUID | None = None) -> RefreshToken:
    return RefreshToken(session_id=session_id or uuid.uuid4(), secret=secrets.token_urlsafe(32))


def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def parse_refresh_token(raw_token: str) -> tuple[uuid.UUID, str] | None:
    """Split a client-presented refresh token into (session_id, secret).

    Returns None for any malformed input — never raises on untrusted input.
    """
    session_id_part, _, secret = raw_token.partition(".")
    if not secret:
        return None
    try:
        session_id = uuid.UUID(session_id_part)
    except ValueError:
        return None
    return session_id, secret
