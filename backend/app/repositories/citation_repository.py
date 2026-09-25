from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.citation import Citation
from app.retrieval.types import RetrievalCandidate


def bulk_create(
    db: Session,
    *,
    message_id: uuid.UUID,
    workspace_id: uuid.UUID,
    candidates: list[tuple[int, RetrievalCandidate]],
) -> list[Citation]:
    """`candidates` is `[(marker, candidate), ...]` — the same pairing
    `app.generation.context_builder.ContextBlock` carries, kept as plain
    tuples here so this repository has no dependency on the generation
    package (matching the existing layering: repositories are a leaf,
    never importing from `services`/higher-level packages).
    `document_id`/`page`/`section` are copied from each candidate onto
    the row at write time (see `app/models/citation.py`'s docstring for
    why). Follows the existing add/flush/no-commit convention -- the
    caller controls the transaction boundary.
    """
    rows = [
        Citation(
            message_id=message_id,
            workspace_id=workspace_id,
            document_id=candidate.document_id,
            chunk_id=candidate.chunk_id,
            page=candidate.page,
            section=candidate.section,
            rank=marker,
        )
        for marker, candidate in candidates
    ]
    db.add_all(rows)
    db.flush()
    for row in rows:
        db.refresh(row)
    return rows


__all__ = ["bulk_create"]
