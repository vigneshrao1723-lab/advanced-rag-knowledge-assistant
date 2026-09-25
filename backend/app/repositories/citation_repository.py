from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
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


def list_for_messages(
    db: Session, *, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Citation]]:
    """One query for every message in a conversation, grouped by
    `message_id` and ordered by `rank` -- avoids an N+1 query when
    listing a conversation's message history (each message may have its
    own citations to show)."""
    if not message_ids:
        return {}
    rows = db.execute(
        select(Citation)
        .where(Citation.message_id.in_(message_ids))
        .order_by(Citation.message_id, Citation.rank)
    ).scalars()
    grouped: dict[uuid.UUID, list[Citation]] = defaultdict(list)
    for row in rows:
        grouped[row.message_id].append(row)
    return dict(grouped)


__all__ = ["bulk_create", "list_for_messages"]
