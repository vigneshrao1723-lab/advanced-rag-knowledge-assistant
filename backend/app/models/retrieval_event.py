"""The `retrieval_events` entity (docs/DATA_MODEL.md) — a record of a
retrieval operation (query, method, results, scores) for observability
and evaluation (GitHub Issue #4, Slice 4.1). Feeds `docs/EVALUATION.md`'s
metrics (Recall@K, Precision@K, MRR, nDCG, Hit Rate) and
`docs/RAG_DESIGN.md`'s "Observability" section.

`conversation_id`/`message_id` use `ON DELETE SET NULL`, not CASCADE,
matching `AuditLog`'s own precedent: a retrieval event is an
observability/evaluation record, not conversation content, and should
outlive the conversation/message it was made for (e.g. if the
conversation is later deleted, historical retrieval-quality data should
not silently disappear with it). Both are nullable — a standalone
`/search` call (not part of a chat turn) has no conversation/message to
attach to.

`results` (JSONB) holds the ranked candidate list at the point this
event was recorded — `[{chunk_id, document_id, score, rank}, ...]` — a
snapshot, not a live reference, so it stays meaningful even after the
underlying chunks are later re-embedded, re-chunked, or deleted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RetrievalEvent(Base):
    __tablename__ = "retrieval_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Set only when query rewriting actually changed the query -- the
    # original `query_text` above is always preserved unchanged, per
    # docs/REQUIREMENTS.md "Query handling": "while preserving the
    # original user query for transparency/debugging."
    rewritten_query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plain string, not a native enum -- matches `AuditLog.event_type`'s
    # own reasoning: this taxonomy ("dense"/"lexical"/"hybrid" today) may
    # grow, and a native enum would require a migration for every new
    # retrieval method.
    method: Mapped[str] = mapped_column(Text, nullable=False)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
