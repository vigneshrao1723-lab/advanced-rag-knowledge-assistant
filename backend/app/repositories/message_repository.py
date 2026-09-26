from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message, MessageRole


def create(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    role: MessageRole,
    content: str,
) -> Message:
    message = Message(
        conversation_id=conversation_id, workspace_id=workspace_id, role=role, content=content
    )
    db.add(message)
    db.flush()
    db.refresh(message)
    return message


def list_for_conversation(db: Session, *, conversation_id: uuid.UUID) -> list[Message]:
    """Ordered by `created_at` -- real chat/conversation order."""
    return list(
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        ).scalars()
    )


def get_by_id_for_conversation(
    db: Session, *, conversation_id: uuid.UUID, message_id: uuid.UUID
) -> Message | None:
    """Scoped to `conversation_id` in the query itself, matching
    `document_repository.get_by_id_for_workspace()`'s own IDOR-defense
    shape -- a message ID from one conversation can never be looked up
    through another (Issue #6's voice-playback endpoint)."""
    return db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
        )
    ).scalar_one_or_none()


__all__ = ["create", "get_by_id_for_conversation", "list_for_conversation"]
