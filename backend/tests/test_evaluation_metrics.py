"""Unit tests for `app.evaluation.metrics` (Issue #4 "evaluation hooks"
deliverable). Pure functions, no database/HTTP — every case is a plain,
known-answer example.
"""

from __future__ import annotations

import pytest

from app.evaluation.metrics import (
    citation_completeness,
    citation_correctness,
    extract_cited_markers,
    hit_rate_at_k,
    is_extractive_answer_grounded,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

# --- recall_at_k --------------------------------------------------------


def test_recall_at_k_finds_all_relevant_items() -> None:
    assert recall_at_k(["a", "b", "c"], {"a", "b"}, k=3) == 1.0


def test_recall_at_k_finds_partial_relevant_items() -> None:
    assert recall_at_k(["a", "x", "y"], {"a", "b"}, k=3) == 0.5


def test_recall_at_k_respects_k_cutoff() -> None:
    # "b" is relevant but ranked 3rd, outside k=2.
    assert recall_at_k(["a", "x", "b"], {"a", "b"}, k=2) == 0.5


def test_recall_at_k_empty_relevant_set_is_zero() -> None:
    assert recall_at_k(["a", "b"], set(), k=2) == 0.0


def test_recall_at_k_empty_retrieved_list_is_zero() -> None:
    assert recall_at_k([], {"a"}, k=5) == 0.0


def test_recall_at_k_zero_k_is_zero() -> None:
    assert recall_at_k(["a"], {"a"}, k=0) == 0.0


def test_recall_at_k_duplicate_retrieved_ids_do_not_inflate_recall() -> None:
    # "a" appearing twice still only counts as finding one of the two
    # relevant items -- recall is about relevant items found, not slots.
    assert recall_at_k(["a", "a", "a"], {"a", "b"}, k=3) == 0.5


# --- precision_at_k -------------------------------------------------------


def test_precision_at_k_all_relevant() -> None:
    assert precision_at_k(["a", "b"], {"a", "b"}, k=2) == 1.0


def test_precision_at_k_partial() -> None:
    assert precision_at_k(["a", "x"], {"a"}, k=2) == 0.5


def test_precision_at_k_respects_k_cutoff() -> None:
    assert precision_at_k(["a", "x", "y", "z"], {"a", "x", "y", "z"}, k=2) == 1.0


def test_precision_at_k_empty_retrieved_is_zero() -> None:
    assert precision_at_k([], {"a"}, k=5) == 0.0


def test_precision_at_k_zero_k_is_zero() -> None:
    assert precision_at_k(["a"], {"a"}, k=0) == 0.0


def test_precision_at_k_counts_duplicate_positions_independently() -> None:
    # Position-based (standard IR definition): "a" (relevant) at two of
    # three positions -> 2/3, not deduplicated to a single hit.
    assert precision_at_k(["a", "a", "x"], {"a"}, k=3) == pytest.approx(2 / 3)


# --- mrr ------------------------------------------------------------------


def test_mrr_first_result_relevant() -> None:
    assert mrr(["a", "x", "y"], {"a"}) == 1.0


def test_mrr_third_result_relevant() -> None:
    assert mrr(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)


def test_mrr_no_relevant_result_is_zero() -> None:
    assert mrr(["x", "y", "z"], {"a"}) == 0.0


def test_mrr_empty_retrieved_is_zero() -> None:
    assert mrr([], {"a"}) == 0.0


def test_mrr_uses_first_hit_only() -> None:
    # Two relevant items present -- MRR only cares about the earliest.
    assert mrr(["x", "a", "b"], {"a", "b"}) == 0.5


# --- ndcg_at_k --------------------------------------------------------------


def test_ndcg_at_k_perfect_ranking_is_one() -> None:
    # Both relevant items packed at the top -- ideal ordering.
    assert ndcg_at_k(["a", "b", "x"], {"a", "b"}, k=3) == pytest.approx(1.0)


def test_ndcg_at_k_worse_ranking_is_less_than_one() -> None:
    perfect = ndcg_at_k(["a", "b", "x"], {"a", "b"}, k=3)
    worse = ndcg_at_k(["x", "a", "b"], {"a", "b"}, k=3)
    assert worse < perfect


def test_ndcg_at_k_no_relevant_items_is_zero() -> None:
    assert ndcg_at_k(["a", "b"], set(), k=2) == 0.0


def test_ndcg_at_k_no_hits_in_top_k_is_zero() -> None:
    assert ndcg_at_k(["x", "y"], {"a"}, k=2) == 0.0


def test_ndcg_at_k_zero_k_is_zero() -> None:
    assert ndcg_at_k(["a"], {"a"}, k=0) == 0.0


def test_ndcg_at_k_deterministic() -> None:
    args = (["a", "x", "b", "y"], {"a", "b"}, 4)
    assert ndcg_at_k(*args) == ndcg_at_k(*args)


def test_ndcg_at_k_duplicate_relevant_items_never_exceed_one() -> None:
    # A relevant item repeated across multiple positions must not
    # inflate DCG past what IDCG normalizes for -- nDCG is a bounded
    # [0, 1] metric, never higher, regardless of duplicates.
    assert ndcg_at_k(["a", "a", "a"], {"a", "b"}, k=3) <= 1.0


def test_recall_at_k_never_exceeds_one() -> None:
    # Same bound -- a real regression once found in this exact form
    # (duplicate IDs pushed recall to 1.5): recall is a [0, 1] metric.
    assert recall_at_k(["a", "a", "a"], {"a", "b"}, k=3) <= 1.0


# --- hit_rate_at_k ----------------------------------------------------------


def test_hit_rate_at_k_hit() -> None:
    assert hit_rate_at_k(["x", "a"], {"a"}, k=2) == 1.0


def test_hit_rate_at_k_miss() -> None:
    assert hit_rate_at_k(["x", "y"], {"a"}, k=2) == 0.0


def test_hit_rate_at_k_respects_cutoff() -> None:
    assert hit_rate_at_k(["x", "a"], {"a"}, k=1) == 0.0


def test_hit_rate_at_k_zero_k_is_zero() -> None:
    assert hit_rate_at_k(["a"], {"a"}, k=0) == 0.0


# --- citation_completeness / citation_correctness ----------------------


def test_citation_completeness_all_markers_covered() -> None:
    assert citation_completeness("See [1] and [2].", {1, 2}) == 1.0


def test_citation_completeness_partial_coverage() -> None:
    assert citation_completeness("See [1] and [2].", {1}) == 0.5


def test_citation_completeness_no_markers_is_vacuously_complete() -> None:
    assert citation_completeness("No citations here.", set()) == 1.0


def test_citation_completeness_repeated_marker_counts_once() -> None:
    # [1] referenced twice in the text is still one distinct marker to
    # cover -- extract_cited_markers() returns a set, not a multiset.
    assert citation_completeness("[1] and again [1].", {1}) == 1.0


def test_citation_correctness_all_grounded() -> None:
    assert citation_correctness({1, 2}, {1, 2, 3}) == 1.0


def test_citation_correctness_fabricated_citation_is_penalized() -> None:
    # Citation rank 5 doesn't correspond to any block the context
    # actually included -- a fabricated/stale reference.
    assert citation_correctness({1, 5}, {1, 2, 3}) == 0.5


def test_citation_correctness_no_citations_is_vacuously_correct() -> None:
    assert citation_correctness(set(), {1, 2}) == 1.0


def test_extract_cited_markers_parses_all_distinct_markers() -> None:
    assert extract_cited_markers("[1] then [3] then [1] again") == {1, 3}


def test_extract_cited_markers_no_markers_is_empty_set() -> None:
    assert extract_cited_markers("no markers here") == set()


# --- is_extractive_answer_grounded ------------------------------------------


def test_extractive_answer_grounded_for_no_evidence_case() -> None:
    assert is_extractive_answer_grounded(
        "no evidence available", "", no_evidence_answer="no evidence available"
    )


def test_extractive_answer_grounded_for_evidence_case() -> None:
    context_text = "[1] some real content"
    answer = f"Based on the available documents:\n\n{context_text}"
    assert is_extractive_answer_grounded(
        answer, context_text, no_evidence_answer="no evidence available"
    )


def test_extractive_answer_not_grounded_if_content_added() -> None:
    context_text = "[1] some real content"
    tampered = f"Based on the available documents:\n\n{context_text}\n\nand also my own opinion"
    assert not is_extractive_answer_grounded(
        tampered, context_text, no_evidence_answer="no evidence available"
    )
