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


__all__ = ["create", "list_for_conversation"]
