from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def create(db: Session, *, email: str, password_hash: str) -> User:
    user = User(email=email.lower(), password_hash=password_hash)
    db.add(user)
    db.flush()
    db.refresh(user)
    return user
