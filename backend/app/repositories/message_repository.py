from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message, MessageFeedback, MessageRole


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


def set_feedback(db: Session, *, message: Message, feedback: MessageFeedback | None) -> Message:
    """Updates an already-persisted row in place -- never inserts.
    Setting the same rating again, a different rating, or `None`
    (clearing it) are all valid, idempotent transitions."""
    message.feedback = feedback
    db.add(message)
    db.flush()
    db.refresh(message)
    return message


def get_preceding_user_message(
    db: Session, *, conversation_id: uuid.UUID, message: Message
) -> Message | None:
    """The `USER` message this `message` (expected to be an `ASSISTANT`
    row) answered -- the most recent `USER` message strictly before it
    in the same conversation, by `created_at`. Used by regenerate
    (GitHub Issue #41): re-running generation needs the original
    question, not the answer being replaced."""
    return db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == MessageRole.USER,
            Message.created_at < message.created_at,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def update_content(
    db: Session, *, message: Message, content: str, feedback: MessageFeedback | None
) -> Message:
    """Replaces an already-persisted message's content in place --
    regenerate (Issue #41) overwriting a superseded answer, never a new
    row. `feedback` is set explicitly (not left untouched) because a
    rating on the old content doesn't describe the new content --
    callers pass `None` to clear it, matching `set_feedback()`'s own
    semantics for "no feedback"."""
    message.content = content
    message.feedback = feedback
    db.add(message)
    db.flush()
    db.refresh(message)
    return message


def delete(db: Session, *, message: Message) -> None:
    """Removes one message row (its citations cascade). Used to withdraw a
    user message whose answer could not be generated, so a failed attempt
    leaves no orphan question in the history."""
    db.delete(message)
    db.flush()


__all__ = [
    "create",
    "delete",
    "get_by_id_for_conversation",
    "get_preceding_user_message",
    "list_for_conversation",
    "set_feedback",
    "update_content",
]
