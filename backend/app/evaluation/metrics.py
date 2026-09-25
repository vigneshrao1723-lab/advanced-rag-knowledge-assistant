"""Retrieval and generation evaluation metrics (docs/EVALUATION.md).

Pure functions — no database, HTTP, or provider dependency. Operate on
plain, already-computed inputs (a ranked list of retrieved IDs, a set of
known-relevant IDs) so they're trivially unit-testable and reusable by
both an ad-hoc script and, later, a real evaluation harness. This is the
"evaluation hooks" deliverable for GitHub Issue #4 ("wiring that can
compute the docs/EVALUATION.md metrics... against a small fixture set,
proving the pipeline is measurable") — the full experiment-tracking
system (`evaluation_runs`/`evaluation_results`, docs/DATA_MODEL.md) is
Issue #7's job, not this module's.

All retrieval metrics use **binary relevance** (an item either is or
isn't in the `relevant` set) — matching docs/EVALUATION.md's own metric
definitions, which don't call for graded relevance.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

# --- Retrieval metrics --------------------------------------------------


def recall_at_k[T](retrieved: Sequence[T], relevant: set[T], k: int) -> float:
    """Fraction of *distinct* relevant items found within the top-K
    retrieved results. `0.0` if there are no relevant items to find
    (rather than raising or returning `1.0`/`NaN` — an empty relevant
    set means this query can never be satisfied, which is a `0.0`, not
    "vacuously perfect"). Counts distinct items found, not matching
    positions — unlike `precision_at_k()`, a duplicate ID appearing
    twice in `retrieved` must not push recall above `1.0`."""
    if not relevant or k <= 0:
        return 0.0
    top_k_distinct = set(retrieved[:k])
    hits = len(top_k_distinct & relevant)
    return hits / len(relevant)


def precision_at_k[T](retrieved: Sequence[T], relevant: set[T], k: int) -> float:
    """Fraction of the top-K retrieved results that are relevant.
    Counts each retrieved *position* independently (so a duplicate ID
    appearing twice in `retrieved` counts twice), matching standard IR
    definitions — retrieval pipelines in this project already dedupe
    (RRF fusion dedupes by `chunk_id`), so duplicates are not expected
    in practice, but this function does not assume that."""
    if k <= 0:
        return 0.0
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for item in top_k if item in relevant)
    return hits / len(top_k)


def mrr[T](retrieved: Sequence[T], relevant: set[T]) -> float:
    """Reciprocal of the rank (1-based) of the first relevant result.
    `0.0` if no relevant result appears anywhere in `retrieved`."""
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k[T](retrieved: Sequence[T], relevant: set[T], k: int) -> float:
    """Normalized Discounted Cumulative Gain at K, binary relevance
    (each *distinct* relevant item's first occurrence contributes
    `1 / log2(rank + 1)`), normalized against the best-possible ordering
    (all relevant items packed into the first `min(len(relevant), k)`
    positions). `0.0` when there is no possible positive gain (no
    relevant items, or `k <= 0`). A relevant item's *second* occurrence
    in `retrieved` (a duplicate) contributes no further gain — it
    represents the same piece of information already found, not new
    evidence — the same reasoning `recall_at_k()` applies, so a
    duplicate can never push nDCG above `1.0`."""
    if k <= 0 or not relevant:
        return 0.0
    top_k = retrieved[:k]
    seen: set[T] = set()
    dcg = 0.0
    for rank, item in enumerate(top_k, start=1):
        if item in relevant and item not in seen:
            dcg += 1.0 / math.log2(rank + 1)
            seen.add(item)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def hit_rate_at_k[T](retrieved: Sequence[T], relevant: set[T], k: int) -> float:
    """`1.0` if at least one relevant item appears in the top-K, else
    `0.0`."""
    if k <= 0:
        return 0.0
    top_k = retrieved[:k]
    return 1.0 if any(item in relevant for item in top_k) else 0.0


# --- Generation / citation groundedness checks -------------------------
#
# docs/EVALUATION.md's "faithfulness"/"answer relevance"/"context
# relevance" metrics are semantic judgments that genuinely require
# either a human rater or an LLM-as-judge -- neither exists for this
# project's current deterministic/local `LLMProvider`
# (`LocalGroundedExtractiveProvider`, Issue #4 Slice 4.3), and
# fabricating a numeric score for them would violate
# docs/EVALUATION.md's own "never fabricate results" rule. What *is*
# real and mechanically checkable today: whether citations correspond
# to evidence actually included in the built context (correctness),
# whether every citation marker referenced in the answer text has a
# matching persisted citation (completeness), and — specific to the
# extractive provider's own guarantee — whether the answer's content is
# provably confined to what the context contained (a real, checkable
# groundedness property for *this* provider, not a general-purpose
# faithfulness score).

_CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")


def extract_cited_markers(answer_text: str) -> set[int]:
    """Every `[n]` citation marker literally referenced in the answer
    text."""
    return {int(match) for match in _CITATION_MARKER_RE.findall(answer_text)}


def citation_completeness(answer_text: str, citation_ranks: set[int]) -> float:
    """Fraction of `[n]` markers referenced in the answer text that have
    a corresponding persisted citation (`citation_ranks` — the set of
    `Citation.rank` values actually stored for that message). `1.0`
    (vacuously) if the answer references no markers at all — nothing to
    fail to cover."""
    cited_markers = extract_cited_markers(answer_text)
    if not cited_markers:
        return 1.0
    matched = cited_markers & citation_ranks
    return len(matched) / len(cited_markers)


def citation_correctness(citation_ranks: set[int], context_marker_set: set[int]) -> float:
    """Fraction of persisted citations (`citation_ranks`) that
    correspond to evidence actually included in the built context
    (`context_marker_set` — the set of markers `build_context()`
    assigned) — i.e. never a fabricated reference to evidence that was
    never retrieved. `1.0` (vacuously) if there are no citations to
    check."""
    if not citation_ranks:
        return 1.0
    matched = citation_ranks & context_marker_set
    return len(matched) / len(citation_ranks)


def is_extractive_answer_grounded(
    answer_text: str, context_text: str, *, no_evidence_answer: str
) -> bool:
    """True iff `answer_text` is exactly one of the two shapes
    `LocalGroundedExtractiveProvider.generate()` can ever produce: the
    fixed no-evidence answer, or the fixed framing prefix followed by
    `context_text` verbatim. This is a precise, mechanical groundedness
    check for *this specific, extractive* provider — it proves the
    answer contains nothing beyond the retrieved evidence, by
    construction. It is not a general-purpose faithfulness metric; a
    real (future) LLM provider's output would need a different,
    genuinely semantic check (a human rater or an LLM-as-judge), not
    this one.
    """
    if answer_text == no_evidence_answer:
        return True
    return answer_text == f"Based on the available documents:\n\n{context_text}"


__all__ = [
    "citation_completeness",
    "citation_correctness",
    "extract_cited_markers",
    "hit_rate_at_k",
    "is_extractive_answer_grounded",
    "mrr",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
]
