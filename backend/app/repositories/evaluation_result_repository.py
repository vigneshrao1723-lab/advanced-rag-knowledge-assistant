from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.evaluation_result import EvaluationResult


def bulk_create(
    db: Session, *, evaluation_run_id: uuid.UUID, metrics: dict[str, float]
) -> list[EvaluationResult]:
    """`metrics` is `{metric_name: value}`, e.g. `{"recall@3": 1.0,
    "precision@3": 0.33, ...}` -- one row per entry. Follows the
    existing add/flush/no-commit convention -- the caller controls the
    transaction boundary."""
    rows = [
        EvaluationResult(evaluation_run_id=evaluation_run_id, metric_name=name, metric_value=value)
        for name, value in metrics.items()
    ]
    db.add_all(rows)
    db.flush()
    for row in rows:
        db.refresh(row)
    return rows


__all__ = ["bulk_create"]
