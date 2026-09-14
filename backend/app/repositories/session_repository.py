from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.session import Session


def create(
    db: DbSession,
    *,
    id: uuid.UUID,
    user_id: uuid.UUID,
    refresh_token_hash: str,
    expires_at: datetime,
    device_label: str | None,
) -> Session:
    session = Session(
        id=id,
        user_id=user_id,
        refresh_token_hash=refresh_token_hash,
        expires_at=expires_at,
        device_label=device_label,
    )
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


def get_by_id(db: DbSession, session_id: uuid.UUID) -> Session | None:
    return db.get(Session, session_id)


def list_for_user(db: DbSession, user_id: uuid.UUID) -> list[Session]:
    return list(
        db.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .order_by(Session.last_used_at.desc())
        )
        .scalars()
        .all()
    )


def revoke(db: DbSession, session: Session, *, when: datetime) -> None:
    session.revoked_at = when
    db.flush()


def revoke_all_for_user(db: DbSession, user_id: uuid.UUID, *, when: datetime) -> None:
    """Used after a successful password reset: the user must re-authenticate
    everywhere, on every device."""
    for session in list_for_user(db, user_id):
        session.revoked_at = when
    db.flush()


def rotate(
    db: DbSession,
    session: Session,
    *,
    new_refresh_token_hash: str,
    new_expires_at: datetime,
    when: datetime,
) -> None:
    session.refresh_token_hash = new_refresh_token_hash
    session.expires_at = new_expires_at
    session.last_used_at = when
    db.flush()
