from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.retrieval_event import RetrievalEvent


def create(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    method: str,
    results: list[dict[str, Any]],
    rewritten_query_text: str | None = None,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    latency_ms: int | None = None,
) -> RetrievalEvent:
    """Follows the existing add/flush/no-commit convention -- the caller
    controls the transaction boundary, same as every other repository in
    this codebase."""
    event = RetrievalEvent(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        message_id=message_id,
        query_text=query_text,
        rewritten_query_text=rewritten_query_text,
        method=method,
        results=results,
        latency_ms=latency_ms,
    )
    db.add(event)
    db.flush()
    db.refresh(event)
    return event


__all__ = ["create"]
