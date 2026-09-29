"""The `evaluation_runs` entity (docs/DATA_MODEL.md) — a configured
evaluation experiment (embedding model, chunking strategy, retrieval
method, top-K, reranker, LLM), extending Issue #4 Slice 4.4's
fixture-scale evaluation hooks into real, persisted, comparable
experiment tracking (GitHub Issue #7).

`workspace_id` uses `ON DELETE SET NULL`, not CASCADE, and is nullable:
`eval/scripts/run_retrieval_evaluation.py` runs against a dedicated,
throwaway workspace that is deleted at the end of every run (so the
script stays safely re-runnable and never pollutes real workspace
data) — an evaluation run's whole purpose is to be a durable,
comparable-over-time record of pipeline configuration and quality, so
it must outlive the throwaway workspace that produced it, matching
`retrieval_events.conversation_id`'s own "observability/evaluation
record should outlive what it describes" precedent (Issue #4, Slice
4.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Plain strings, not native enums -- matches `AuditLog.event_type`'s/
    # `RetrievalEvent.method`'s own reasoning: these taxonomies may grow
    # (a new embedding provider, chunking strategy, or retrieval method)
    # without a migration for every addition.
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    chunking_strategy: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_method: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    reranker: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str] = mapped_column(Text, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
