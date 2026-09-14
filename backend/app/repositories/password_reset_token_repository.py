from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken


def create(
    db: Session, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
) -> PasswordResetToken:
    entry = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(entry)
    db.flush()
    db.refresh(entry)
    return entry


def get_by_hash(db: Session, token_hash: str) -> PasswordResetToken | None:
    return db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    ).scalar_one_or_none()


def mark_used(db: Session, token: PasswordResetToken, *, when: datetime) -> None:
    token.used_at = when
    db.flush()
