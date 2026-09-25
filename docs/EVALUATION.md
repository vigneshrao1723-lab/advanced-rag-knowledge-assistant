# Evaluation

**Status:** PARTIALLY IMPLEMENTED — describes the intended evaluation
methodology. **Evaluation "hooks" (GitHub Issue #4) exist and have been
run against a small, deterministic fixture set — see "Evaluation hooks"
below for the real, reproducible numbers this produced.** The full
evaluation/experiment-tracking system (`evaluation_runs`/
`evaluation_results` persistence, cross-configuration comparison
dashboards) described elsewhere in this document remains PROPOSED
(Issue #7). No number in this document was fabricated — see "Rule:
never fabricate results" below.

## Purpose

Retrieval and generation quality must be measurable, not asserted. This
document defines the metrics and comparisons the system is designed to
support once an ingestion + retrieval + generation pipeline actually exists
to evaluate.

## Evaluation hooks (GitHub Issue #4, Slice 4.4)

**Proves the pipeline is measurable — the full experiment-tracking
system below (`evaluation_runs`/`evaluation_results`) is Issue #7's
job, not this.**

- **Metrics implementation**: `backend/app/evaluation/metrics.py` — pure
  functions for every retrieval metric below (binary relevance:
  `recall_at_k`, `precision_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`)
  plus real, mechanically-checkable generation/citation checks
  (`citation_completeness`, `citation_correctness`,
  `is_extractive_answer_grounded`) — see that module's own docstring
  for why "faithfulness"/"answer relevance" aren't reported as
  fabricated numeric scores while the shipped `LLMProvider` is
  deterministic/extractive rather than a real model. 42 unit tests
  (`backend/tests/test_evaluation_metrics.py`), including known-answer
  cases, empty inputs, ties, and duplicate-candidate handling. **A real
  bug was found and fixed during test-writing**: `recall_at_k()` and
  `ndcg_at_k()`'s first drafts both counted a duplicate relevant ID
  once per *position* it appeared at, which could push either metric
  above the mathematically-required `[0, 1]` bound — fixed to count
  each distinct relevant item at most once (its first, best-ranked
  occurrence), matching `mrr()`'s own "first hit only" semantics. See
  `SOLVING.md` for the full write-up.
- **Fixture dataset**: `eval/datasets/retrieval_fixture.py` — 6 short,
  single-chunk documents (refund/shipping/warranty/privacy/account-
  security/product-specs policies) and 7 queries with known relevance
  judgments. Deliberately short (each document becomes exactly one
  chunk) so "the relevant document" and "the relevant chunk" are the
  same thing, keeping relevance judgments unambiguous. Query wording
  deliberately shares literal keywords with its relevant document —
  `LocalHashingEmbeddingProvider` (Issue #3) has no semantic
  understanding, so this keeps the fixture honest about what *this*
  pipeline's current deterministic/local providers can actually do,
  rather than testing an idealized embedding model this project doesn't
  have.
- **Runnable script**: `eval/scripts/run_retrieval_evaluation.py` —
  ingests the fixture set through the real pipeline (cleaning,
  structure-aware chunking, embedding — the same modules
  `process_document()` itself uses), runs `hybrid_search()` for every
  fixture query, computes the metrics above, runs `generate_answer()`
  for two representative queries and computes the citation checks, and
  writes `eval/results/retrieval_evaluation.json`. Uses a dedicated,
  throwaway workspace, deleted at the end of every run (verified via a
  direct query showing zero leftover rows) — safely re-runnable,
  confirmed deterministic across repeated runs (identical output twice
  in a row). Run it yourself: `cd backend && uv run python
  ../eval/scripts/run_retrieval_evaluation.py`.
- **Real results from the run committed in `eval/results/retrieval_evaluation.json`**
  (top-K = 3, 6 documents, 7 queries): **Recall@3 = 1.0, Precision@3 =
  0.33, MRR = 1.0, nDCG@3 = 1.0, Hit Rate@3 = 1.0**, averaged across all
  7 queries — every query's single relevant document was always
  retrieved and ranked first; Precision@3 is exactly `1/3` because only
  one of the three retrieved slots is ever relevant in a 6-document
  corpus at `k=3`, not a retrieval defect. Generation checks on 2
  sample queries: citation completeness/correctness both `1.0`, and
  `is_extractive_answer_grounded` `true` for both — expected, since
  `LocalGroundedExtractiveProvider` only ever quotes retrieved evidence
  by construction (see `app/generation/llm_provider.py`). **These
  numbers describe this specific fixture set and this project's current
  local/deterministic providers ([ADR 0007](DECISIONS/0007-local-providers-for-embedding-reranking-generation.md))
  — they are not a claim of production-scale retrieval quality**, which
  would need a larger, more realistic corpus and a real embedding
  model, per "Rule: never fabricate results" below.

## Retrieval metrics

- **Recall@K** — fraction of relevant chunks found within the top-K results.
- **Precision@K** — fraction of the top-K results that are relevant.
- **MRR** (Mean Reciprocal Rank) — position of the first relevant result.
- **nDCG** (normalized Discounted Cumulative Gain) — rank-aware relevance
  quality.
- **Hit Rate** — fraction of queries with at least one relevant result in
  the top-K.

## Generation metrics

- **Faithfulness** — does the answer only claim what's supported by the
  retrieved evidence?
- **Answer relevance** — does the answer actually address the question?
- **Context relevance** — was the retrieved context relevant to the
  question?
- **Citation correctness** — do citations point to evidence that actually
  supports the claim they're attached to?
- **Citation completeness** — are all supportable claims in the answer
  actually cited?

## Configuration comparison

The evaluation harness is intended to compare, on the same query set:

- Dense retrieval only
- BM25 only
- Hybrid (dense + BM25 + fusion)
- Hybrid + Reranker

Independently of retrieval-method comparisons, **chunking strategy
comparisons are also part of this framework**: the same query set and
retrieval configuration can be re-run against corpora chunked with
different strategies (fixed-size, recursive, structure-aware) and
parameters (size, overlap) to measure their effect on the retrieval
metrics above. Chunking strategy is already tracked per run — see
"Experiment tracking" below.

## Experiment tracking

Each evaluation run should record the configuration that produced its
results, so results are reproducible and comparable:

- Embedding model
- Chunking strategy and chunk size
- Retrieval method (dense / BM25 / hybrid / hybrid+rerank)
- Top-K
- Reranker (if used)
- LLM used for generation
- The resulting metric values

This maps to the `evaluation_runs` / `evaluation_results` entities in
[`docs/DATA_MODEL.md`](DATA_MODEL.md).

## Rule: never fabricate results

This is restated here deliberately, because evaluation is the area most
tempting to "fill in" with plausible-looking numbers:

- No retrieval or generation metric may be written into any document, PR
  description, or commit message unless it was actually computed by running
  the evaluation harness against real data in this repository.
- `eval/results/` (once it exists) is the only legitimate source of
  evaluation numbers referenced elsewhere in the docs.
- If asked to report evaluation results before the harness and dataset
  exist, the correct answer is "not yet measured," not an invented number.

## Related documents

- [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) — the pipeline being evaluated.
- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — `evaluation_runs`,
  `evaluation_results` entities (still PROPOSED — Issue #7).
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — `backend/app/evaluation/`
  module (metrics implemented, Issue #4) and `eval/` directory
  (`datasets/`/`scripts/`/`results/` — fixture hooks implemented,
  Issue #4; full experiment-tracking PLANNED, Issue #7).
- [`docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md`](DECISIONS/0007-local-providers-for-embedding-reranking-generation.md)
  — why the numbers above describe local/deterministic providers, not a
  commercial vendor.
