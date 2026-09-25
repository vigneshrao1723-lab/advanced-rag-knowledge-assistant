"""Result fusion — Reciprocal Rank Fusion (RRF), combining two or more
independently-ranked candidate lists (dense, lexical, ...) into one.

RRF is used (rather than combining raw scores) because dense cosine
similarity and lexical `ts_rank_cd` live on incomparable scales — RRF
only ever looks at each list's own *rank order*, never the underlying
score's magnitude, so no cross-method score normalization is needed.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from app.retrieval.types import RetrievalCandidate

# The standard RRF constant (Cormack et al., 2009) — dampens the
# influence of a candidate's exact rank near the top of a list (rank 1
# vs. rank 2 matters much less than rank 1 vs. rank 50) without needing
# to be tuned per dataset.
_DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[RetrievalCandidate]], *, k: int = _DEFAULT_K
) -> list[RetrievalCandidate]:
    """`rankings` is a list of already-ranked candidate lists (each in
    best-first order, from `dense_search()`/`lexical_search()`). A
    candidate present in more than one list is fused into a single
    entry, using the first occurrence's content/metadata (identical
    across lists for the same `chunk_id` anyway) and a summed RRF score.
    Returns one list, best-first, deduplicated by `chunk_id`.
    """
    scores: dict[uuid.UUID, float] = {}
    candidates_by_id: dict[uuid.UUID, RetrievalCandidate] = {}

    for ranking in rankings:
        for rank, candidate in enumerate(ranking, start=1):
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (k + rank)
            candidates_by_id.setdefault(candidate.chunk_id, candidate)

    fused = [
        replace(candidate, score=scores[chunk_id])
        for chunk_id, candidate in candidates_by_id.items()
    ]
    fused.sort(key=lambda candidate: candidate.score, reverse=True)
    return fused


__all__ = ["reciprocal_rank_fusion"]
