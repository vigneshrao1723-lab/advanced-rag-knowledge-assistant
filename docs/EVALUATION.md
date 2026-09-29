# Evaluation

**Status:** IMPLEMENTED (experiment tracking + configuration comparison,
GitHub Issue #7, extending Issue #4 Slice 4.4's fixture-scale hooks).
`evaluation_runs`/`evaluation_results` are real, persisted Postgres
tables (migration `0008`), populated by an actually-executed run of
`eval/scripts/run_retrieval_evaluation.py` comparing **4 retrieval
methods** (dense-only, lexical-only, hybrid, hybrid+reranked) across
**2 chunking strategies** (structure-aware, fixed-size) — see
"Evaluation hooks" below for the real, reproducible numbers this
produced. No number in this document was fabricated — see "Rule: never
fabricate results" below.

## Purpose

Retrieval and generation quality must be measurable, not asserted. This
document defines the metrics and comparisons the system is designed to
support once an ingestion + retrieval + generation pipeline actually exists
to evaluate.

## Evaluation hooks (GitHub Issue #4, Slice 4.4; extended by Issue #7)

**Proves the pipeline is measurable, and now persists real, comparable
experiment history via `evaluation_runs`/`evaluation_results`.**

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
  ingests the fixture set through the real pipeline (cleaning, then
  chunking — once per chunking strategy compared — embedding, the same
  modules `process_document()` itself uses), then for each of the 4
  retrieval methods (dense-only, lexical-only, hybrid, hybrid+reranked
  — reconstructed from `dense_search()`/`lexical_search()`/
  `reciprocal_rank_fusion()`/the reranker directly, without changing
  `hybrid_search()` itself) computes the metrics above and **persists
  one `EvaluationRun` + its `EvaluationResult` rows** (8 runs total: 2
  chunking strategies × 4 retrieval methods). Also runs
  `generate_answer()` for two representative queries (against the
  hybrid+reranked configuration only) and computes the citation checks.
  Writes `eval/results/retrieval_evaluation.json`. Uses one dedicated,
  throwaway workspace per chunking strategy, deleted at the end of every
  run (verified via a direct query showing zero leftover rows) —
  `evaluation_runs.workspace_id` uses `ON DELETE SET NULL` specifically
  so the persisted run/result rows survive that cleanup (see
  `backend/app/models/evaluation_run.py`). Safely re-runnable, confirmed
  deterministic across repeated runs (identical metric output twice in a
  row; each run appends new `evaluation_runs` rows, by design, so
  history accumulates). Run it yourself: `cd backend && uv run python
  ../eval/scripts/run_retrieval_evaluation.py`.
- **`FixedSizeChunker`** (`backend/app/ingestion/chunking.py`, new,
  Issue #7): a naive, non-structure-aware baseline chunker (fixed-size
  character windows, no boundary preference) — exists purely as the
  second chunking strategy this comparison needs; the real ingestion
  pipeline (`document_service.process_document()`) is unaffected and
  continues to use `StructureAwareChunker` exclusively.
- **Real results from the run committed in `eval/results/retrieval_evaluation.json`**
  (top-K = 3, 6 documents, 7 queries), averaged across all 7 queries,
  for both chunking strategies (identical between the two on this
  fixture — each fixture document is short enough to become exactly one
  chunk under either chunker, so chunking strategy has no
  differentiating effect at this fixture's scale; a real difference
  would only emerge on longer, multi-chunk documents):

  | Retrieval method | Recall@3 | Precision@3 | MRR | nDCG@3 | Hit Rate@3 |
  |---|---|---|---|---|---|
  | Dense only | 1.0 | 0.33 | 1.0 | 1.0 | 1.0 |
  | Lexical only | 0.71 | 0.71 | 0.71 | 0.71 | 0.71 |
  | Hybrid (no rerank) | 1.0 | 0.33 | 1.0 | 1.0 | 1.0 |
  | Hybrid + reranked | 1.0 | 0.33 | 1.0 | 1.0 | 1.0 |

  Every query's single relevant document was always retrieved by dense/
  hybrid/hybrid+reranked and ranked first; Precision@3 is exactly `1/3`
  for those methods because only one of the three retrieved slots is
  ever relevant in a 6-document corpus at `k=3`, not a retrieval defect.
  **Lexical-only retrieval is genuinely weaker on this fixture** (0.71
  vs. 1.0) — a real, honest finding from this run, not adjusted or
  hidden: Postgres full-text search's `ts_rank_cd` did not always rank
  the single relevant (keyword-overlapping) document first among this
  small corpus, where the (deterministic, hashed) dense embeddings did.
  Generation checks on 2 sample queries: citation completeness/
  correctness both `1.0`, and `is_extractive_answer_grounded` `true` for
  both — expected, since `LocalGroundedExtractiveProvider` only ever
  quotes retrieved evidence by construction (see
  `app/generation/llm_provider.py`). **These numbers describe this
  specific fixture set and this project's current local/deterministic
  providers ([ADR 0007](DECISIONS/0007-local-providers-for-embedding-reranking-generation.md))
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

**Implemented (Issue #7)** — the evaluation harness compares, on the
same query set, in one run:

- Dense retrieval only
- Lexical (Postgres full-text search) only
- Hybrid (dense + lexical + RRF fusion)
- Hybrid + Reranker

Independently of retrieval-method comparisons, **chunking strategy
comparisons are also implemented**: the same query set and retrieval
configuration is re-run against corpora chunked with two strategies —
`StructureAwareChunker` (the real pipeline's own chunker) and
`FixedSizeChunker` (a naive baseline, Issue #7) — to measure their
effect on the retrieval metrics above. A `recursive` strategy or
size/overlap sweep is not implemented — the Definition of Done's "at
least two chunking strategies" is met by these two; see
`backend/app/ingestion/chunking.py`'s own docstring for why a third
strategy wasn't added (matches this project's established "one real
implementation, `ChunkingStrategy`/`Protocol`-ready for more" pattern
already used for `EmbeddingProvider`/`Reranker`/`LLMProvider`).
Chunking strategy is tracked per run — see "Experiment tracking" below.

## Experiment tracking

**Implemented (Issue #7)** — `evaluation_runs`/`evaluation_results`
(migration `0008`, `backend/app/models/evaluation_run.py`/
`evaluation_result.py`) record the configuration that produced each
run's results, so results are reproducible and comparable over time:

- Embedding model
- Chunking strategy and chunk size/overlap
- Retrieval method (dense / lexical / hybrid / hybrid+reranked)
- Top-K
- Reranker (if used)
- LLM used for generation
- Document/query count
- The resulting metric values (`evaluation_results`, one row per metric
  per run)

`evaluation_runs.workspace_id` is nullable (`ON DELETE SET NULL`): an
evaluation run must outlive the (often throwaway) workspace it was
computed against — see the model's own docstring. This maps to the
`evaluation_runs` / `evaluation_results` entities in
[`docs/DATA_MODEL.md`](DATA_MODEL.md), now IMPLEMENTED there too.

## Observability (GitHub Issue #7)

**Implemented** — per docs/RAG_DESIGN.md's "Observability" section,
per-stage latency and a token-usage analog are tracked as structured
JSON log records (`app/observability/logging.py`'s existing convention
— not new database columns, since this is debugging/telemetry detail,
distinct from the durably-persisted `evaluation_runs`/`retrieval_events`
history above):

- `app/retrieval/service.py::hybrid_search()` logs
  `retrieval_stage_latencies` — `embed_ms`/`dense_ms`/`lexical_ms`/
  `rerank_ms`/`total_ms` plus candidate counts per stage. The existing
  `RetrievalEvent.latency_ms` column (end-to-end, Issue #4) is
  unchanged.
- `app/generation/service.py::generate_answer()` logs
  `generation_stage_latencies` — `context_build_ms`/`generation_ms`,
  plus `context_chars`/`answer_chars` as a **character-count proxy for
  token usage**: the shipped `LocalGroundedExtractiveProvider` is
  deterministic and non-tokenizing ([ADR 0007](DECISIONS/0007-local-providers-for-embedding-reranking-generation.md)),
  so character counts are the closest honest analog available today,
  not a claim of real token accounting — a future tokenizing provider
  can report real token counts through the same log field names.
- Tested via `caplog` (`backend/tests/test_retrieval.py`,
  `test_generation.py`) — confirms the telemetry actually records data
  for a real pipeline run, not just that logging code doesn't crash.
- **A genuine bug found and fixed while writing these tests**:
  `alembic/env.py`'s `fileConfig()` call used its default
  `disable_existing_loggers=True`, which silently disabled every
  `app.*` logger not explicitly listed in `alembic.ini` for the rest of
  a pytest session once migrations ran — invisible in production (where
  Alembic runs as a separate one-shot process) but would have silently
  swallowed all future `app.*` structured logging in tests. Fixed by
  passing `disable_existing_loggers=False`. See `SOLVING.md`.

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

- [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) — the pipeline being evaluated,
  and its "Observability" section.
- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — `evaluation_runs`,
  `evaluation_results` entities (IMPLEMENTED, migration `0008`).
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — `backend/app/evaluation/`
  module (metrics implemented, Issue #4) and `eval/` directory
  (`datasets/`/`scripts/`/`results/` — fixture hooks + full experiment
  tracking + configuration comparison, Issues #4/#7).
- [`docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md`](DECISIONS/0007-local-providers-for-embedding-reranking-generation.md)
  — why the numbers above describe local/deterministic providers, not a
  commercial vendor.
- [`docs/SECURITY.md`](SECURITY.md) — audit logging and security testing
  this evaluation/observability work extends (Issue #7).
