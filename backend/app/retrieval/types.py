"""Shared value types for the retrieval pipeline. Deliberately not the
`DocumentChunk` SQLAlchemy model — a `RetrievalCandidate` is a read-only,
already-scored snapshot, not a live ORM row, matching `chunking.py`'s own
`Chunk` dataclass precedent (Issue #3) for the same reason: no accidental
database dependency for callers that only need the value."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    content: str
    page: int | None
    section: str | None
    # Meaning depends on the stage that produced this candidate:
    # dense -> cosine similarity (1 - cosine distance, higher is better);
    # lexical -> ts_rank_cd; fused -> RRF score; reranked -> the
    # reranker's own score. Always "higher is better" at every stage, so
    # callers never need to know which stage produced a given list.
    score: float


__all__ = ["RetrievalCandidate"]
