from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation


def create(
    db: Session, *, workspace_id: uuid.UUID, created_by: uuid.UUID | None
) -> Conversation:
    conversation = Conversation(workspace_id=workspace_id, created_by=created_by)
    db.add(conversation)
    db.flush()
    db.refresh(conversation)
    return conversation


def get_by_id_for_workspace(
    db: Session, *, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation | None:
    """Scoped to `workspace_id` in the query itself, matching
    `document_repository.get_by_id_for_workspace()`'s own IDOR-defense
    shape -- a conversation ID from one workspace can never be looked up
    through another."""
    return db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()


def list_for_workspace(db: Session, *, workspace_id: uuid.UUID) -> list[Conversation]:
    """Newest first -- matches the order a conversation-history UI wants
    to show (most recently active on top)."""
    return list(
        db.execute(
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .order_by(Conversation.updated_at.desc())
        ).scalars()
    )


__all__ = ["create", "get_by_id_for_workspace", "list_for_workspace"]
