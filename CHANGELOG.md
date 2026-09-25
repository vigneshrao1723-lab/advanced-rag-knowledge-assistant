# CHANGELOG.md

All notable changes to this project are recorded here, in chronological
order. Entries under **[Unreleased — working tree]** describe changes made
locally that have **not yet been committed** (see `git status`) — logged
honestly as such, not backdated to look committed. Entries under
**[Unreleased — committed]** are real commits, referenced by hash, that
haven't been part of a tagged release yet. This file is never backfilled
with invented history of either kind.

## [Unreleased — working tree]

### 2026-09-25 — Issue #5, Slice 5.1 follow-up: browser E2E coverage for the document-upload/chat flow

*(Small follow-up on top of the merged Slice 5.1 (`2ad720f`, PR #29) —
no application code changed, only a new Playwright spec and this
documentation reconciliation.)*

- Adds `frontend/e2e/documents-chat.spec.ts`: a browser-level smoke test
  for Issue #5's primary flow — register → create workspace → upload a
  real `.txt` document → poll for `READY` → open Chat → ask a question →
  a real grounded answer appears with its citation's filename visible.
  Run against a freshly rebuilt real Docker stack (backend + frontend
  images rebuilt from the merged Slice 5.1 code, real
  PostgreSQL/Redis/Mailpit) — no mocks, matching this project's
  established Playwright precedent (`auth.spec.ts`,
  `password-recovery.spec.ts`).
- **Full Playwright suite: 20/20 passing** (19 pre-existing +
  this 1 new one), confirmed with a full clean run.
- No new migration, no new dependency, no application code changed.
- Docs updated in the same working tree: `PROJECT_STATE.md`,
  `HANDOFF.md`, `docs/DEPLOYMENT.md` (also corrects several other
  sections left stale from Slice 4.4/5.1's pre-merge state).

## [Unreleased — committed]

### 2026-09-25 — `feat: document list/get endpoints + real Documents/Chat pages (Issue #5, Slice 5.1)` (#29), merged as `2ad720f`

*(Branch `issue-5-slice-5-1-documents-conversations-api`, cut from the
merged Slice 4.4 (`fd2041c`, PR #28). Opened as **PR #29**, verified
green on GitHub Actions CI, and **merged into `main` as squash commit
`2ad720f`**.)*

- Adds `GET /api/v1/workspaces/{workspace_id}/documents` (list,
  newest-first) and `GET .../documents/{document_id}` (single document/
  status) — both VIEWER-role, workspace-scoped at the query level. Closes
  a real gap found during this slice's frontend inspection: only `POST`
  upload/process existed before, so a real frontend had no way to list
  documents or poll processing status.
- Adds `GET /api/v1/workspaces/{workspace_id}/conversations` (list,
  newest-updated-first, VIEWER-role).
- **Fixes a real bug**: `GET .../conversations/{id}/messages` always
  returned `citations=[]` for every message, even though
  `POST .../messages` had already persisted real `Citation` rows —
  reloading a conversation's history silently dropped its citations.
  Fixed via a new bulk `citation_repository.list_for_messages()` lookup.
  Regression-tested.
- Adds `frontend/app/documents/page.tsx` (replaces the `PageStub`): a
  real upload form, workspace-scoped document list with live status
  badges, 3-second polling while any document is mid-pipeline, and a
  retry action for `FAILED` documents.
- Adds `frontend/app/chat/page.tsx` (new): a real conversation list +
  "New conversation," a message thread with an input box, and citations
  rendered under each assistant message (resolved against the
  workspace's document list for a filename/page/section label).
- Both new pages consume the real backend APIs above through new
  `lib/api-client.ts` functions and `lib/schemas.ts` Zod schemas — no
  mock or disconnected data.
- 9 new backend tests (`backend/tests/test_document_listing.py`,
  `test_conversations.py`) — **678/678 backend tests passing**. 10 new
  frontend tests (`app/documents/page.test.tsx`, `app/chat/page.test.tsx`)
  — **58/58 frontend tests passing**. `ruff`/`mypy`/`eslint`/
  `tsc --noEmit` clean, `next build` succeeds.
- No new migration, no new dependency.
- Docs updated in the same commit: `PROJECT_STATE.md`, `HANDOFF.md`.

### 2026-09-25 — `feat: add evaluation hooks and prompt-injection corpus (Issue #4, Slice 4.4)` (#28), merged as `fd2041c`

*(Branch `issue-4-slice-4-4-evaluation-security`, cut from the merged
Slice 4.3 (`54b08b2`, PR #27). Opened as **PR #28**, verified green on
GitHub Actions CI, and **merged into `main` as squash commit
`fd2041c`**. **Completes GitHub Issue #4's explicit deliverables/
Definition-of-Done — GitHub Issue #4 (Hybrid RAG Pipeline) is
functionally complete.**)*

- Adds `backend/app/evaluation/metrics.py`: pure functions for every
  `docs/EVALUATION.md` retrieval metric (`recall_at_k`, `precision_at_k`,
  `mrr`, `ndcg_at_k`, `hit_rate_at_k`, binary relevance) plus real,
  mechanically-checkable generation/citation checks
  (`citation_completeness`, `citation_correctness`,
  `is_extractive_answer_grounded`) — deliberately does not fabricate a
  numeric "faithfulness"/"answer relevance" score, which would need a
  human rater or an LLM-as-judge this project doesn't have.
- **A genuine bug found and fixed while writing the metric tests**:
  `recall_at_k()`/`ndcg_at_k()` could exceed the mathematically-required
  `[0, 1]` bound when a relevant item appeared more than once in the
  retrieved list — fixed to count each distinct relevant item once, at
  its best rank, matching `mrr()`'s own existing semantics. See
  `SOLVING.md`.
- Adds `eval/datasets/retrieval_fixture.py` (6 documents, 7 queries,
  known relevance) and `eval/scripts/run_retrieval_evaluation.py` (a
  runnable harness — ingests the fixtures through the real pipeline,
  runs `hybrid_search()`/`generate_answer()`, computes the metrics
  above, writes `eval/results/retrieval_evaluation.json`, cleans up its
  own throwaway workspace). **Actually run twice, deterministically** —
  real, committed results: Recall@3 = 1.0, Precision@3 = 0.33, MRR = 1.0,
  nDCG@3 = 1.0, Hit Rate@3 = 1.0; citation completeness/correctness both
  1.0 and `is_extractive_answer_grounded` true on 2 sample generation
  queries.
- Adds `backend/tests/test_prompt_injection.py` (29 tests): a
  12-payload corpus (ignore-previous-instructions, fake system message,
  system-prompt/secret exfiltration, documentation-disguised
  instructions, indirect/quoted injection, query-conflicting
  instructions, policy-override claims, a roleplay jailbreak, a
  tool/filesystem-access-expansion request, cross-workspace
  exfiltration, a spoofed context-boundary marker), tested at both the
  provider level (every payload) and the full HTTP pipeline (four
  representative payloads ingested as a real document's entire
  content).
- Fixes a genuine, if minor, test-quality issue: `tests/conftest.py`'s
  fallback `SECRET_KEY` was 31 bytes (one short of PyJWT's HS256
  minimum), silently triggering `InsecureKeyLengthWarning` on 624 of
  the suite's warnings — not a production config issue; fixed by
  lengthening the test-only value. Warning count dropped to 8 (all
  pre-existing, unrelated). See `SOLVING.md`.
- No new migration, no new dependency.
- `ruff`/`mypy` clean (136 source files). Complete backend suite:
  **669/669 passing** (598 pre-existing + 71 new), 3 consecutive runs.
- Docs updated in the same commit: `PROJECT_STATE.md`,
  `HANDOFF.md`, `docs/EVALUATION.md` (new "Evaluation hooks" section
  with the real results), `docs/ARCHITECTURE.md` (`evaluation/` module +
  `eval/` directory status), `docs/SECURITY.md` (expanded "Prompt
  injection defense" section), `SOLVING.md` (two entries).

### 2026-09-25 — `feat: add generation module and conversations ask-flow (Issue #4, Slice 4.3)` (`f7a67ee`, docs `8e9631d`), merged as `54b08b2`

*(Branch `issue-4-slice-4-3-generation`, cut from the merged Slice 4.2
(`378fec4`, PR #26). Opened as **PR #27**, verified green on GitHub
Actions CI, and **merged into `main` as squash commit `54b08b2`**.
First slice where a real question against real ingested documents
returns a real grounded answer with citations end-to-end — Issue #4's
primary Definition-of-Done item.)*

- Adds `backend/app/generation/`: `context_builder.py`'s
  `build_context()` (packs ranked evidence into a `[n]`-citation-marked
  string, exact-content dedup, character budget with first-block-always-
  included truncation), `llm_provider.py`'s `LLMProvider` protocol +
  `LocalGroundedExtractiveProvider` (deterministic, offline — returns
  the provided evidence verbatim rather than paraphrasing it, grounded
  and prompt-injection-immune *by construction*), `service.py`'s
  `generate_answer()` (a fixed system prompt framing the evidence
  section as untrusted data, structurally separate from `context`/
  `query`), and `citation_engine.py`'s `create_citations()`.
- Adds `backend/app/repositories/{citation,conversation,message}_repository.py`
  and `backend/app/services/conversation_service.py`: `create_conversation()`,
  `post_message()` (persists the user message, runs retrieval +
  generation off the event loop via `asyncio.to_thread()`, persists the
  assistant message + citations atomically), `list_messages()`.
- Adds `POST /api/v1/workspaces/{workspace_id}/conversations` (MEMBER),
  `POST .../conversations/{conversation_id}/messages` (MEMBER,
  rate-limited via a new `conversation_message` Tier A dimension),
  `GET .../conversations/{conversation_id}/messages` (VIEWER).
- No evidence found → a fixed, honest "I don't have enough information"
  answer with zero citations, never a fabricated one.
- No new migration (reuses Slice 4.1's schema unchanged); no new
  dependency.
- Adds [ADR 0007](docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md):
  records the deliberate decision that `EmbeddingProvider`/`Reranker`/
  `LLMProvider` all use local, deterministic implementations with no
  commercial vendor selected yet, satisfying Issue #4's Definition-of-
  Done requirement for a vendor ADR. Also fixes the stale
  `docs/DECISIONS/README.md` ADR index (was missing 0004–0006).
- `backend/tests/test_generation.py` (new, 13 unit tests) and
  `backend/tests/test_conversations.py` (new, 12 HTTP-level tests, real
  Postgres/Redis/filesystem, no mocks, exercising the complete Issue #3
  ingestion pipeline before asking a question): a real grounded answer
  with real citations against real ingested content; no-evidence
  handling; conversation-not-found `404`; message ordering; VIEWER-can-
  list-not-post; cross-workspace conversation `404`; a dedicated
  cross-workspace-content-leakage test; a dedicated prompt-injection
  test (a document whose entire content is an injection attempt still
  produces a normal, well-formed response); rate-limit enforcement;
  empty-content validation.
- `ruff`/`mypy` clean (133 source files). Complete backend suite:
  **598/598 passing** (573 pre-existing + 25 new), 3 consecutive runs.
- Docs updated in the same working tree: `PROJECT_STATE.md`,
  `HANDOFF.md`, `docs/API_CONTRACT.md` (new "Implemented: conversations"
  section), `docs/RAG_DESIGN.md`, `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/DECISIONS/README.md`.
- **Explicitly deferred to a later issue**: conversational context/query
  rewriting (Issue #5).

### 2026-09-25 — `feat: add retrieval module (Issue #4, Slice 4.2)` (`820c145`, docs `6ec291c`), merged as `378fec4`

*(Branch `issue-4-slice-4-2-retrieval`, cut from the merged Slice 4.1
(`5e4a626`, PR #25). Opened as **PR #26**, verified green on GitHub
Actions CI, and **merged into `main` as squash commit `378fec4`**.)*

- Adds `backend/app/retrieval/`: `dense_search()` (pgvector
  `cosine_distance()`, backed by the existing HNSW index),
  `lexical_search()` (Postgres full-text search —
  `to_tsvector`/`plainto_tsquery`/`ts_rank_cd`, backed by a new GIN
  functional index, migration `0007` — no second search engine, per
  ADR 0002's own stated consequence), `reciprocal_rank_fusion()`
  (standard RRF, `k=60`), a `Reranker` protocol + `LexicalOverlapReranker`
  (deterministic, offline Jaccard token-overlap scoring — no paid API
  required, matching `EmbeddingProvider`'s own precedent), and
  `hybrid_search()` (the single orchestrating entry point: embed query
  → dense + lexical → RRF → rerank → optionally record a
  `RetrievalEvent`).
- Every query is workspace-scoped at the SQL level (`WHERE workspace_id
  = ...`, never filtered after the fact) and requires the owning
  document be `READY`, so a document still mid-ingestion never surfaces
  partial/inconsistent results. `document_id` metadata filtering is
  supported; collection-based filtering deferred until `collections`
  exists.
- Query rewriting is deliberately not implemented here — a meaningful
  rewrite needs conversation history that doesn't exist until a later
  conversation-aware caller has it; `hybrid_search()` accepts an
  optional already-computed `rewritten_query_text` and always records
  both it and the original `query_text` distinctly, per
  `docs/REQUIREMENTS.md` "Query handling."
- Verified migration `0007` reversible directly against the real
  database.
- `backend/tests/test_retrieval.py` (new, 23 tests, real Postgres, no
  mocks): dense/lexical search correctness (similarity ranking,
  no-embedding/non-`READY`/workspace/`document_id` exclusions), RRF
  (multi-list ranking, dedup, empty input), the reranker (exact-match
  ranking, empty-query no-op, never drops/adds candidates), and
  `hybrid_search()` end-to-end (results + a matching `RetrievalEvent`
  row, `record_event=False`, workspace isolation, `document_id` filter,
  original-query preservation, conversation/message linkage). One
  genuine test-design bug (not a retrieval-code defect) found and fixed
  during validation: a coincidental score tie caused by stopword
  overlap between a test's query and its "unrelated" comparison
  sentence, against `LocalHashingEmbeddingProvider`'s un-weighted
  (no-IDF) hashing scheme — fixed by choosing zero-overlap comparison
  content (see `HANDOFF.md` for the full root-cause).
- `ruff`/`mypy` clean (121 source files). Complete backend suite:
  **573/573 passing** (550 pre-existing + 23 new), 3 consecutive runs.
  No new dependency.
- Docs updated in the same working tree: `PROJECT_STATE.md`,
  `HANDOFF.md`, `docs/RAG_DESIGN.md`, `docs/ARCHITECTURE.md`,
  `docs/SECURITY.md` (new "Retrieval workspace isolation" section). No
  new ADR — the RRF-constant/HNSW-reuse/GIN-index choices are direct
  applications of already-documented architecture, not new decisions;
  a real reranker/LLM vendor selection (if one is ever added) is the
  kind of choice that would warrant one, per the Issue #4 GitHub
  issue's own Definition of Done.

### 2026-09-25 — `feat: add conversation/message/citation/retrieval-event schema (Issue #4, Slice 4.1)` (`035f1b6`, docs `b9878f0`), merged as `5e4a626`

*(Branch `issue-4-slice-4-1-conversation-schema`, cut from the merged
Slice 3.7 (`7241ec8`, PR #24). Opened as **PR #25**, verified green on
GitHub Actions CI, and **merged into `main` as squash commit
`5e4a626`**.)*

- Adds migration `0006`: `conversations`, `messages`, `citations`,
  `retrieval_events` tables — the minimal persistence shape Issue #4
  needs to eventually write a retrieval/generation result somewhere.
  Schema only; no service/API code reads or writes these tables yet.
- `message_role` is a native Postgres enum (`USER`/`ASSISTANT`),
  matching `workspace_role`'s existing convention.
- `workspace_id` is denormalized onto `messages`/`citations`/
  `retrieval_events` (matching `document_chunks.workspace_id`'s own
  precedent) so every workspace-scoped query can filter without an
  extra join.
- `citations` denormalizes `document_id`/`page`/`section` from the
  cited chunk at write time, so a citation answers "which document/
  page/section" directly without a join; `ON DELETE CASCADE` from both
  `messages` and `document_chunks`.
- `retrieval_events.conversation_id`/`message_id` use `ON DELETE SET
  NULL` (matching `audit_logs`' own precedent — an observability record
  should outlive what it describes); `query_text` (the original user
  query) is a separate column from `rewritten_query_text`, so the
  original is always preserved per `docs/REQUIREMENTS.md` "Query
  handling"; `results` is `JSONB` (matching `audit_logs.event_metadata`'s
  existing precedent).
- Verified reversible directly against the real database (`alembic
  downgrade`/`upgrade` round-tripped, all four tables confirmed removed
  then recreated via direct schema inspection).
- `backend/tests/test_conversation_schema.py` (new, 23 tests, mirrors
  `tests/test_document_schema.py`'s own structure): table existence, FK
  validity/rejection, cascade-delete chains, `ON DELETE SET NULL`
  behavior, enum persistence, `JSONB` round-trip, nullable defaults,
  database-assigned timestamps — real Postgres, no mocks.
- `ruff`/`mypy` clean (112 source files). Complete backend suite:
  **550/550 passing** (527 pre-existing + 23 new), 3 consecutive runs.
  No new dependency.
- Docs updated in the same working tree: `PROJECT_STATE.md`,
  `HANDOFF.md`, `docs/DATA_MODEL.md`. No new ADR — this schema is a
  direct application of already-documented requirements
  (`docs/REQUIREMENTS.md` "Chat"/"Citations"/"Observability"), not a
  new architectural decision.

### 2026-09-24 — `feat: add embedding generation and vector indexing (Issue #3, Slice 3.7)` (`a576527`, docs `8e93c4c`), merged as `7241ec8`

*(Branch `issue-3-slice-3-7-embeddings-indexing`, cut from the merged
Slice 3.6 (`aa68079`, PR #23). Opened as **PR #24**, verified green on
GitHub Actions CI, and **merged into `main` as squash commit
`7241ec8`**. Completes GitHub Issue #3's full documented ingestion
lifecycle, `UPLOADED → ... → READY`.)*

- Extends `process_document()` (`app/services/document_service.py`)
  past `CHUNKED` through `EMBEDDED`/`INDEXED` to `READY`. No new
  endpoint — reuses the existing `document_process` rate-limit
  dimension and MEMBER-role authorization unchanged.
- Adds `backend/app/ingestion/embedding.py`: an `EmbeddingProvider`
  protocol (`model_name`/`model_version`/`dimension`/`embed_batch()`)
  plus one concrete implementation, `LocalHashingEmbeddingProvider` — a
  deterministic, offline, dependency-free 384-dimension hashed-bag-of-
  words embedding (L2-normalized), no API key or network call, so the
  whole pipeline is testable/demoable without a paid external provider.
  `embed_with_retry()` retries a transient provider failure
  (`EmbeddingTransientError`) with exponential backoff before giving
  up.
- Adds migration `0005`: `document_chunks.embedding` (`pgvector`
  `Vector(384)`, nullable), `embedding_model`/`embedding_dimension`
  (per-row provenance), and an HNSW index (`vector_cosine_ops`) —
  chosen over IVFFlat since it needs no separate training/list-count
  step. Verified reversible directly against the real database
  (`alembic downgrade`/`upgrade` round-tripped, index confirmed present
  via `pg_indexes` after re-upgrade).
- **Resumability**: a document at `CHUNKED`/`EMBEDDED`/`INDEXED`
  (interrupted mid-pipeline) skips extraction/cleaning/chunking
  entirely — its `document_chunks` rows already exist as real durable
  state — and re-embeds from the already-persisted chunks. Only `READY`
  is now terminal (`409`).
- **A document with zero extractable text** (chunking legitimately
  produces zero chunks — an empty file, or e.g. a scanned, text-layer-
  less PDF) fails explicitly with a clear reason, rather than silently
  reaching `READY` with nothing to retrieve.
- Adds two `AuditEvent` constants: `DOCUMENT_EMBEDDING_FAILED`,
  `DOCUMENT_READY`. Deliberately no `DOCUMENT_INDEXED` event — indexing
  performs no distinct work (pgvector's HNSW index is maintained
  transactionally by the same commit that writes each embedding
  vector).
- `backend/tests/test_embedding.py` (new, 14 unit tests) and 6 new
  HTTP-level tests added to `backend/tests/test_document_lifecycle.py`
  (embedding-failure handling, zero-content failure, `DOCUMENT_READY`
  audit event, resume-from-`CHUNKED` proven to skip re-chunking,
  resume-from-`EMBEDDED`, `READY`-rejection) plus 3 existing tests
  extended with embedding-shape assertions. 3 pre-existing tests in
  `tests/test_document_processing.py` updated from asserting `CHUNKED`
  to `READY` — an intended consequence of this slice, not a regression.
  A shared PDF test fixture across both files was replaced with a
  hand-built one containing genuinely extractable text, after the new
  zero-chunk safety check correctly caught the old contentless-blank-
  page fixture (see `SOLVING.md`).
- `ruff`/`mypy` clean (106 source files). Complete backend suite:
  **527/527 passing** (507 pre-existing + 20 new), 3 consecutive runs.
  No new dependency (`pgvector` already present since Slice 3.1).
- Docs updated in the same working tree: `PROJECT_STATE.md`,
  `HANDOFF.md`, `docs/DATA_MODEL.md`, `docs/API_CONTRACT.md`,
  `docs/RAG_DESIGN.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`,
  `SOLVING.md`. No new ADR — the HNSW-vs-IVFFlat choice and dimension
  rationale are recorded directly in the migration/model docstrings and
  `docs/DATA_MODEL.md`, a direct, narrow application of already-
  documented architecture (ADR 0002), not a new decision.

### 2026-09-24 — `feat: add processing lifecycle (Issue #3, Slice 3.6)` (`8f0af7c`, docs `2998909`), merged as `aa68079`

*(Branch `issue-3-slice-3-6-ingestion-lifecycle`, cut from the merged
Slice 3.5 (`237be97`, PR #22). Opened as **PR #23**, verified green on
GitHub Actions CI, and **merged into `main` as squash commit
`aa68079`**.)*

- Extends the existing `POST
  .../documents/{document_id}/process` endpoint
  (`app/services/document_service.py::process_document`) past `PARSED`
  through a new cleaning stage to `CLEANED`, then through
  `StructureAwareChunker` (Slice 3.5) to persisted `document_chunks`
  rows and `CHUNKED`. No new endpoint, no new migration — reuses the
  existing `document_process` rate-limit dimension and MEMBER-role
  authorization unchanged.
- Adds `backend/app/ingestion/cleaning.py`: a pure
  `ExtractedDocument -> ExtractedDocument` transformation —
  deterministic, conservative, loss-minimizing normalization only
  (CRLF/CR → LF, trailing-whitespace strip, excess-blank-line collapse
  to exactly one, never to zero). Never rewrites, summarizes, or removes
  semantic content, punctuation, or Unicode. No third-party dependency —
  stdlib `re` only.
- Adds `backend/app/repositories/document_chunk_repository.py`
  (`bulk_create()`/`get_by_document()`, same add/flush/no-commit
  convention as every other repository) and two new
  `document_repository.py` functions, `mark_cleaned()`/`mark_chunked()`.
- Adds three `AuditEvent` constants: `DOCUMENT_CLEANING_FAILED`,
  `DOCUMENT_CHUNKED`, `DOCUMENT_CHUNKING_FAILED`. Deliberately no
  `DOCUMENT_CLEANED` success event, to avoid audit noise for an
  internal, always-conservative stage.
- **Transaction strategy**: each stage's success commits as its own
  transaction before the next, more expensive stage begins
  (`PROCESSING` → commit → extraction → `PARSED` → commit → cleaning →
  `CLEANED` → commit → chunking → chunk rows + `CHUNKED` committed
  atomically together). Cleaning and chunking both run via
  `asyncio.to_thread()`, matching Slice 3.4's own established pattern
  for extraction, so neither blocks the single event loop for other
  concurrent requests.
- **Concurrency**: a genuine race between two concurrent `/process`
  calls reaching the chunk-insert step simultaneously is caught via
  `document_chunks`' own `UniqueConstraint(document_id, chunk_index)` —
  `IntegrityError` is caught, rolled back, and the document is
  re-fetched so the response reflects the actual persisted state rather
  than erroring, reusing the same pattern already established for the
  upload flow's own duplicate-checksum race.
- **Resumability**: a document at `PARSED` or `CLEANED` (interrupted
  mid-pipeline) is resumed, not rejected — only `CHUNKED` and later are
  terminal (`409`). No extracted/cleaned text is persisted between
  requests, so resuming re-runs the already-passed, pure/deterministic
  stages rather than skipping them — a deliberate simplification to
  avoid new content-persistence infrastructure.
- **`document_processing_jobs`** (the "potential entity"
  `docs/DATA_MODEL.md` names) evaluated and confirmed not needed: the
  existing `documents.status` field plus the client-triggered
  `/process` endpoint's own resumability is sufficient for this
  project's synchronous, single-process architecture. No new ADR — a
  direct application of already-documented architecture, not a new
  decision.
- `backend/tests/test_cleaning.py` (new, 17 unit tests) and
  `backend/tests/test_document_lifecycle.py` (new, 17 HTTP-level tests,
  real Postgres/Redis/filesystem, no mocks): full pipeline to `CHUNKED`
  with persisted-chunk ordering/metadata verification, no-duplicate-rows,
  cascade-delete, resume-from-`PARSED`/`CLEANED`, `CHUNKED`-rejected-
  with-`409`, cleaning/chunking failure paths landing safely in `FAILED`
  never a raw `500`, exactly-one `DOCUMENT_CHUNKED` audit event,
  VIEWER-role rejection, cross-workspace chunk isolation, a concurrent-
  duplicate-chunk-insert-race recovery test, a commit-order regression
  test proving `CLEANED` commits before chunking is attempted, and a
  slow-chunking event-loop-non-blocking test. Six pre-existing tests in
  `tests/test_document_processing.py` updated (not newly added) to
  assert `CHUNKED` instead of `PARSED` as the pipeline's terminal
  success state — an intended consequence of this slice, not a
  regression.
- `ruff`/`mypy` clean (103 source files). Complete backend suite:
  **507/507 passing** (473 pre-existing + 34 new), 3 consecutive runs.
  No dependency added, so no Docker rebuild was needed.
- Docs updated in the same working tree: `PROJECT_STATE.md`,
  `HANDOFF.md`, `docs/DATA_MODEL.md`, `docs/API_CONTRACT.md`. No new ADR.

### 2026-09-22 — `feat: add structure-aware chunking (Issue #3, Slice 3.5)` (`06577aa`, docs `9afc69c`/`fb44dc1`/`8e8401b`), merged as `237be97`

*(Branch `issue-3-slice-3-5-structure-aware-chunking`, cut from the
merged Slice 3.4 (`2961b62`, PR #21). Opened as **PR #22**, verified
green on GitHub Actions CI, and **merged into `main` as squash commit
`237be97`**.)*

- Adds `backend/app/ingestion/chunking.py`: a `ChunkingConfig` (all
  sizes are character counts, not tokens), a `Chunk` output dataclass
  (deliberately not the `DocumentChunk` SQLAlchemy model — no database
  dependency), a `ChunkingStrategy` protocol, and one concrete
  implementation, `StructureAwareChunker`. Pure
  `ExtractedDocument -> list[Chunk]` transformation — no database, HTTP,
  filesystem, or lifecycle dependency; nothing is persisted, no
  `PARSED -> CLEANED -> CHUNKED` transition happens (that's Slice 3.6).
- **Central design decision**: a `Chunk` never spans more than one
  `ExtractedSection`, since `document_chunks` (migration `0004`) stores
  exactly one `page`/`section` value per row — no array/range type.
  Every `Chunk` inherits its source section's `page`/`heading` value
  unchanged; a short section produces its own short chunk rather than
  being merged with a different section's content under an invented,
  misleading metadata value. Overlap follows the same rule — never
  carried across a section boundary.
- Boundary preference: section (never crossed) → paragraph (a blank
  line, falling back to a single newline when none exists — most of
  this project's own extractors join lines with `\n`, not `\n\n`) →
  sentence (a `.`/`!`/`?` punctuation heuristic, not real segmentation)
  → word → a hard character cut, reached only for a single "word" (no
  internal whitespace) that alone still exceeds `max_chunk_size`.
  Splitting guarantees every piece is `<= max_chunk_size` before
  packing; packing greedily targets `target_chunk_size`, carries
  `chunk_overlap` characters into the next chunk, and merges an
  undersized trailing remainder into the previous chunk when that stays
  within `max_chunk_size`.
- `ChunkingConfig` validates eagerly (`ValueError`, matching
  `app/core/config.py`'s own convention): every size positive,
  `max_chunk_size` capped at an absolute 100,000-character ceiling,
  `min_chunk_size <= target_chunk_size <= max_chunk_size`,
  `chunk_overlap < min_chunk_size`. A `ChunkingError` (raised only for a
  `_MAX_CHUNKS_PER_DOCUMENT` resource-safety ceiling, not for config
  validation) protects against a pathological configuration producing
  an unreasonable chunk count.
- `backend/tests/test_chunking.py` (new, 45 unit tests, no
  database/HTTP/filesystem): basic chunking, determinism (repeated
  calls and fresh instances), gapless zero-based indexes, section/page
  metadata preservation and non-mixing across sections, multiple
  pages/sections, sentence/hard-character splitting for oversized
  paragraphs, overlap behavior (tail-appears-in-next-chunk,
  zero-overlap-no-duplication, never-exceeds-max), min/max enforcement
  including trailing-remainder merge-back, empty/whitespace handling,
  every `ChunkingConfig` validation rule, pathological-input
  no-infinite-loop and bounded-chunk-count behavior, a large-document
  no-quadratic-blowup timing test, and two tests feeding this module
  real `extraction.extract()` output (Markdown, PDF) to prove the two
  modules' contracts actually compose.
- **A dedicated post-implementation quality review found and fixed two
  genuine gaps**: (1) the overlap mechanism could emit a tiny orphaned
  fragment chunk (pure carried-over overlap text that failed to combine
  with the next piece), violating `min_chunk_size` and duplicating the
  previous chunk's own tail — fixed by discarding pure-overlap buffers
  that can't be combined further rather than emitting them; (2) the
  `_MAX_CHUNKS_PER_DOCUMENT` ceiling was checked only once per section,
  so a single very large section (TXT/CSV always produce exactly one)
  could build far more than the stated ceiling internally before the
  check ever ran — fixed by checking incrementally inside the packing
  loop. Both verified with regression tests confirmed (via temporary,
  `Edit`-based reverts, never `git checkout` on uncommitted work) to
  fail against the pre-fix code and pass against the fix.
- No third-party tokenizer or chunking framework added — stdlib `re`/
  `dataclasses`/`typing` only; a real tokenizer was considered and
  explicitly rejected for this slice (chunk sizing shouldn't be tied to
  a specific model/tokenizer choice before `EmbeddingProvider`, Slice
  3.7, exists to consume it).
- `ruff`/`mypy` clean (99 source files). 45 new tests, 45/45 passing.
  Complete backend suite: **471/471 passing** (426 pre-existing + 45
  new), 3 consecutive runs. Frontend unaffected (no frontend file
  changed) — `eslint`/`tsc --noEmit` re-confirmed clean. No dependency
  added, so no Docker rebuild was needed for this slice.
- Docs updated in the same working tree: `PROJECT_STATE.md`,
  `HANDOFF.md`. No ADR added — the schema-compatibility constraint is a
  direct consequence of the already-existing `document_chunks` schema,
  documented in the module's own docstring, not a new architectural
  decision.

**Final independent review (same PR #22)**: stress-tested the merged
implementation beyond the original test suite — Unicode/multi-script
text (Tamil, Kannada, Hindi, emoji, CJK, combining characters) confirmed
correctly sized by character count, never bytes (the module never calls
`.encode()`/`.decode()`, so Python's native codepoint-based `str`
semantics apply throughout); adversarial overlap configurations
(overlap=1, overlap=min-1, overlap after hard-character splitting,
cross-section boundaries) found no leakage, duplication, or violation;
a single enormous section (matching extraction's own real 20 MiB
single-document cap, in the pathological short-space-separated-token
shape) confirmed linear, bounded, non-quadratic — no new correctness
bug found. Two genuine test/documentation gaps were found and closed:
(1) the documented `min_chunk_size` trailing-remainder exception was
verified genuinely reachable (reproduced directly: ten 9-character
words packed to 19-char chunks under a 20-char max leave a real
1-character trailing chunk that cannot merge back) but had no
regression test locking it in — added one; (2) the existing
no-quadratic-blowup timing test only covered 50 *small* sections, never
a genuinely large *single* section (the shape TXT/CSV always produce)
— added a dedicated single-section performance test. The
`_MAX_CHUNKS_PER_DOCUMENT` ceiling's own comment was corrected to state
precisely what it bounds (accumulated output, checked incrementally)
versus what it doesn't (the necessarily single-pass splitting phase,
whose own cost — measured directly, not assumed, at ~1.7s/~250 MiB for
one 20 MiB section, confirmed linear across 5/20/50 MiB) — accepted as
bounded by extraction's own pre-existing cap, not a code defect. `ruff`/
`mypy` clean. 2 new regression tests. Complete backend suite:
**473/473 passing** (471 pre-review + 2 new), 3 consecutive runs.

### 2026-09-22 — `feat: add document text extraction (Issue #3, Slice 3.4)` (`b01cd24`/`8f72916`, review fixes `105ec72`/`eb14287`), merged as `2961b62`

*(Branch `issue-3-slice-3-4-text-extraction`, cut from the merged Slice
3.3 (`a6762e2`, PR #20). Opened as **PR #21**, verified green on GitHub
Actions CI (4/4 checks) after each of two pre-merge correctness reviews'
fixes, and **merged into `main` as squash commit `2961b62`**.)*

- Adds `POST
  /api/v1/workspaces/{workspace_id}/documents/{document_id}/process` —
  synchronous text extraction for the same five formats Slice 3.3
  accepts (PDF, DOCX, TXT, Markdown, CSV), moving a document from
  `UPLOADED`/`PROCESSING`/`FAILED` to `PARSED` or `FAILED`. No chunking,
  embedding, vector indexing, or background job system — synchronous,
  within the request, per this slice's own scope.
- `backend/app/ingestion/extraction.py` (new): `extract(extension,
  content) -> ExtractedDocument` (`ExtractedSection` list with
  `page`/`heading`/`text`), or a raised `ExtractionError` — pure, no
  database/storage/HTTP dependency. Per-format extractors: PDF (pypdf,
  one section per page, a 2000-page cap, per-page parser-exception
  isolation); DOCX (python-docx, sections split on heading-styled
  paragraphs) behind a pre-flight ZIP archive-safety check
  (`_validate_docx_archive_safety`) that inspects only ZIP
  central-directory metadata — member count (≤2000), per-member
  uncompressed size (≤50 MiB), total uncompressed size (≤200 MiB), and
  member-name traversal (`..`/leading `/`) — before any member is
  decompressed or `python-docx` runs; TXT/Markdown (decoded with
  `errors="replace"`, Markdown split on top-level headings); CSV (via
  the stdlib `csv` module, `csv.Error` normalized). A 20 MiB output-text
  budget applies to every format, independent of the input-size limit.
  New dependencies: `pypdf`, `python-docx`.
- `backend/app/services/document_service.py` (extended):
  `process_document()` — looks up the document scoped to its workspace
  (404 if absent/cross-workspace), rejects `PARSED`/later states with
  `409`, transitions to `PROCESSING` and **commits that transition as
  its own transaction before extraction runs** (so a crash mid-parse
  leaves the document honestly `PROCESSING`, not falsely `PARSED`), then
  reads through `StorageProvider` and calls `extraction.extract()`. A
  parsing failure (a `StorageError`, an `ExtractionError`, or any other
  unexpected exception) is recorded as `FAILED` with a short generic
  `failure_reason` and returned as an ordinary `200` — never raised as a
  request error, never silently swallowed.
- `backend/app/repositories/document_repository.py`: additive
  `get_by_id_for_workspace()`, `mark_processing()`, `mark_parsed()`,
  `mark_failed()` — all follow the existing add/flush/no-commit
  convention; the caller controls transaction boundaries.
  `backend/app/schemas/document.py`: additive `failure_reason: str |
  None` on `DocumentRead`. `backend/app/core/audit.py`: additive
  `AuditEvent.DOCUMENT_PARSED`/`DOCUMENT_PARSING_FAILED`.
  `backend/app/core/rate_limit.py`: additive `document_process`
  operation (IP + authenticated user ID, Tier A, 20/60s — CPU-bound, so
  it gets the same defensive treatment as `document_upload`, not
  register/login's lighter policy). `backend/app/api/v1/documents.py`:
  new `POST .../process` route in the same router as upload.
- `backend/tests/test_extraction.py` (new, 27 unit tests, no
  database/HTTP): valid/malformed/no-extractable-text PDF, a page-count
  limit, a simulated single-page parser exception; valid DOCX with
  heading-split sections, a malformed zip, four archive-traversal member
  names, member-count/per-member/total-size limits (via monkeypatched
  smaller thresholds for determinism, plus one real highly-compressible
  60 MB→~50 KB member proving the check is against declared
  uncompressed size at the real default threshold, not on-disk size), a
  DOCX that passes the safety check but isn't real OOXML; valid/invalid-
  byte-sequence TXT; Markdown heading-splitting and the empty-document
  edge case; valid CSV and a field-size-limit failure; the unsupported-
  extension path and the output-text budget.
- `backend/tests/test_document_processing.py` (new, 24 HTTP-level tests,
  real Postgres/Redis/filesystem, no mocks): per-format success
  (PARSED, correct `page_count`, exactly one `DOCUMENT_PARSED` audit
  row); per-format/malformed failure including a DOCX archive-traversal
  attempt (FAILED, `200`, safe `failure_reason`, exactly one
  `DOCUMENT_PARSING_FAILED` audit row); a storage-read failure (FAILED,
  the storage key never appears in the response); an unexpected
  (non-`ExtractionError`) exception from the extractor (FAILED, not a
  `500`); a regression test proving the `PROCESSING` transition is
  actually committed before extraction runs (reads the document's status
  through the same session from inside a patched `extraction.extract`,
  before it returns); authorization (unauthenticated `401`, VIEWER
  `403`, non-member/cross-workspace-document-id `404`,
  nonexistent-document `404`); lifecycle (`PARSED` reprocess `409`,
  `FAILED` reprocess allowed); rate-limit key creation, threshold
  enforcement, and Redis-unavailable Tier A fallback (each via a single
  reprocessed `FAILED` document, to exhaust the `document_process` limit
  without also tripping the separate `document_upload` limit).
- `ruff`/`mypy` clean (97 source files). New tests: 27 + 24 = 51/51
  passing. Complete backend suite: **421/421 passing** (370 pre-existing
  + 51 new), 3 consecutive runs. Frontend unaffected (no frontend code
  changed) — `eslint`/`tsc --noEmit` re-confirmed clean. A full manual
  smoke test against the real Docker Compose stack (backend image
  rebuilt with the new `pypdf`/`python-docx` dependencies; register →
  create workspace → upload a real 2-page PDF → process → `PARSED` with
  `page_count: 2`) succeeded end-to-end.
- Docs updated in the same working tree: `docs/API_CONTRACT.md` (the
  `/process` endpoint's full contract), `docs/SECURITY.md` ("Upload &
  document safety" extended with the extraction-time threat model and
  limits; "Audit logging" and "Security testing" updated from their
  previous "not yet" state), `PROJECT_STATE.md`, `HANDOFF.md`.

**Pre-merge correctness review (same PR #21, commit `105ec72`)**: found
that the extracted-text budget (`_MAX_EXTRACTED_TEXT_BYTES`) was applied
independently to each section/page rather than as a running total
across the whole document. PDF (up to 2000 pages) and DOCX (one section
per heading) could each produce many sections, so a document with many
sections each near the per-section cap could yield total extracted text
far exceeding the documented per-document limit — for PDF specifically,
pypdf decompresses each page's content stream internally, so a small,
highly compressed upload can still expand to a large per-page text
output (a decompression-bomb shape distinct from the already-handled
DOCX archive case). Markdown has the same multi-section structure,
though bounded by the 50 MiB upload cap since no decompression is
involved. Fixed: PDF/DOCX/Markdown extraction now track a running byte
total across sections, stopping once the budget is reached (not just
truncating each section independently); CSV's rendering was also made
incremental (row by row, with exact separator-byte accounting) rather
than joining every row into one string before truncating. A separate
question — whether a crafted ZIP could lie about a member's declared
uncompressed size to bypass the DOCX archive-safety check while
`python-docx` still decompresses a much larger real payload — was
investigated empirically with a hand-built malicious ZIP fixture and
confirmed **not** exploitable: Python's `zipfile` module caps
decompressed output at the declared size regardless of the underlying
compressed stream's real size, so no code change was needed for that
path. 4 new regression tests (`test_extraction.py`), each confirmed to
fail against the pre-fix code before being confirmed to pass against
the fix. `ruff`/`mypy` clean. Complete backend suite: **425/425
passing** (421 pre-review + 4 new), 3 consecutive runs.

**Final pre-merge review (same PR #21, commit `eb14287`)**: a second,
independent review found and fixed a more significant gap —
`process_document()` called the
synchronous, CPU-bound `extraction.extract()` (and the synchronous
`storage.read()`) directly inside its `async def` body. This project
runs one `uvicorn` process with no `--workers`
(`infra/docker/backend.Dockerfile`'s entrypoint), so a synchronous call
inside an async handler blocks that single event loop for its full
duration — not just for the requesting user, but for **every**
concurrent request the process is serving, including unrelated
workspaces' logins, health checks, and uploads. Confirmed empirically
with a real concurrency test (`httpx.AsyncClient` over an in-process ASGI
transport, sharing the app's own event loop, with an absolute shared
clock): an unrelated concurrent request measurably stalled until a slow
extraction finished. Fixed by running the storage read + parse
(`document_service._read_and_extract()`, new) via `asyncio.to_thread()`
instead of calling it directly — re-confirmed with the same concurrency
test that the unrelated request now completes promptly regardless of a
slow extraction in progress. The existing crash-safety regression test
(`test_processing_transition_is_committed_before_extraction_is_attempted`)
was rewritten to avoid querying the database from inside the (now
thread-offloaded) extraction spy — SQLAlchemy `Session`s are not
thread-safe — replaced with commit/extraction-order tracking via plain
list appends, safe under the GIL; both the rewritten test and the new
concurrency test were confirmed to fail against the pre-fix code before
being confirmed to pass against the fix. Separately reviewed and
confirmed **not** a bug needing a fix: two simultaneous `/process` calls
against the same document are not prevented by a lock, but each request
gets its own database session/connection in production (`get_db()`),
PostgreSQL's row-level locking serializes the competing status-transition
updates, and the deterministic content means both converge on the same
final outcome — the only cost is duplicate extraction work and duplicate
audit rows for one logical operation, already bounded by the
`document_process` rate limit, consistent with this codebase's existing
no-pessimistic-locking convention. A related question — whether a
wall-clock/CPU timeout on a single pathological document's parse should
also be added now — was considered and deliberately deferred: the more
severe "affects every other request" failure mode is what the threading
fix closes; a true per-parse timeout on arbitrary synchronous Python code
would need process-based isolation or signal-based interruption, a
materially larger architectural change out of this slice's scope, and
the existing page-count/output-size caps already bound the structural
work involved. 1 new regression test
(`test_slow_extraction_does_not_block_unrelated_concurrent_requests`).
`ruff`/`mypy` clean. Complete backend suite: **426/426 passing** (425
pre-review + 1 new), 3 consecutive runs.

### 2026-09-20 — Abuse-protection Slice 3c: escalation audit emission + HTTP-level tests

- **Not committed.** Adds abuse-escalation audit emission on top of
  Slice 3b's now-merged decision engine (`42529e3`, PR #14) — no
  production abuse-decision code modified, only consumed via
  `AbuseRecordOutcome`'s existing return value.
- `backend/app/core/audit.py`: one additive constant,
  `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` — no existing constant or
  the `record()` function's signature changed.
- `backend/app/api/v1/auth.py`: a new `_audit_abuse_escalation()` helper
  called from `login`/`forgot-password`/`reset-password` right after
  each `record_login_failure()`/`record_forgot_password_request()`/
  `record_reset_validation_failure()` call. Fires exactly once per
  escalation (`outcome.newly_escalated`) — never on an already-escalated
  repeat, never for an ordinary `ALLOW`. Emits `AuditEvent.RATE_LIMITED`
  for a `STRICT_THROTTLE` transition or `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED`
  for a `TEMPORARY_BLOCK` transition, with metadata limited to
  `rule`/`operation`/`dimension`, the already-HMAC-hashed `account_hash`
  when account-scoped, and `block_ttl_seconds` for blocks — never a raw
  email, password, or token. `user_id` is always `None` (genuinely
  unavailable at this layer in all three call sites, never invented).
  `ip_address` is the same trusted-proxy-resolved value the abuse
  decision itself acted on.
- `backend/tests/test_abuse_audit.py` (new, 6 HTTP-level tests, real
  Redis + real PostgreSQL, no mocks): R1 strict-throttle with exactly
  one audit row and strict-bucket consumption proof; account-scoped R2
  through the endpoint with isolation; R3's 5-distinct-IP temporary
  block with audit row, TTL metadata, and outright post-block rejection;
  R4 forgot-password strict-throttle with enumeration resistance intact;
  R5 reset-password validation-failure block; successful-login reset
  behavior with zero abuse-audit rows from an ordinary sequence. Two
  test-design bugs (not production defects) were found and fixed during
  this slice's own validation: an initial attempt to pre-fill the base
  `rl:*` bucket with abundant tokens doesn't work (the Lua script always
  clamps effective tokens at the dimension's configured capacity,
  regardless of stored value) — fixed by pre-seeding the abuse layer's
  own counters directly via the same production `record_*` functions;
  and an assertion wrongly assumed a globally-empty `audit_logs` table
  for `LOGIN_SUCCEEDED`, when 5 real historical rows already existed
  from earlier manual verification sessions against the live stack —
  fixed by scoping the assertion to the test's own unique IP.
- `ruff`/`mypy` clean (82 source files). **6/6 new tests passed, 3
  consecutive times**, alongside the complete **254-test backend suite
  passing 254/254, 3 consecutive runs**, against real Redis and real
  PostgreSQL inside `compose-backend-1` (the host shell's own
  published-port path remained broken this session too).
- Docs updated in the same working tree: ADR 0006 (Implementation status
  table updated for Slice 3b's merge and the new audit-emission row),
  `docs/SECURITY.md` (the "Rate limiting" section's stale
  "abuse-detection layer does not exist yet" statement corrected now
  that Slice 3b has actually merged; "Audit logging" extended for the
  two new event types and their metadata/`user_id` conventions),
  `PROJECT_STATE.md`, `HANDOFF.md`.

### 2026-09-19 — Test-isolation fix: sweep `abuse:*` Redis keys between tests

- **Not committed to `main`** (commit on the still-open PR #14 branch,
  `issue-redis-rate-limiting-slice-3b`). Fixes a real test-isolation gap
  the abuse-protection layer's endpoint wiring (Slice 3b, below)
  surfaced and CI itself caught: `backend/tests/conftest.py`'s
  `_reset_rate_limiters` autouse fixture swept `rl:*` Redis keys between
  tests but not the new `abuse:*` keys `login`/`forgot-password`/
  `reset-password` now write. Every `TestClient` request shares the same
  fixed default peer IP, so that state accumulated across unrelated
  tests within one pytest session and could legitimately trip R4's
  `STRICT_THROTTLE`, producing real `429` responses in later,
  unconnected tests.
- Fixed with a single, minimal change: the existing `rl:*`
  pattern-delete loop now also sweeps `abuse:*`, under the same
  `RedisError` tolerance already in place. No production code touched
  (`abuse_decision.py`/`abuse_state.py`/`rate_limit.py`/`auth.py` all
  unchanged); no test skipped, `xfail`ed, or reordered.
- The complete backend suite (248 tests: 215 pre-abuse-layer + 32 Slice
  3a + 33 Slice 3b) **passed 248/248, 3 consecutive runs**, against real
  PostgreSQL and real Redis. `ruff`/`mypy` clean.

### 2026-09-19 — Abuse-protection Slice 3b: decision engine and endpoint wiring

- **Not committed.** Implements the deterministic decision layer on top
  of Slice 3a's primitives (now merged, see `[Unreleased — committed]`
  below) and wires it into `login`/`forgot-password`/`reset-password` —
  the only three operations any of R1–R5 target. `register`/`refresh`
  remain byte-for-byte unchanged.
- `backend/app/core/abuse_decision.py` (new): a module-level R1–R5 rule
  table (the data that makes `TEMPORARY_BLOCK` deterministically
  dominate `STRICT_THROTTLE` — block dimensions are always resolved
  before any strict dimension is even inspected); `check()` (pre-request,
  read-only); four explicitly-named record functions
  (`record_login_failure`, `record_login_success`,
  `record_forgot_password_request`, `record_reset_validation_failure` —
  deliberately not one function overloaded with a `succeeded` flag,
  since `forgot-password` has no real success/failure branch to key
  off); fails open unconditionally on Redis unavailability, no-ops when
  Redis is unconfigured; never touches PostgreSQL or `app.core.audit`
  (Slice 3c's job).
- `backend/app/core/abuse_state.py` (additive): one new primitive,
  `temporary_block_ttl_seconds()`, for an accurate `Retry-After` on a
  blocked response — no existing signature changed.
- `backend/app/core/token_bucket_types.py` (new): `DimensionSpec`/
  `TokenBucketResult` extracted out of `rate_limit.py` to break a
  circular import (`rate_limit.py` → `abuse_decision.py` →
  `abuse_state.py` → `rate_limit.py`) discovered — via an actual
  `ImportError`, not just suspected — while wiring this slice.
  `rate_limit.py` re-exports both names unchanged; no other call site
  needed to change.
- `backend/app/core/rate_limit.py` / `backend/app/api/v1/auth.py`
  (modified): `enforce_login_rate_limit`/
  `enforce_forgot_password_rate_limit`/`enforce_reset_password_rate_limit`
  now consult `abuse_decision.check()` ahead of the base `check_all()`
  (an active block rejects immediately; an active strict dimension is
  folded into the same atomic `check_all()` invocation as the base
  dimensions — never a second Redis round trip). `login`/
  `forgot-password`/`reset-password` gained post-outcome recording,
  called only after the real outcome is known — never in the
  pre-request dependency, which necessarily runs before authentication
  is attempted.
- `backend/tests/test_abuse_decision.py` (new, 33 tests): rule-table
  shape, per-rule threshold behavior for R1–R5, TTL/non-refresh
  semantics, simultaneous-rule precedence (confirming block always
  dominates strict, by construction), account/IP isolation,
  successful-login reset scoping, R4's unconditional recording, R5's
  failure-only recording, Redis-unavailable/unconfigured handling,
  concurrency races, strict-dimension atomicity with the base dimension,
  and no raw secret leakage. Two test-design bugs (not implementation
  bugs) were found and fixed during this slice's own validation.
- `ruff`/`mypy` clean (81 source files). **33/33 new tests passed, 3
  consecutive times, against real Redis + real PostgreSQL**, run inside
  `compose-backend-1` (the host shell's own published-port path remained
  broken this session too) — alongside the unaffected 32 from Slice 3a
  (65/65 combined).
- **A genuine test-infrastructure gap was found and deliberately not
  fixed** (out of scope for this slice): `tests/conftest.py`'s
  `_reset_rate_limiters` sweeps `rl:*` between tests but not the new
  `abuse:*` keys, so a full pre-existing-suite run can accumulate real
  R4 state across the shared default `TestClient` IP and fail 2
  pre-existing `test_password_reset.py` tests — reproduced from a
  freshly flushed Redis, confirmed unrelated to this slice's own
  correctness. Recorded in `HANDOFF.md` with the exact one-line fix for
  a future, separately-approved change.
- Docs updated in the same working tree: ADR 0006 (§6's flow diagram
  corrected — the original placed `record(outcome)` inside the
  pre-request dependency, which is unreachable since outcomes aren't
  known until the endpoint body runs; "Implementation status" table
  updated), `PROJECT_STATE.md`, `HANDOFF.md`. `docs/SECURITY.md`
  reviewed and left unchanged — it describes the *committed* codebase,
  and Slice 3b isn't committed yet, so its "abuse layer doesn't exist
  yet" statement remains accurate for `main`.

### 2026-09-19 — Abuse-protection Slice 3a: real-Redis validation

- **Still not committed** — this entry records a validation result for
  the same uncommitted working tree as the entry immediately below, not a
  new implementation change.
- The host shell's path to the Dockerized Redis/Postgres published ports
  (`127.0.0.1:5432`/`127.0.0.1:6379`) was found broken this session (TCP
  handshake succeeds, protocol read reset) — confirmed as an environment
  fault via internal Docker-network health checks and via a
  previously-passing, unrelated test file failing identically, not a
  Slice 3a defect.
- Worked around by running `tests/test_abuse_state.py` **inside the
  running `compose-backend-1` container**, over its internal `db`/`redis`
  Docker service hostnames: **32/32 passed, 3 consecutive runs**, no
  flakiness. Live Redis inspection during that run confirmed real
  `abuse:*` key creation of every expected type, a finite positive TTL on
  every key observed, and no raw email substring in any key name or
  value. `ruff`/`mypy` re-confirmed clean inside the container.
- The container's own backend image was stale relative to `main` HEAD
  (missing 8 pre-existing tests from `test_rate_limit_wiring.py`) and had
  an `EMAIL_PROVIDER=smtp` app-runtime setting that caused 5 unrelated
  `test_password_reset.py` failures (diagnosed and resolved via a
  one-off, file-free `EMAIL_PROVIDER=console` invocation override to
  confirm the root cause) — **this is not a run of the current 215-test
  full suite** and is not represented as one.
- Net effect: Slice 3a's 32 tests are now **real-Redis validated**,
  distinct from — and not yet extending to — a clean host-side full-suite
  run or any production validation.

### 2026-09-18 — Abuse-protection Slice 3a: Redis/Lua primitives for the deterministic abuse layer (ADR 0006 §11/§12)

- **Not committed.** Implements only the low-level Redis primitives the
  abuse layer needs — no rule table, no `AbuseDecisionEngine`, no
  endpoint wiring (Slice 3b/3c, not started). Every existing endpoint
  (`register`/`login`/`refresh`/`forgot-password`/`reset-password`)
  remains byte-for-byte unchanged from Slice 2.
- `backend/app/core/abuse_keys.py` (new): key builders for the `abuse:`
  namespace (`failcount_key`, `distinct_ips_key`, `strict_throttle_key`,
  `block_key`), mirroring `redis_keys.py`'s role for `rl:`.
- `backend/app/core/abuse_state.py` (new): atomic Lua-scripted
  primitives, fully parameterized (no hardcoded thresholds):
  `record_login_failure()` (one Lua invocation atomically updating the
  IP failcount, account failcount, and distinct-IP HyperLogLog together,
  escalating each dimension independently once its own threshold is
  crossed); `record_ip_failure()` (the shared primitive behind the
  forgot-password/reset-password IP counters, parameterized by a
  `strict`/`block` escalation mode); `reset_account_state()` (the
  successful-login decay — deletes only the account-scoped failcount and
  distinct-IP HyperLogLog, never the IP failcount or any block/strict
  state); `is_strict_throttle_active()`/`is_temporarily_blocked()`
  (read-only checks for Slice 3b's future use). STRICT_THROTTLE reuses
  the existing `RedisTokenBucketLimiter`/`DimensionSpec` bucket shape —
  no new bucket engine. TEMPORARY_BLOCK's TTL is set once at creation and
  never refreshed (guarantees ADR §12's "never permanent or indefinite");
  STRICT_THROTTLE's TTL does refresh on re-escalation. All primitives
  raise `RedisUnavailableError` on failure — no second fallback limiter.
- `backend/tests/test_abuse_state.py` (new, 32 tests): failcount
  lifecycle, HyperLogLog lifecycle, reset-on-success scoping, block/
  strict-throttle creation and TTL semantics, multi-signal atomicity,
  concurrent-write races (real `threading`, no mocks), cross-account/
  cross-IP isolation, Redis-unavailable handling, and a check that no raw
  email or secret is ever stored in a Redis value.
- `ruff`/`mypy` clean on all three new files; `pytest --collect-only`
  succeeds at 215 tests (183 existing + 32 new). **The 32 new tests have
  not been executed against a real Redis this session** — Docker/WSL was
  confirmed unavailable (connection-refused checks against both
  6379/5432; see `HANDOFF.md` for the exact evidence). Do not read "215
  collected" as a passing count.
- Docs updated in the same working tree: `docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md`
  (R1–R5 thresholds/windows resolved and recorded, the corrected
  60-second token-bucket timing derivation replacing an earlier wrong
  "~2 minutes" estimate, the strict/block TTL-asymmetry rationale, the
  successful-login decay policy, and a 7-row per-component
  implementation-status breakdown for the abuse layer),
  `PROJECT_STATE.md` (component-status rows), `HANDOFF.md` (current
  task, a new "Completed work (Redis abuse layer — Slice 3a)" section,
  revised "Next major task"/"Tests run"/"Exact next recommended action").
  `docs/SECURITY.md` was reviewed and needs no change — it already
  states the abuse layer doesn't exist yet, still true since Slice 3a
  changes no runtime behavior.

### 2026-09-11 — Application Foundation: backend/frontend/infra scaffold, Docker fixes, CI workflow

- Backend (`backend/`): FastAPI scaffold with configuration
  (`app/core/config.py`), structured JSON logging, request-ID middleware,
  centralized error handling, SQLAlchemy + Alembic, a pgvector-enabling
  migration (`0001_enable_pgvector_extension`), and health/readiness
  endpoints (`/api/v1/health`, `/api/v1/health/ready`).
- Frontend (`frontend/`): Next.js + TypeScript, Tailwind v4, a shadcn/ui
  foundation, an application shell, stub routes for the target feature
  areas, and a live backend-readiness widget (`components/backend-status.tsx`).
- Infrastructure (`infra/`): `infra/docker/backend.Dockerfile`,
  `infra/docker/frontend.Dockerfile`, and
  `infra/compose/docker-compose.yml` wiring Postgres+pgvector, backend, and
  frontend together for local development.
- Fixed a container-runtime bug found during verification: the backend
  image built its virtualenv as root, then switched to a non-root
  `appuser` without transferring ownership, so the entrypoint's
  `uv run alembic upgrade head` crash-looped with `Permission denied`
  trying to resync the root-owned `.venv`. Fixed with
  `chown -R appuser:appuser /app` before `USER appuser` in
  `infra/docker/backend.Dockerfile`.
- Fixed a missing-CORS bug found during verification: the backend had no
  CORS middleware, so a real browser at `http://localhost:3000` fetching
  `http://localhost:8000` would have been silently blocked even though the
  backend was reachable (confirmed via `curl` outside the browser's CORS
  enforcement). Added `CORSMiddleware` to `backend/app/main.py`, a new
  `cors_allowed_origins` setting (default `http://localhost:3000`) in
  `backend/app/core/config.py`, and wired `CORS_ALLOWED_ORIGINS` through
  `.env.example` and `infra/compose/docker-compose.yml`.
- Added `.github/workflows/ci.yml`: backend lint/typecheck/tests, frontend
  lint/typecheck/tests/build, and a Docker build + `docker compose config`
  validation job.
- Verified end-to-end, against real running containers (not mocked):
  both Docker images build; the full Compose stack starts; the pgvector
  extension is enabled in the running Postgres container (`vector 0.8.6`);
  the Alembic migration applies against the real database
  (`alembic current` → `0001 (head)`); `/api/v1/health` and
  `/api/v1/health/ready` return 200 with a real database round-trip; the
  frontend serves; and a CORS-enabled cross-origin fetch from the
  frontend's origin to the backend's readiness endpoint succeeds.
- No product functionality (auth, ingestion, retrieval, generation, chat,
  voice) was implemented — out of scope for this issue. See `HANDOFF.md`
  for the one verification gap (the `BackendStatus` widget's resolved
  rendered state was not confirmed in an actual browser DOM, only the
  underlying CORS-enabled fetch it depends on).

### 2026-09-11 — Second-pass documentation audit and corrections

- Audited the full documentation set for internal consistency (see
  `HANDOFF.md` for the finding list: 0 CRITICAL / 2 HIGH / 5 MEDIUM / 4 LOW
  / 3 SUGGESTION) and applied corrections:
  - Added [ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md)
    (authentication/session architecture), resolving the bearer-token vs.
    session-revocation contradiction and promoting `sessions` to a core
    entity in `docs/DATA_MODEL.md`. Updated `docs/API_CONTRACT.md` and
    `docs/SECURITY.md` to match.
  - Documented the rate-limiting approach (in-process/PostgreSQL-backed,
    no Redis) in `docs/SECURITY.md` and `docs/ARCHITECTURE.md`.
  - Added `RERANKER_API_KEY` to `.env.example`.
  - Added a target audit-logs API namespace to `docs/API_CONTRACT.md`.
  - Documented chunking-strategy comparison in `docs/EVALUATION.md`.
  - Added `.gitattributes` to the target tree in `docs/ARCHITECTURE.md`.
  - Reworded `README.md`'s opening to avoid any production-readiness
    misread.
  - Documented the Git-workflow bootstrap exception in `AGENTS.md`.
  - Made `docs/DECISIONS/` and `.agents/skills/` explicitly discoverable
    in `START_HERE.md`/`README.md`.
  - Clarified that baseline issue numbers in `PROJECT_STATE.md`/
    `AGENTS.md` are planning references, not existing GitHub issues.
- No application code, dependencies, schemas, Docker services, API
  endpoints, or GitHub issues were created — documentation only.

### 2026-09-11 — Documentation architecture established

- Populated the full documentation/project-memory system: `README.md`,
  `START_HERE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
  `PROJECT_STATE.md`, `HANDOFF.md`, `SOLVING.md` (this changelog's sibling
  files were all previously empty placeholders).
- Populated `docs/PROJECT_BRIEF.md`, `docs/REQUIREMENTS.md`,
  `docs/ARCHITECTURE.md`, `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`,
  `docs/SECURITY.md`, `docs/RAG_DESIGN.md`, `docs/EVALUATION.md`,
  `docs/DEPLOYMENT.md`.
- Added `docs/DECISIONS/` with an ADR process, a template, and two initial
  architecture decision records: modular monolith over microservices, and
  PostgreSQL + pgvector as the initial vector store.
- Added `.agents/skills/README.md` documenting the intended skills roster
  and the RULE/SKILL/MCP/MEMORY/ADR/HANDOFF/SOLVING distinction.
- No application code, dependencies, database schema, Docker services, or
  API endpoints were added — this was a documentation-only initialization
  task.

## [Unreleased — committed]

### 2026-09-21 — `feat: add document upload API (Issue #3, Slice 3.3)` (b81b7d2) + docs (b3cf3cf), merged as `a6762e2`

*(Branch `issue-3-slice-3-3-document-upload-api`, cut from the merged
Slice 3.2 fix (`5e6fdc2`, PR #19). Opened as **PR #20**, merged into
`main` as squash commit `a6762e2` by the repository owner — not by this
agent. `main`/`origin/main` are at `a6762e2`.)*

`POST /api/v1/workspaces/{workspace_id}/documents`
(`multipart/form-data`, field `file`) — authenticate, authorize
(MEMBER, via the existing `require_workspace_role`), rate-limit,
validate, checksum, check for a workspace-scoped duplicate, write to
`StorageProvider`, create the `documents` row, emit the audit event,
commit, return `201`. The document stays in `UPLOADED` — no
extraction, chunking, embedding, or background processing.

`backend/app/services/document_service.py` (new): validation (extension
allowlist, MIME allowlist including named browser variants for
`.md`/`.csv`, a magic-byte signature check for PDF/DOCX — no reliable
signature exists for the plain-text formats, a documented gap, not a
hidden one); a streamed, chunked checksum/size-limit reader that aborts
before buffering an oversized payload; storage-key generation from
trusted identifiers only, never the client filename. Storage-then-
database ordering: the file always durably exists before any DB row is
attempted; if the insert then fails for any reason (including a
race-lost duplicate-checksum insert the pre-check missed), a
best-effort compensating `storage.delete()` runs, logged if it also
fails, never masking the original error. Duplicate uploads in the same
workspace return `409` referencing the existing document's id; the same
checksum in a different workspace is unaffected.

`backend/app/repositories/document_repository.py`,
`backend/app/schemas/document.py` (new, small, following the existing
patterns exactly — `DocumentRead` never includes `storage_key`).
`backend/app/core/audit.py`: additive `AuditEvent.DOCUMENT_UPLOADED`.
`backend/app/core/rate_limit.py`: additive `document_upload` operation
(IP + authenticated user ID, 20/60s, Tier A — falls back on a Redis
outage, never fails open; the R1–R5 abuse-decision layer is not
consulted, since its rule table targets a different threat model).
`backend/app/core/config.py`: additive `max_upload_size_bytes` (default
50 MiB). New dependency: `python-multipart`. `backend/app/api/v1/documents.py`
(new) + router registration.

`backend/tests/test_document_service.py` (new, 37 unit tests, no
database) and `backend/tests/test_document_upload.py` (new, 30
HTTP-level tests, real Postgres/Redis/filesystem, no mocks) — covering
authentication/authorization/cross-workspace isolation, every supported
format, unsupported extension/MIME/signature mismatches, the size
limit, checksum correctness, path-traversal-filename safety, the audit
event, duplicate-checksum handling (same and different workspace), a
genuine storage failure, a genuine database failure (FK violation)
after a successful storage write with compensating cleanup, a genuine
race-lost duplicate insert, cleanup-failure path-leak safety, malformed
multipart input, and real-Redis rate-limit key creation/enforcement/
fallback.

`docs/API_CONTRACT.md`: the `/api/v1/workspaces/{workspace_id}/documents`
contract filled in (correcting the "Target namespaces" table's earlier
flat, non-binding `/api/v1/documents` sketch to the nested path
actually used). `docs/SECURITY.md`: "Upload & document safety"
extended; "Audit logging" and "Security testing" bullets updated from
their previous "not implemented yet" state.

`ruff`/`mypy` clean (94 source files). 67/67 new tests passing; the
complete backend suite 361/361 passing (294 pre-existing + 67 new), 3
consecutive runs, no regression in any existing test. Frontend
re-confirmed unaffected (48/48 vitest, lint/typecheck clean). A full
manual smoke test against the real Docker Compose stack (register →
create workspace → upload a real PDF) succeeded end-to-end, including
verifying the file landed at the correct path inside the running
container.

**Pre-merge correctness review (same PR #20, commit `1cc760f`)**: found
that `_cleanup_orphaned_storage_object()` only caught `StorageError`,
but `StorageProvider` is an unenforced `Protocol` — a cleanup-time
failure of any other exception type would have propagated uncaught,
masking the original error (e.g. a genuine race-lost-duplicate `409`)
with whatever the cleanup attempt itself raised. Fixed: broadened to
catch `Exception`, still never re-raising, still only logging
identifiers, never a path. New regression test proves the original
`409` still surfaces when the compensating delete itself fails with an
unrelated exception type. Also added: boundary-precision tests for the
streaming size limit (exactly at the limit succeeds; one byte over is
rejected; the check depends only on bytes actually read, never a
length hint) and four additional path-traversal-style filename
patterns beyond the one already covered. `ruff`/`mypy` clean. 9 new
tests, 67 → 76, 76/76 passing. Complete backend suite: 370/370 passing
(361 pre-review + 9 new), 3 consecutive runs.

### 2026-09-21 — `feat: add StorageProvider abstraction (Issue #3, Slice 3.2)` (91d98b7) + docs (d57ccdb, 044c54f), merged as `941c1a7`

*(Branch `issue-3-slice-3-2-storage-provider`, cut from the merged Slice
3.1 (`79d4787`, PR #17). Opened as **PR #18**, verified green on GitHub
Actions CI (4/4 checks), merged into `main` as squash commit `941c1a7`.
Note: this merge happened before a concurrent correctness/security
review of the same slice had finished — that review's own fix (next
entry below) landed as a separate follow-up PR instead of inside this
one.)*

Adds the `StorageProvider` abstraction — a `Protocol`
(`save`/`read`/`delete`/`exists`) plus `LocalStorage`, a filesystem-
backed implementation for local dev/CI, mirroring `EmailProvider`'s
exact shape (`backend/app/services/storage_provider.py`). Storage keys
are always server-generated upstream (never a user-supplied filename —
`docs/SECURITY.md`), but `LocalStorage` also rejects any key that would
resolve outside its configured root as defense in depth. New settings:
`storage_provider` (`Literal["local"]`, the only implementation today)
and `storage_local_root`; `storage_bucket` stays reserved for a future
object-storage provider. 14 new tests
(`backend/tests/test_storage_provider.py`), real filesystem, no mocks.
`ruff`/`mypy` clean. Full backend suite: 287/287 passing (273 existing +
14 new), 3 consecutive runs. No upload endpoint, extraction, chunking,
background processing, or embedding code — nothing calls this yet.

### 2026-09-21 — `fix: prevent raw filesystem errors/paths escaping StorageProvider` (6e96481) + docs (d950d4e), merged as `5e6fdc2`

*(A correctness/security review of the already-merged Slice 3.2 found
that `save()`/`delete()`/`exists()` had no filesystem-error handling at
all, and `read()` only handled the "not found" case — a raw
`PermissionError`/`OSError` could have escaped the module, leaking the
absolute configured storage root via its own message. The review ran
concurrently with PR #18's merge, so the fix couldn't land inside it —
committed as `050b185`/`03c870e` on that now-merged branch, then
cherry-picked cleanly onto a fresh branch cut from `main`, opened as
**PR #19**, verified green on GitHub Actions CI (4/4 checks), merged as
squash commit `5e6fdc2`.)*

Every operation now guards its own filesystem calls, raising
`StorageError` referencing only the caller-supplied key, never the
resolved absolute path. Two stdlib-behavior assumptions from the
original implementation were empirically disproven while fixing this —
`Path.is_file()` does not swallow `OSError` on this project's actual
Python version (3.13.15), contrary to what the original code's own
comment claimed. 7 new tests (`backend/tests/test_storage_provider.py`,
14 → 21): a symlink planted inside the root that would resolve outside
it, permission-denied operations each raising `StorageError` with no
path leak, and `exists()` still correctly returning `True` when only a
file's own permissions are restricted. `ruff`/`mypy` clean. Full backend
suite: 294/294 passing (273 existing + 21 new), 3 consecutive runs.

### 2026-09-20 — `feat: add document and document_chunk schema (Issue #3, Slice 3.1)` (36fe8b0) + docs (301f8a2, e73c883), merged as `79d4787`

*(Branch `issue-3-slice-3-1-document-schema`, cut from the merged
Playwright E2E work (`e1c4858`, PR #16). Opened as **PR #17**, verified
green on GitHub Actions CI (4/4 checks — backend, frontend, Docker
build, and the first real Actions run of the `e2e` job), merged into
`main` as squash commit `79d4787`.)*

GitHub Issue #3 (Knowledge Ingestion), Slice 3.1 — schema only. Adds
`documents`/`document_chunks` (migration `0004`): workspace ownership,
nullable `uploaded_by` (`ON DELETE SET NULL`), server-generated
`storage_key`, a native `DocumentStatus` enum matching the documented
ingestion lifecycle exactly, and `document_chunks` with a deliberately
denormalized `workspace_id` and no embedding column yet (deferred until
the embedding provider/model/dimension is chosen). 19 new tests
(`backend/tests/test_document_schema.py`), real Postgres, no mocks.
`ruff`/`mypy` clean. Full backend suite: 273/273 passing (254 existing +
19 new), 3 consecutive runs. Migration reversibility explicitly verified
(`alembic downgrade 0003` / `upgrade head` against the real database).
Also reconciled a documentation lag from the Playwright merge below
(`PROJECT_STATE.md`/`HANDOFF.md`/`CHANGELOG.md` still described it as
uncommitted).

### 2026-09-20 — `feat: add Playwright E2E coverage for auth and password recovery` (e1c4858)

*(Branch `playwright-e2e-auth-validation`, cut from the merged Slice 3c
(`75dd466`, PR #15). Opened as **PR #16** and merged into `main` as
squash commit `e1c4858` — a single-commit PR, so the commit hash above
is both the branch's own commit and the merge result.)*

Introduces Playwright (`@playwright/test` ^1.63.0, Chromium), previously
absent from this repository. `frontend/playwright.config.ts` —
`workers: 1`/`fullyParallel: false` deliberately, since the backend's
rate limiter and abuse layer (ADR 0006) both key partly by source IP and
every request in a run shares one peer address. 19 tests across three
spec files: `app-availability.spec.ts` (3), `auth.spec.ts` (9 —
registration, session persistence/reload, logout, protected-route
redirects, a genuine CSRF positive+negative case through the real
backend middleware), `password-recovery.spec.ts` (7 — the full
forgot-password → Mailpit → reset-password → post-reset login →
session-revocation flow). Run against the real
frontend/backend/PostgreSQL/Redis/Mailpit stack, no mocks — 19/19
passed, 3 consecutive clean runs. Three genuine findings from validation,
all fixed as test-code corrections, no application code changed:
a locator strict-mode ambiguity (a workspace name correctly renders in
three places, not a bug); a direct refresh-revocation check that
initially omitted the CSRF header a state-changing endpoint requires;
Chromium's own "Failed to load resource: 401" console logging for an
already-handled anonymous-visitor auth check. `.github/workflows/ci.yml`
gained a new `e2e` job. `ruff`/`npx eslint`/`npx tsc --noEmit` all clean;
existing 48 vitest tests unaffected.

### 2026-09-20 — `feat: emit audit events for abuse-layer escalations` (58b6c71), merged as `75dd466`

*(Branch `issue-redis-rate-limiting-slice-3c`, on top of the merged
Slice 3b (`42529e3`, PR #14). Opened as **PR #15**, verified green on
GitHub Actions CI (3/3 checks) on the first push, merged into `main` as
squash commit `75dd466`.)*

Adds `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` to
`backend/app/core/audit.py` and a `_audit_abuse_escalation()` helper in
`backend/app/api/v1/auth.py`, called from `login`/`forgot-password`/
`reset-password` right after each abuse-state `record_*()` call — emits
`AuditEvent.RATE_LIMITED` for a `STRICT_THROTTLE` transition or
`AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` for a `TEMPORARY_BLOCK`
transition, exactly once per escalation, with metadata limited to
rule/operation/dimension, the already-HMAC-hashed account identifier
when account-scoped, and the block TTL — never a raw secret. No
abuse-decision production code (`abuse_decision.py`/`abuse_state.py`/
`rate_limit.py`) was modified. 6 new HTTP-level tests
(`backend/tests/test_abuse_audit.py`), real-Redis validated (6/6, 3
consecutive runs, alongside the complete 254-test suite) before this PR
was opened.

### 2026-09-20 — `feat: add abuse-decision engine and wire R1-R5 into auth endpoints` (906e2f9) + `test: clear abuse:* Redis keys between tests alongside rl:*` (46a2860) + docs (2896b1d), merged as `42529e3`

*(Branch `issue-redis-rate-limiting-slice-3b`, on top of the merged
Slice 3a (`026dcf3`, PR #13). Opened as **PR #14**, iterated once after
CI caught a real test-isolation gap, verified green on GitHub Actions CI
(3/3 checks) on the final push, merged into `main` as squash commit
`42529e3`.)*

Adds `backend/app/core/abuse_decision.py` (the deterministic R1–R5 rule
table, `check()`/four explicitly-named `record_*()` functions), one
additive primitive in `backend/app/core/abuse_state.py`
(`temporary_block_ttl_seconds()`), and `backend/app/core/token_bucket_types.py`
(`DimensionSpec`/`TokenBucketResult`, extracted from `rate_limit.py` to
break a real circular import this slice's wiring introduced —
`rate_limit.py` re-exports both names unchanged). Wires the engine into
`enforce_login_rate_limit`/`enforce_forgot_password_rate_limit`/
`enforce_reset_password_rate_limit` (`backend/app/core/rate_limit.py`)
and post-outcome recording into `login`/`forgot-password`/
`reset-password` (`backend/app/api/v1/auth.py`) — `register`/`refresh`
untouched. 33 tests (`backend/tests/test_abuse_decision.py`), real-Redis
validated (65/65 combined with the unaffected Slice 3a suite, 3
consecutive runs) before this PR was opened. A genuine test-isolation
gap in `backend/tests/conftest.py` (`_reset_rate_limiters` not sweeping
the new `abuse:*` keys) was found during validation, confirmed by CI
itself failing 3/248 on the first push, and fixed with a single-file,
minimal change before the final green push — the complete 248-test
backend suite passed 248/248, 3 consecutive runs, after the fix.

### 2026-09-19 — `feat: add Redis abuse state primitives` (676d7e5), merged as `026dcf3`

*(Branch `issue-redis-rate-limiting-slice-3a`, on top of the merged
Slice 2 (`5391a78`, PR #12). Opened as **PR #13**, verified green on
GitHub Actions CI (backend lint/typecheck/tests, frontend
lint/typecheck/tests/build, Docker build check), merged into `main` as
squash commit `026dcf3`.)*

Adds `backend/app/core/abuse_keys.py` (the `abuse:` Redis key namespace)
and `backend/app/core/abuse_state.py` (atomic Lua-scripted record/reset
primitives for R1–R5's counters, R3's distinct-IP HyperLogLog, the
strict-throttle bucket, and the temporary-block flag — reusing the
existing token-bucket engine for the strict bucket, no new engine).
Fully parameterized — no rule thresholds hardcoded. 32 tests
(`backend/tests/test_abuse_state.py`), real-Redis validated (32/32, 3
consecutive runs) before this PR was opened. No endpoint wiring —
`register`/`refresh`/`login`/`forgot-password`/`reset-password` remain
byte-for-byte unchanged from Slice 2 (that's Slice 3b, see
`[Unreleased — working tree]` above).

### 2026-09-18 — `feat: wire Redis rate limiting into auth endpoints` (f61737f), merged as `5391a78`

*(Branch `issue-redis-rate-limiting-slice-2`, on top of the merged Slice
1 (`46ef03b`, PR #11). Opened as **PR #12**, verified green on GitHub
Actions CI (3/3 checks: backend lint/typecheck/tests, frontend
lint/typecheck/tests/build, Docker build check), and **merged into
`main` as squash commit `5391a78`** — a single-parent squash merge
(parent `46ef03b`), so `f61737f` is not itself an ancestor of `5391a78`.
`main` and `origin/main` are both at `5391a78`. The
`issue-redis-rate-limiting-slice-2` branch was auto-deleted on `origin`
after the merge; it still exists as a stale local branch only.)*

Wires the Redis-backed engine built in Slice 1 into every
`enforce_*_rate_limit` dependency (`backend/app/core/rate_limit.py`),
per [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
§6/§9/§13. This **is** a real, observable change to every authentication
endpoint's rate-limiting behavior, now active in the committed codebase
on `main`:

- `register`, `login`, `refresh`, `forgot-password`, `reset-password` all
  now attempt `RedisTokenBucketLimiter` first, using ADR §9's exact
  per-operation dimensions (IP via the trusted-proxy-aware
  `resolve_client_ip()`; HMAC-hashed email for `login`/`forgot-password`'s
  account dimension; the refresh-token cookie's session ID — no DB
  lookup — for `refresh`), falling back to the existing
  `FixedWindowRateLimiter` per ADR §13's operation-aware policy.
- **Resolved one of ADR §13/§22's explicitly-open implementation
  decisions, with rationale recorded in the ADR, `SOLVING.md`, and code**:
  an *unconfigured* Redis (`REDIS_URL` unset — today's default
  everywhere) always falls back to the in-process limiter, for every
  operation including `register`; the ADR's literal Tier B fail-open is
  reserved for a genuine mid-request outage of an *already-configured*
  Redis. Implementing the literal default would have made `register`
  unprotected by default in every environment today.
- New `rate_limit_hash_key` setting (`backend/app/core/config.py`) —
  resolves ADR §14/§22's "HMAC key location" open decision by reusing
  `SECRET_KEY` unless explicitly overridden.
- Fixed a real test-isolation gap this wiring exposed: `conftest.py`'s
  `_reset_rate_limiters` fixture only reset the in-process limiters, not
  the `rl:*` Redis keys every test now writes through the live wiring —
  52 previously-passing tests failed until this was fixed. Full writeup
  in `SOLVING.md`.
- From this slice's own read-only security/architecture review (0 P0,
  3 P1, 3 P2, 2 P3 findings, all P1s and the important P2 fixed before
  commit): structured logging on the Redis-failure fallback path
  (`_log_redis_fallback()`, ADR §13's own requirement — `operation`/
  `policy` fields only, never a request-derived value); corrected stale
  docstrings in `redis_client.py`/`ip_resolution.py` ("not wired into any
  endpoint yet", false as of this slice); 8 additional HTTP-level tests
  covering `refresh`/`forgot-password`/`reset-password` Redis-key
  creation and Tier A fallback (previously only `login`/`register` had
  them), an endpoint-driven multi-dimension atomicity regression test for
  `login`, and a cross-user account-isolation test.
- 13 HTTP-level tests total (`backend/tests/test_rate_limit_wiring.py`,
  183 total up from 170): real-Redis key creation via live endpoint
  calls, Tier A/Tier B failure-policy behavior via dependency override,
  the unconfigured-vs-unreachable distinction, spoofed
  `X-Forwarded-For` ignored by default, endpoint-driven multi-dimension
  atomicity, cross-user isolation. `ruff`/`mypy` clean; full suite
  re-run 3 times with no flakiness (locally, against real Postgres +
  real Redis, immediately before this commit) and independently
  re-verified by GitHub Actions CI on PR #12 after push.
- Verified live against the real Docker Compose stack, in an earlier
  checkpoint before commit: inspected the exact Redis keys a live login
  created (`redis-cli --scan`), confirmed login capacity enforcement
  across a real session, confirmed `/api/v1/health/ready` stays
  independent of Redis, and exercised a genuine Redis outage and
  recovery mid-session — `register` failed open only during the outage,
  `login` still hit `429` via the fallback limiter during that same
  outage, and enforcement resumed automatically once Redis came back,
  with no process restart.
- Also reconciles `PROJECT_STATE.md`, `HANDOFF.md`, `docs/SECURITY.md`,
  and ADR 0006 to reflect that both Redis slices are now merged.
- Does **not** include the deterministic abuse-detection layer (ADR
  §11/§12) — still not started, see `HANDOFF.md`.

### 2026-09-15 — `feat: implement distributed Redis rate limiting foundation` (b1f1b00), merged as `46ef03b`

*(Branch `issue-redis-rate-limiting`. Reconciled with a documentation
checkpoint, `docs: reconcile Redis Slice 1 project state` (`c8aa2be`),
pushed, opened as **PR #11**, verified green on GitHub Actions CI (3/3
checks), and **merged into `main` as squash commit `46ef03b`** — a
single-parent squash merge (parent `7e439d2`), so `b1f1b00`/`c8aa2be`
are not themselves ancestors of `46ef03b`, but its tree content is
byte-identical to `c8aa2be`'s (`git diff c8aa2be 46ef03b` is empty).
`main` and `origin/main` are both at `46ef03b`. The `issue-redis-rate-limiting`
branch still exists locally and on `origin` (not auto-deleted) but has
no content not already in `main`; Slice 2 work continues on a new
branch, `issue-redis-rate-limiting-slice-2`, cut from the merged `main`.)*

Adds the Redis-backed distributed rate-limiting foundation designed in
ADR 0006 (§8/§10/§14), without wiring it into any endpoint yet: the
multi-key atomic Lua token-bucket engine (`RedisTokenBucketLimiter`,
`DimensionSpec`), a Redis connection abstraction with an exception-free
availability check, centralized rate-limit key construction with a
keyed-HMAC (not plain-hash) email identifier, and a trusted-proxy-aware
IP resolver (secure-by-default: `X-Forwarded-For` ignored unless the
peer is within a configured trusted CIDR). The existing in-process
`FixedWindowRateLimiter` and every `enforce_*_rate_limit` function are
byte-for-byte unchanged and remain what every endpoint actually uses —
still true as merged. Also adds the `redis` dependency, a pinned
`redis:7.4-alpine` Docker Compose/CI service, and 51 new tests (119 →
170) covering config validation, the Lua engine's atomicity/concurrency/
TTL/cost semantics (including the multi-key all-or-nothing regression
test for the partial-consumption race found during ADR review), and
trusted-proxy IP resolution. Independently validated in an isolated
worktree before the commit: 170/170 tests pass against real Postgres and
real Redis, `ruff`/`mypy` clean. Endpoint wiring (Slice 2) was
deliberately kept out of this PR — see the "implementation slice 2"
entry above for its own, separate status.

### 2026-09-14 — `feat: complete secure cookie auth and password recovery` (864d783)

*(GitHub Issue #2 checkpoint. Opened as PR #10, verified green on GitHub
Actions CI (3/3 checks), and merged into `main` as commit `ec4225d` — a
squash/rebase merge, so `ec4225d` has a single parent rather than being a
two-parent merge commit, but its tree content is byte-identical to
`864d783`. `main` and `origin/main` are both at `ec4225d`.)*

Migrates browser authentication from bearer tokens in the response body to
HttpOnly cookies with CSRF protection, and adds a complete password
recovery vertical slice, on top of the registration/login/workspace work
already in this branch:

- **Cookie + CSRF authentication** (supersedes the original
  response-body-token design): access/refresh tokens delivered exclusively
  via `HttpOnly` cookies (`access_token` on `Path=/`, `refresh_token`
  scoped to `Path=/api/v1/auth`) — never in a response body, never read by
  frontend JavaScript, no `localStorage`/`sessionStorage` token storage
  anywhere (`frontend/lib/auth-storage.ts` removed). Double-submit CSRF
  cookie (`csrf_token`, deliberately non-`HttpOnly`) + `X-CSRF-Token`
  header on every state-changing request, including login/register.
  Deployment-aware cookie/CORS configuration
  (`COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`/
  `CORS_ALLOWED_ORIGINS`), documented in new
  [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  including the "different origin ≠ cross-site" distinction that governs
  `COOKIE_SAMESITE`.
- **Password recovery** (backend + frontend): `/forgot-password` and
  `/reset-password` — cryptographically random, SHA-256-hashed-at-rest,
  single-use, expiring reset tokens; enumeration-resistant
  (identical response/timing regardless of whether the email exists); a
  successful reset revokes every existing session for the account. Email
  delivery via a new vendor-neutral `EmailProvider` abstraction (`console`
  dev fallback or `smtp`, verified locally against Mailpit).
  `ENVIRONMENT=production` with `EMAIL_PROVIDER=console` now fails at
  config-load time — a genuine defect found during a dedicated security
  audit of this feature (stdout is typically captured by log aggregation
  in real deployments, which would otherwise leak raw reset tokens into
  production logs).
- **Audit logging**: new `audit_logs` table and `AuditEvent` recording for
  authentication events, password-reset events, workspace membership
  changes, and authorization denials.
- **Docs**: `docs/SECURITY.md` corrected to match the current
  implementation (previously described bearer tokens and listed audit
  logging as not implemented).
- **Tests**: backend 95 → 119 pytest tests; frontend 30 → 48 vitest tests,
  including explicit regression tests proving no auth token ever reaches
  `localStorage`/`sessionStorage`/an `Authorization` header.
- **Verified end-to-end** against the real Docker Compose stack (now
  including a `mailpit` service): register → forgot-password → Mailpit
  received the email with a correct reset link → reset-password (CSRF
  matrix: missing rejected, valid accepted) → old password rejected, new
  password accepted → the pre-reset refresh token invalidated → zero
  occurrences of the raw reset token in backend logs.
- Two non-obvious problems solved during this checkpoint are written up in
  `SOLVING.md`: a rate-limiter test-isolation gap that made password-reset
  tests silently receive no email, and a Vitest fetch-mock `Response`
  object being reused across multiple calls in one test (causing "Body
  already read" errors).
- Does **not** include Redis-backed rate limiting, a deterministic
  abuse-detection layer, or Playwright E2E — all explicitly deferred; see
  `HANDOFF.md`.

### 2026-09-11 — `chore: configure Git line endings` (a059965)

- Added `.gitattributes` (`* text=auto eol=lf`).

### 2026-09-11 — `chore: initialize project architecture and documentation` (a7d81cf)

- Initial repository scaffold: empty placeholder docs (`AGENTS.md`,
  `CHANGELOG.md`, `CLAUDE.md`, `GEMINI.md`, `HANDOFF.md`,
  `PROJECT_STATE.md`, `SOLVING.md`, `START_HERE.md`, `docs/*.md`),
  `.env.example`, `.gitignore`.
