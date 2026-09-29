"""The `evaluation_results` entity (docs/DATA_MODEL.md) — a computed
metric for an `evaluation_run` (GitHub Issue #7).

One row per metric per run (`recall@3`, `precision@3`, `mrr`, `ndcg@3`,
`hit_rate@3`, ...) rather than a wide/sparse fixed-column table -- an
open-ended metric taxonomy, matching `RetrievalEvent.method`'s own
"plain string, not enum, since this may grow" reasoning. `ON DELETE
CASCADE` from `evaluation_runs`: a result has no independent meaning
once the run that produced it is gone, matching `document_chunks`'
relationship to `documents`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
