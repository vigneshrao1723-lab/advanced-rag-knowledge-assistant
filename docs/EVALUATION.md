# Evaluation

**Status:** IMPLEMENTED (experiment tracking + configuration comparison,
GitHub Issue #7, extending Issue #4 Slice 4.4's fixture-scale hooks).
`evaluation_runs`/`evaluation_results` are real, persisted Postgres
tables (migration `0008`), populated by an actually-executed run of
`eval/scripts/run_retrieval_evaluation.py` comparing **4 retrieval
methods** (dense-only, lexical-only, hybrid, hybrid+reranked) across
**3 chunking strategies** (structure-aware, fixed-size, recursive) —
see "Evaluation hooks" below for the real, reproducible numbers this
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
  one `EvaluationRun` + its `EvaluationResult` rows** (12 runs total: 3
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
- **`FixedSizeChunker`** (`backend/app/ingestion/chunking.py`, Issue
  #7): a naive, non-structure-aware baseline chunker (fixed-size
  character windows, no boundary preference) — exists purely as a
  second chunking strategy for this comparison; the real ingestion
  pipeline (`document_service.process_document()`) is unaffected and
  continues to use `StructureAwareChunker` exclusively.
- **`RecursiveChunker`** (`backend/app/ingestion/chunking.py`, Issue
  #41): a third comparison-only strategy using a fixed, universal,
  document-type-agnostic separator priority list (paragraph → line →
  sentence → word → hard character cut), unlike `StructureAwareChunker`
  which adapts its paragraph-detection heuristic per extractor. Like
  `FixedSizeChunker`, it exists for this comparison only — the real
  ingestion pipeline is unaffected. See that class's own docstring for
  the full distinction.
- **Real results from the run committed in `eval/results/retrieval_evaluation.json`**
  (top-K = 3, 6 documents, 7 queries), averaged across all 7 queries,
  for all three chunking strategies (identical across all three on this
  fixture — each fixture document is short enough to become exactly one
  chunk under any of the three chunkers, so chunking strategy has no
  differentiating effect at this fixture's scale; a real difference
  would only emerge on longer, multi-chunk documents — see "Larger fixture"
  below for the first such run):

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

## Larger fixture (pre-release audit, 2026-10-27)

The original fixture above has six documents that are each exactly one
chunk, so all three chunking strategies produce identical chunks and the
comparison cannot tell them apart. **That result must not be read as "the
strategies are equivalent."** A second, larger fixture was added to make
differences observable:
`eval/datasets/retrieval_fixture_large.py`, run with
`cd backend && uv run python ../eval/scripts/run_retrieval_evaluation.py --fixture large`,
writing `eval/results/retrieval_evaluation_large.json` (source of truth for
every number in this section; 12 more `evaluation_runs` persisted).

What it contains: 8 synthetic multi-section documents (24–27 chunks
depending on strategy; most documents are 2–4 chunks, so "long" is
relative), two near-duplicate **distractor** pairs (Borealis vs. Aldrin
runbooks, X200 vs. X100 manuals), and 19 queries — 6 direct, 4
distractor-sensitive, 3 multi-fact (answer needs two chunks), 3
**boundary-spanning**, and 3 **unanswerable**. Relevance is judged by
verbatim *evidence phrases* that must appear inside a retrieved chunk
(`evidence_coverage@3`, `app/evaluation/metrics.py`), so the same judgments
score every chunking strategy; a phrase a chunker cut in half counts as not
covered. `recall@3` over chunk IDs is deliberately not used here (overlap
duplicates would count as misses).

Real results (real Postgres 16 + pgvector, `local-hashing` embeddings,
`LexicalOverlapReranker`, `local-extractive` generation, `top_k=3`; no
external language model or embedding model was used anywhere):

| Chunking strategy (chunks) | Retrieval method | Evidence coverage@3 | Hit Rate@3 | MRR | nDCG@3 | Precision@3 |
|---|---|---|---|---|---|---|
| Structure-aware (24) | Dense only | 0.91 | 0.94 | 0.91 | 0.89 | 0.35 |
| Structure-aware (24) | Lexical only | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 |
| Structure-aware (24) | Hybrid (no rerank) | 0.91 | 0.94 | 0.91 | 0.89 | 0.35 |
| Structure-aware (24) | Hybrid + reranked | 0.97 | 1.00 | 1.00 | 0.97 | 0.38 |
| Fixed-size (27) | Dense only | 0.72 | 0.75 | 0.72 | 0.70 | 0.29 |
| Fixed-size (27) | Lexical only | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 |
| Fixed-size (27) | Hybrid (no rerank) | 0.72 | 0.75 | 0.72 | 0.70 | 0.29 |
| Fixed-size (27) | Hybrid + reranked | 0.78 | 0.81 | 0.81 | 0.78 | 0.31 |
| Recursive (24) | Dense only | 0.91 | 0.94 | 0.91 | 0.89 | 0.35 |
| Recursive (24) | Lexical only | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 |
| Recursive (24) | Hybrid (no rerank) | 0.91 | 0.94 | 0.91 | 0.89 | 0.35 |
| Recursive (24) | Hybrid + reranked | 0.97 | 1.00 | 1.00 | 0.97 | 0.38 |

Evidence coverage@3 by query category, hybrid + reranked:

| Chunking strategy | direct | distractor | multi_fact | boundary |
|---|---|---|---|---|
| Structure-aware | 1.00 | 1.00 | 0.83 | 1.00 |
| Fixed-size | 1.00 | 1.00 | 0.83 | 0.00 |
| Recursive | 1.00 | 1.00 | 0.83 | 1.00 |

How to read this honestly:

- **The whole structure-aware/recursive vs. fixed-size gap is the three
  boundary queries (coverage 0.00 vs. 1.00).** The fixture is *engineered*
  so each boundary sentence straddles `FixedSizeChunker`'s first window edge
  (`backend/tests/test_eval_large_fixture.py` asserts this, so the property
  cannot silently rot). The result demonstrates the mechanism — a chunker
  with no boundary preference can sever the answer — it is not a measurement
  of how often that happens on real documents. On all non-boundary
  categories the three strategies are identical.
- **Structure-aware and recursive remain indistinguishable** on this
  fixture (same 24 chunks' worth of evidence retrieved). Nothing here shows
  one is better than the other.
- **Lexical search returned zero chunks for 14 of the 16 answerable
  queries.** `lexical_search()` uses `plainto_tsquery`, which ANDs every
  non-stopword term, so one query word absent from a chunk (e.g. "many",
  "receive") yields no match. Consequently hybrid ≡ dense in every row
  above: with natural-language questions the lexical leg currently
  contributes nothing to the fusion. (On the small fixture lexical looked
  merely "weaker", 0.71; here it is close to non-functional.) A
  `websearch_to_tsquery`/OR-with-ranking change is a candidate improvement;
  it was not made in this audit.
- **The reranker helps modestly** (0.91 → 0.97 coverage, structure-aware),
  mostly by promoting the right near-duplicate when the query names the
  product (Jaccard overlap on tokens like "X200", "Borealis").
- **Multi-fact coverage is 0.83 (5 of 6 phrases) for all strategies**: the
  top-3 cannot always hold both required chunks.
- **Unanswerable queries are not refused.** For the 3 unanswerable queries,
  dense/hybrid/hybrid+reranked each still return 3 chunks (lexical returns
  0), and the production path (`hybrid_search()` defaults →
  `generate_answer()`) produced a normal "Based on the available
  documents" answer with **5 citations for 3 of 3** queries — never the
  fixed no-evidence answer. There is no relevance threshold anywhere in
  retrieval or generation; the no-evidence answer only occurs when the
  workspace has no READY chunks at all. With `local-hashing` embeddings the
  similarity of off-topic queries is driven by stopword overlap (measured:
  an off-topic "meaning of life" query scored 0.316, equal to the
  legitimate "mayor of Quenby" query), so no single similarity cutoff
  separates them; a content-word-overlap gate or a real embedding model
  plus a calibrated threshold would be needed. This is a documented
  limitation and an owner decision, not a fix made in this audit.
- **Groundedness/citation metrics are circular for this provider.**
  `is_extractive_answer_grounded` is `true` by construction for
  `LocalGroundedExtractiveProvider` (it only quotes evidence); it says
  nothing about a real language model, whose faithfulness, answer
  relevance, and prompt-injection resistance remain **unmeasured**.
  Prompt-injection behavior was tested only against the inert extractive
  provider (the injected text is quoted as evidence and nothing acts on it,
  verified live and in `backend/tests/test_prompt_injection.py`).

Everything above is a property of a ~19-query synthetic corpus and this
project's local deterministic providers. It is not evidence of quality on
real documents or with a real embedding model/LLM.

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
configuration is re-run against corpora chunked with three strategies —
`StructureAwareChunker` (the real pipeline's own chunker),
`FixedSizeChunker` (a naive baseline, Issue #7), and `RecursiveChunker`
(a fixed-separator-list baseline, Issue #41) — to measure their effect
on the retrieval metrics above. A chunk-size/overlap sweep is not
implemented — out of scope for this item; chunking strategy is tracked
per run — see "Experiment tracking" below.

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
