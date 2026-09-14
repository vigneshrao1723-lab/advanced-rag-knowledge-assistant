from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead

# Input validation: a defensible minimum, not fabricated complexity rules —
# docs/REQUIREMENTS.md requires "input validation on all auth endpoints" and
# "secure password hashing" without prescribing exact complexity. An upper
# bound guards against pathologically large inputs being hashed.
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 256


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=_PASSWORD_MAX_LENGTH)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=_PASSWORD_MAX_LENGTH)


class IssuedTokens(BaseModel):
    """Internal transport between `auth_service` and the API layer — never
    returned directly to a client. Access/refresh tokens are delivered as
    HttpOnly cookies (`app/core/cookies.py`), not in a JSON body (ADR 0005).
    """

    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
    user: UserRead


class AuthResponse(BaseModel):
    """What a client actually receives from register/login/refresh — the
    tokens themselves are in cookies the client never reads directly."""

    user: UserRead


class SessionRead(BaseModel):
    id: uuid.UUID
    device_label: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    is_current: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=_PASSWORD_MAX_LENGTH)


class MessageResponse(BaseModel):
    message: str
