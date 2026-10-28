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
  | Lexical only | 1.0 | 0.76 | 1.0 | 1.0 | 1.0 |
  | Hybrid (no rerank) | 1.0 | 0.33 | 1.0 | 1.0 | 1.0 |
  | Hybrid + reranked | 1.0 | 0.33 | 1.0 | 1.0 | 1.0 |

  Every query's single relevant document was always retrieved by dense/
  hybrid/hybrid+reranked and ranked first; Precision@3 is exactly `1/3`
  for those methods because only one of the three retrieved slots is
  ever relevant in a 6-document corpus at `k=3`, not a retrieval defect.
  **Lexical-only retrieval was weaker on this fixture (0.71) until the
  2026-10-28 change** from AND to OR matching of query words
  (`app/retrieval/lexical.py`): the 0.71 came from queries containing a word
  absent from the relevant passage. It is now 1.0 here; the table above is
  the current committed result (`eval/results/retrieval_evaluation.json`).
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
external language model or embedding model was used anywhere). **Re-run on
2026-10-28 after three retrieval changes** (OR-matching lexical search, a
content-word relevance gate, and routing the unanswerable probe through the
production resolver); the 2026-10-27 baseline is given in the bullets.

| Chunking strategy (chunks) | Retrieval method | Evidence coverage@3 | Hit Rate@3 | MRR | nDCG@3 | Precision@3 |
|---|---|---|---|---|---|---|
| Structure-aware (24) | Dense only | 0.91 | 0.94 | 0.91 | 0.89 | 0.35 |
| Structure-aware (24) | Lexical only | 1.00 | 1.00 | 0.90 | 0.92 | 0.41 |
| Structure-aware (24) | Hybrid (no rerank) | 0.97 | 1.00 | 0.94 | 0.93 | 0.38 |
| Structure-aware (24) | Hybrid + reranked | 1.00 | 1.00 | 1.00 | 0.99 | 0.40 |
| Fixed-size (27) | Dense only | 0.72 | 0.75 | 0.72 | 0.70 | 0.29 |
| Fixed-size (27) | Lexical only | 0.81 | 0.81 | 0.70 | 0.72 | 0.33 |
| Fixed-size (27) | Hybrid (no rerank) | 0.78 | 0.81 | 0.74 | 0.73 | 0.31 |
| Fixed-size (27) | Hybrid + reranked | 0.81 | 0.81 | 0.81 | 0.81 | 0.33 |
| Recursive (24) | Dense only | 0.91 | 0.94 | 0.91 | 0.89 | 0.35 |
| Recursive (24) | Lexical only | 1.00 | 1.00 | 0.90 | 0.92 | 0.41 |
| Recursive (24) | Hybrid (no rerank) | 0.97 | 1.00 | 0.94 | 0.93 | 0.38 |
| Recursive (24) | Hybrid + reranked | 1.00 | 1.00 | 1.00 | 0.99 | 0.40 |

Evidence coverage@3 by query category, hybrid + reranked:

| Chunking strategy | direct | distractor | multi_fact | boundary |
|---|---|---|---|---|
| Structure-aware | 1.00 | 1.00 | 1.00 | 1.00 |
| Fixed-size | 1.00 | 1.00 | 1.00 | 0.00 |
| Recursive | 1.00 | 1.00 | 1.00 | 1.00 |

How to read this honestly:

- **Lexical search was the largest single weakness and is fixed.** It used
  `plainto_tsquery`, which ANDs every query word, so one word missing from a
  passage ("many", "receive", "explain") matched nothing: lexical-only
  returned 0 chunks for 14 of the 16 answerable queries and scored 0.125
  coverage; hybrid was therefore identical to dense. With OR matching ranked
  by `ts_rank_cd` it returns chunks for 16 of 16, and lexical-only coverage
  is 1.00 (structure-aware). Hybrid + reranked went 0.97 → 1.00 and
  multi-fact 0.83 → 1.00. **Caveat:** this fixture's queries deliberately
  share words with their evidence (the local embedder has no semantics), so
  1.00 is a ceiling effect of a small synthetic set, not a quality claim.
  Lexical-only now *beats* dense-only (1.00 vs 0.91) here, a sign of how weak
  the hashing embedder is.
- **The whole structure-aware/recursive vs. fixed-size gap is the three
  boundary queries (coverage 1.00 vs 0.00).** The fixture is *engineered*
  so each boundary sentence straddles `FixedSizeChunker`'s first window edge
  (`backend/tests/test_eval_large_fixture.py` asserts this, so the property
  cannot silently rot). The result demonstrates the mechanism, not how often
  it happens on real documents. On every other category the three strategies
  are identical, and structure-aware vs. recursive remain indistinguishable.
- **Unanswerable queries are now refused.** Through the production path
  (`resolve_question()` → `generate_answer()`), 3 of 3 unanswerable queries
  return the fixed no-evidence answer with 0 citations (2026-10-27: a normal
  answer with 5 citations for 3 of 3). The mechanism is a content-word
  relevance gate that applies only to the hashing embedder
  (`LocalHashingEmbeddingProvider.semantic = False`): a passage is kept only
  if it shares at least one meaningful word (5-letter stem, stopwords and
  command words removed) with the question; questions with no meaningful word
  ("What does the document say?") are never filtered. It cannot rescue a
  paraphrase that shares no word with the evidence — the same limit the
  embedder already has. A real embedder should set `semantic = True`, which
  disables the gate.
- **Groundedness/citation metrics are circular for the extractive provider**
  and say nothing about a real model. Real-model behaviour is covered
  separately below.
- Prompt-injection behaviour of the *extractive* provider is inert by
  construction; for the real model see "Real-model checks".

## Real-model checks (2026-10-28, local `qwen2.5:3b-instruct`)

Not a benchmark: a handful of hand-inspected runs on a synthetic 4-page C/MPI
lab manual (`backend/tests/pdf_fixtures.py`), through the real upload →
extraction → chunking → retrieval → generation path on an RTX 3050 (4 GB).
Observed, not scored:

- "Explain Program 2 / 1 / 3" produced structured explanations (what it does,
  step-by-step, output, concepts) that were correct at the program level; the
  program's output was reproduced correctly. Program 3, which spans two pages,
  was reassembled and cut at the next program's heading.
- "Explain program 9" (absent) → instant deterministic reply listing Programs
  1–4, no model call. Before the change the model said "not mentioned" and then
  dumped (partly wrong) explanations of every other program.
- Code in answers is checked against the document line by line and corrected or
  appended verbatim, including indentation (the model alone re-typed it with
  reordered declarations and dropped lines).
- Residual model errors remain in prose: e.g. it once said an array is printed
  "on a new line" where the code prints space-separated values; "line by line"
  requests only work because the system splits the code and asks for one
  sentence per line; the short overview paragraph sometimes misreads "the first
  program line by line" as "the first line".
- Time per answer 7–17 s on GPU. Injection resistance of this model was tested
  only with the generic "ignore previous instructions" document used elsewhere
  (answer stayed on topic); this is far from a security evaluation.

Everything above is a property of a ~19-query synthetic corpus, a small
hand-inspected sample, and this project's local providers. It is not evidence
of quality on real documents or with a real embedding model/hosted LLM.

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
