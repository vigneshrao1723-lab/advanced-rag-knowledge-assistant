# PROJECT_STATE.md

**Last updated:** 2026-10-28  
**Current phase:** Owner-acceptance fixes ([Issue #53](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/53)) — implementation complete on `main` (`24bfd77`), **awaiting the owner's hands-on acceptance**. The owner tested the app and found it not release-ready: document questions returned raw PDF text, speech recognition was inaccurate, and there was no conversational voice. Cycles 1–4 (PRs #54–#57) address those; they are verified by automated tests and by real-model/real-browser runs, **not yet by the owner**. Do not call the product ready until they confirm.

This is the authoritative living snapshot. The current repository contents and latest test runs take precedence over old counts in this file.

**What changed (2026-10-28):** (1) answers are now written by a real language model (`LLM_PROVIDER=openai_compatible`; free local Ollama is the documented default, ADR 0009) instead of printing retrieved passages; with no model the chat says so (503 + banner) and never falls back to excerpts. (2) Questions that name things now resolve before the model runs: "Program N", "the first/last program", file names ("my PC lab PDF") and follow-ups find the item's complete span; an absent item gets a deterministic reply listing what exists; off-topic questions get the fixed no-evidence answer (the audit's "no relevance gate" finding is fixed). (3) PDF extraction keeps code indentation; answers' code blocks are verified against the document and the original listing is appended; "line by line" is assembled structurally. (4) Lexical search ORs query words (the audit's "near-dead lexical search" finding is fixed). (5) Speech: local Whisper (faster-whisper) replaces PocketSphinx as the Compose default (ADR 0010), dictation puts the transcript in the editable box for review before sending, workspace vocabulary hints. (6) A separate turn-based **Voice conversation** mode with spoken answers (ADR 0011) — explicitly not full-duplex realtime.

**Verified this phase (2026-10-28):** backend 981 passed + 2 skipped inside the image (the skips need a repository checkout and pass on the host; the opt-in real-model STT tests ran and passed), `ruff`/`mypy` clean; frontend 181/181, lint/tsc/build clean; Playwright 21/21 against the live stack with the real model; the 30-check headless-browser UI regression 29/30 (the one non-pass is the expected pre-login 401); real headless-Chromium voice runs with a fake microphone fed from audio files (dictation, silence, cancel, full conversation loop with the real Whisper model and real LLM). **Not verified by anyone yet:** real human voices/accents/microphones/speakers, Windows browser speech voices, answer quality of the 3B model on the owner's own documents.

Repository: vigneshrao1723-lab/advanced-rag-knowledge-assistant.

## Status legend

`IMPLEMENTED` · `PARTIALLY IMPLEMENTED` · `PLANNED` · `PROPOSED` ·
`EXPERIMENTAL` · `DEPRECATED` · `BLOCKED`

## Current architecture

A modular-monolith FastAPI backend (PostgreSQL + pgvector, Redis) and a
Next.js/TypeScript frontend, per `docs/ARCHITECTURE.md` and
[ADR 0001](docs/DECISIONS/0001-modular-monolith-over-microservices.md).
End-to-end today: register/login → create a workspace → upload a document
(PDF/DOCX/TXT/Markdown/CSV) → it processes through the full ingestion
pipeline to `READY` → ask a question by text or voice in Chat → hybrid
(dense + lexical, RRF-fused, reranked) retrieval finds evidence → grounded
generation returns an answer with citations → the answer can be played
back as speech. Workspace isolation, audit logging, Redis-backed rate
limiting + deterministic abuse detection, and a real persisted evaluation
harness comparing retrieval configurations all run alongside this. Every
embedding/reranking/generation/STT/TTS provider is a local, deterministic,
offline implementation — no paid API key required (see ADRs 0007, 0008).

## Component status

| Component | Status | Issue |
|---|---|---|
| Documentation architecture (`START_HERE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `PROJECT_STATE.md`, `HANDOFF.md`, `SOLVING.md`, `CHANGELOG.md`, `docs/*`) | IMPLEMENTED | ongoing |
| `docs/DECISIONS/` ADR log | IMPLEMENTED | 8 ADRs: modular monolith (0001), Postgres/pgvector (0002), auth/session architecture (0003), Argon2id (0004), HttpOnly cookie + CSRF (0005), Redis rate limiting + abuse protection (0006), local providers for embedding/reranking/generation (0007), local STT/TTS providers (0008) |
| Application foundation (config, structured logging, request-ID middleware, error handling, SQLAlchemy + Alembic, health/readiness, CI, Docker Compose) | IMPLEMENTED | #1 |
| Authentication & sessions | IMPLEMENTED | #2 — Argon2id, JWT access tokens + PostgreSQL-backed sessions with refresh rotation/reuse-detection, HttpOnly cookies only (never `localStorage`/`Authorization` header), double-submit CSRF, password recovery (enumeration-resistant, single-use hashed tokens, revokes all sessions on reset). See [ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md)/[ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md). |
| Workspaces | IMPLEMENTED | #2 — CRUD, membership, four-role matrix (OWNER/ADMIN/MEMBER/VIEWER), `require_workspace_role` enforced server-side on every scoped route, last-owner protection. |
| Redis distributed rate limiting + deterministic abuse detection | IMPLEMENTED | ADR 0006 — every `enforce_*_rate_limit` dependency attempts the Redis token-bucket engine first, falls back to an in-process limiter. R1–R5 abuse rules (strict-throttle/temporary-block escalation) wired into login/forgot-password/reset-password, audited. |
| Document upload & ingestion pipeline (`UPLOADED → ... → READY`) | IMPLEMENTED | #3 — upload (format/size/checksum validation, dedup, storage-then-DB ordering), synchronous extraction → cleaning → structure-aware chunking → embedding (`LocalHashingEmbeddingProvider`, 384-dim) → pgvector HNSW indexing, all crash-safe (each stage commits before the next begins), resumable from any non-terminal status. |
| Retrieval (dense / lexical / fusion / reranking) | IMPLEMENTED | #4 — `dense_search()` (pgvector cosine), `lexical_search()` (Postgres FTS), `reciprocal_rank_fusion()` (RRF, k=60), `LexicalOverlapReranker`; `hybrid_search()` is the orchestrating entry point, workspace-scoped and READY-only at the SQL level, records a `RetrievalEvent` per call. |
| Generation & citations | IMPLEMENTED (real model required) | #4 → ADR 0009 — `OpenAICompatibleLLMProvider` (local Ollama / any OpenAI-style server; hosted only by explicit config) writes explanation-style answers with `[n]` citations; `LocalGroundedExtractiveProvider` remains the code default for tests/CI/offline eval only and is not an assistant. No evidence → fixed answer without calling the model. Evidence is delivered in a delimited, source-labelled block (untrusted-data boundary); citations are limited to what the model cited; a code-fidelity guard verifies/repairs code blocks against the document and appends the original listing; "line by line" is assembled by the system. Unreachable/misconfigured model → `503 llm_unavailable` (question withdrawn, no silent fallback). Measured on a 3B local model: correct program-level explanations, but occasional factual slips in prose — see `docs/EVALUATION.md` "Real-model checks". |
| Conversations / chat | IMPLEMENTED (ask flow + history + rename/delete/feedback/regenerate) | #4/#5/#41 — create conversation, post message (full retrieval+generation pipeline synchronously), list messages with real persisted citations. Rename (`PATCH`)/delete (`DELETE`) conversations and message feedback (`PUT .../feedback`, `UP`/`DOWN`, `messages.feedback` migration `0009`) added in the final quality-hardening pass. Regenerate (`POST .../regenerate`, Issue #41) re-runs retrieval+generation for an assistant message's original question, replacing its content/citations in place and clearing prior feedback. All workspace/role/IDOR-tested (cross-workspace, cross-conversation, VIEWER-cannot-mutate). Search conversations is a client-side title filter over the already-fetched list (no backend endpoint needed). Not implemented: conversational context/query rewriting across turns — deliberately deferred as lower-value relative to effort. |
| Product frontend (Documents, Chat) | IMPLEMENTED (primary flow, design-polished) | #5/#8 + 72-hour design sprint (PRs #37/#38) — real `app/documents/page.tsx` (drag-and-drop dropzone, format/size guidance, icon status badges, upload, live-polling status list, retry, and — as of Issue #41 — rename/delete/download and a filename-search/status-filter UI) and `app/chat/page.tsx` (card-framed conversation list with search/rename/delete, message thread, citations with click-to-inspect source text plus a "View in document" deep link, thumbs-up/down feedback, a "Regenerate" control, voice controls, a composer that wraps correctly on mobile), consuming the real backend APIs. `login/register/forgot-password/reset-password` share a new vertically-centered `AuthShell`. `dashboard` has quick-action cards plus real (never fabricated) document/conversation counts. `settings/workspace` are icon-polished; Settings' session list shows a parsed device label (e.g. "Chrome on Linux") instead of the raw User-Agent string. One shared indigo/slate design-token update (`globals.css`) makes every shadcn-based page consistent with the landing page/nav. Collections (`app/collections/page.tsx`/`[id]/page.tsx`), standalone search (`app/search/page.tsx`), the full document viewer (`app/documents/[id]/page.tsx`), and a global command palette (`components/command-palette.tsx`, mounted in `AppShell`) were added in the feature-completion sprint (Issue #41) — see their own rows below. Deferred, documented, not forgotten: the `/chat/[id]` deep-link route. |
| Voice (dictation + conversation) | IMPLEMENTED — owner acceptance pending | #6 → ADR 0010/0011 — local Whisper STT (`faster_whisper`, installed once by `infra/scripts/setup-local-stt.sh`, never downloaded during a request; PocketSphinx remains the code default), `POST …/transcriptions` (transcription only), review-before-send dictation, workspace vocabulary hint, silent/too-short checks, device and language choice; a turn-based **Voice conversation** (listen → transcribe → ask → speak → listen) with Stop-speaking/End, local browser voices else server espeak, code never read aloud. **Not full-duplex realtime.** Only synthetic speech through a real browser capture path was tested; human voices are untested. |
| Evaluation harness | IMPLEMENTED | #4/#7/#41 — `evaluation_runs`/`evaluation_results` tables (migration `0008`); `eval/scripts/run_retrieval_evaluation.py` compares 4 retrieval methods × 3 chunking strategies (structure-aware, fixed-size, recursive) against real Postgres (12 persisted runs). Real, non-fabricated results: dense/hybrid/hybrid+reranked reach Recall@3=1.0/MRR=1.0/nDCG@3=1.0/HitRate@3=1.0/Precision@3=0.33 on all three chunking strategies; lexical-only is genuinely weaker (0.71 across those metrics). See `docs/EVALUATION.md`. |
| Observability / audit logging | IMPLEMENTED | #1/#2/#3/#7 — structured JSON logging, request-ID propagation, persistent `audit_logs` (auth/password-reset/workspace/document-lifecycle/`CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED` events), per-stage retrieval/generation latency + character-count token-usage-proxy structured logs (`caplog`-tested). |
| Testing (unit/integration/security) | IMPLEMENTED | Backend: **981 passed, 2 skipped** inside the Docker image (hermetic: `conftest` forces the deterministic providers; the 2 skips need a repository checkout and pass on the host; 4 opt-in real-model STT tests pass with the model installed), `ruff`/`mypy` clean. On a bare host 5 tests fail only because `espeak-ng` is not installed. Frontend: **181/181** vitest, `eslint`/`tsc --noEmit` clean, `next build` succeeds. Playwright: **21/21**. |
| Browser E2E (Playwright) | IMPLEMENTED | `frontend/e2e/` — 21/21 tests passing (app availability, auth/session/CSRF/password-recovery, and `documents-chat.spec.ts`'s full upload→process→READY→chat→cited-answer flow) against a freshly rebuilt real Docker stack. The Issue #41 UI (collections, search page, document viewer, document management, regenerate, command palette) has **no committed Playwright spec**: it was verified by a one-off headless-Chromium script in the 2026-10-27 audit (29/30 checks; the one non-pass is the expected pre-login 401) and manually in earlier sessions. A committed spec was not added because the existing specs already use 4 of the 5-per-minute registration tokens (rate limiter) — it should extend an existing logged-in session instead of registering again. Voice has no Playwright E2E (judged disproportionately expensive vs. real-device audio automation) but is fully unit/HTTP-level tested and was manually verified end-to-end via `curl`. |
| CI/CD (`.github/workflows/ci.yml`) | IMPLEMENTED | backend (lint/typecheck/pytest against real Postgres+Redis service containers, `espeak-ng` installed), frontend (lint/typecheck/vitest/build), e2e (Playwright against real services), docker-build (image builds + `docker compose config`) — all required, green on every merged PR #9–#32. |
| Docker / deployment (`infra/`) | IMPLEMENTED for local development | `infra/docker/*.Dockerfile`, `infra/compose/docker-compose.yml` (db/redis/mailpit/backend/frontend). Uploaded documents now persist across a backend container recreate via a named volume (`backend_documents`, matching `db_data`'s pattern — see `SOLVING.md` 2026-10-23). A real hosting/production target is a deliberate, undecided scope boundary — see `docs/DEPLOYMENT.md` "Target deployment environment", `docs/PRODUCTION_READINESS.md`, and CLAUDE.md §4 (this is exactly the kind of infrastructure decision this project stops and asks a human about). |
| Collections | IMPLEMENTED | Issue #41 — `collections`/`collection_documents` schema (migration `0010`), workspace-role-gated CRUD + document association API (`app/api/v1/collections.py`), real `app/collections/page.tsx`/`[id]/page.tsx` (create/list/rename/delete, add/remove documents). 15 backend + 9 frontend tests, plus an 11-step real-browser verification (create → add document → reload and confirm persistence → remove → rename → delete). See `docs/REQUIREMENTS_MATRIX.md` §1. |
| Standalone search (outside chat) | IMPLEMENTED | Issue #41 — `GET /workspaces/{id}/search` (retrieval only, never calls generation, reuses the same `hybrid_search()` chat uses), real `app/search/page.tsx` replacing its `PageStub`. 8 backend + 3 frontend tests (ranked results, cross-workspace isolation, auth/role checks, rate limiting, `RetrievalEvent` recorded with null conversation/message). See `docs/REQUIREMENTS_MATRIX.md` §2. |
| Full document viewer + citation highlighting | IMPLEMENTED | Issue #41 — `GET /workspaces/{id}/documents/{id}/chunks` (ordered, additive to the existing per-chunk source-inspection endpoint), real `app/documents/[id]/page.tsx` replacing its `PageStub`, with `?chunk=` highlight-and-scroll-to; the chat citation chip now links there (`CitationSource`'s "View in document"), and the Documents list now links each filename to its viewer. 5 backend + 4 frontend tests, plus a full real-browser verification of the citation → viewer → highlighted-chunk flow. See `docs/REQUIREMENTS_MATRIX.md` §3. |
| Answer regeneration | IMPLEMENTED | Issue #41 — `POST /workspaces/{id}/conversations/{id}/messages/{id}/regenerate` re-runs retrieval+generation for an assistant message's original question, replacing its content/citations in place (same message id, no new row) and clearing any prior feedback. A "Regenerate" button on each assistant message in `app/chat/page.tsx`. 8 backend + 1 frontend test, plus a full real-browser verification (rate an answer → regenerate → confirm it's still grounded and the rating was cleared). See `docs/REQUIREMENTS_MATRIX.md` §4. |
| Document management (rename/delete/download/filter/search) | IMPLEMENTED | Issue #41 — `PATCH`/`DELETE`/`GET .../download` on `/workspaces/{id}/documents/{id}`, plus `?status=`/`?q=` filter/search on the list endpoint. Real rename/delete/download controls and a search/status-filter UI on `app/documents/page.tsx`. Document delete cascades its chunks/citations (a documented decision — see `docs/API_CONTRACT.md` "Document delete") but never affects a chat message's own text content. 17 backend + 5 frontend tests, plus a full real-browser verification (upload → rename → search → filter → download with byte-for-byte content verification → delete). See `docs/REQUIREMENTS_MATRIX.md` §5. |
| Command palette | IMPLEMENTED | Issue #41 — `frontend/components/command-palette.tsx`, mounted once in `AppShell`: a visible trigger button plus `Ctrl+K`/`Cmd+K`, filterable actions for every real route and a dynamic switch-workspace action per other workspace. No new dependency. 9 component tests, plus a full real-browser verification (trigger button, `Ctrl+K` while a text input has focus — confirmed its content is unaffected, filter + arrow-key + Enter navigation, outside-click close, `Escape` close, a real workspace switch). See `docs/REQUIREMENTS_MATRIX.md` §6. |
| Recursive chunking strategy | IMPLEMENTED | Issue #41 — `RecursiveChunker` (`backend/app/ingestion/chunking.py`), a third comparison-only chunking strategy using a fixed, universal separator list (paragraph → line → sentence → word → hard character cut), unlike `StructureAwareChunker`'s per-extractor heuristics; still never merges across `ExtractedSection`s. Real ingestion is unaffected (still `StructureAwareChunker` exclusively). Wired into `eval/scripts/run_retrieval_evaluation.py`'s 3-way comparison and re-run against real Postgres (12 persisted `evaluation_runs`). 15 backend unit tests. See `docs/REQUIREMENTS_MATRIX.md` §7. |
| Skills system (`.agents/skills/`) | PARTIALLY IMPLEMENTED | Roster documented (`.agents/skills/README.md`); individual skill procedures not yet written. |

## Known limitations

- **Answer quality depends on the model.** The default local model
  (qwen2.5:3b-instruct on a 4 GB GPU) explains short programs well but makes
  occasional factual slips in prose, a short overview can misread the question,
  and "line by line" only works because the system splits the code. Code shown
  is verified against the document; prose is not. A larger/hosted model is
  better (`docs/AI_SETUP.md`). Prompt-injection resistance of the real model was
  checked only with generic injection text.
- **Documents ingested before 2026-10-28 keep the old (flattened) code** in
  their stored chunks; re-upload them to get indentation-preserving extraction.
- **Voice is unproven with real people.** Whisper small is far better than the
  old engine but still mishears technical words ("bubble sort" → "verbal sort"
  without the workspace hint); human accents, noisy rooms, real microphones and
  Windows/Chrome speech voices have not been measured. Voice conversation is
  turn-based, has no barge-in, and each turn takes seconds (STT ≈ 3 s + answer
  7–17 s). Energy-based turn detection can be fooled by steady loud noise.
- **Deployment footprint grew sharply** (measured): the backend holds ≈ 1.2 GiB
  with Whisper loaded (was ≈ 0.12), the local LLM needs ≈ 2.3 GB of GPU memory,
  and the images are 2.3 GB (backend) and 8.5 GB (Ollama). The earlier
  single-small-VPS hosting recommendation no longer fits unless the LLM is a
  hosted API — see `docs/PRODUCTION_READINESS.md` "Deployment impact".
- **Redis outage can stall the API** when the Redis hostname stops
  resolving (each rate-limited request ~4 s; `/health` blocked 3.4 s),
  because the sync Redis call runs on the event loop and DNS is outside the
  50 ms socket timeouts. Running without `REDIS_URL` on a single instance
  avoids it; a proper fix changes ADR 0006's failure policy.
- **No security response headers** (nosniff, frame-ancestors, referrer
  policy, HSTS/CSP); `/docs` and `/openapi.json` are public in production
  mode; 0-byte uploads are accepted then end `FAILED`; 429s have no
  `Retry-After`. Details: `docs/PRODUCTION_READINESS.md`.
- Relevance gate limits: it only applies to the hashing embedder and cannot
  rescue a paraphrase that shares no word with the evidence (the embedder's own
  limit). A real embedder should set `semantic = True`.
- Evaluation numbers (`eval/results/retrieval_evaluation.json`,
  `evaluation_runs`/`evaluation_results`) describe a small deterministic
  fixture document set and this project's current local/deterministic
  providers only — not production-scale quality. Any future retrieval/
  generation quality claim must come from an actual run recorded under
  `eval/results/`/`evaluation_runs` — never fabricated.
- Chunking-strategy comparison now covers three strategies (structure-
  aware, a naive fixed-size baseline, and a recursive-separator-list
  baseline); a chunk-size/overlap sweep is not implemented. The eval
  fixture's documents are each short enough to become exactly one chunk
  under any of the three chunkers, so all three currently produce
  identical retrieval metrics on that fixture — an artifact of fixture
  scale, not a claim the chunkers are equivalent in general. A second,
  larger synthetic fixture (`--fixture large`, 8 documents / 19 queries,
  `eval/results/retrieval_evaluation_large.json`) does separate them, but
  only on three queries engineered to straddle the fixed-size window edge;
  structure-aware and recursive are still indistinguishable. The retrieval
  numbers come from local deterministic providers; generation with a real
  local model was only hand-inspected (`docs/EVALUATION.md` "Real-model
  checks"), not scored — faithfulness and prompt-injection resistance are
  unmeasured.
- Concurrency/race-condition behavior of the Redis token-bucket engine is
  tested against a real Redis instance at the unit level; behavior
  *through a real endpoint under genuinely concurrent multi-process HTTP
  load* has not been tested — no multi-instance deployment of this project
  exists to test the distributed-coordination property against under real
  concurrent traffic from more than one backend process.
- The backend's CORS policy (`CORS_ALLOWED_ORIGINS`) defaults to
  `http://localhost:3000`; a genuinely cross-site production deployment
  needs the explicit configuration in
  [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md),
  not yet exercised against a real deployment target since none is decided.
- Access-token revocation on logout/session-revoke/password-reset is
  bounded by the token's short TTL (`ACCESS_TOKEN_EXPIRE_MINUTES`, default
  15 minutes), not immediate — a deliberate trade-off in
  [ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md),
  not a defect.
- No real hosting/production deployment target has been decided — see
  `docs/DEPLOYMENT.md` "Target deployment environment."

## Immediate priorities

1. **Owner acceptance** of the Issue #53 work — follow the checklist in
   `HANDOFF.md`. If anything fails, report the step and what you saw; do not
   treat CI or the automated runs above as acceptance.
2. After acceptance: the hosting decision (`docs/PRODUCTION_READINESS.md`,
   including the new "Deployment impact" section: a production deployment now
   needs a hosted OpenAI-compatible LLM or a GPU host, and ≥ 4 GiB RAM for the
   backend with local Whisper).
3. Known follow-ups, not started: streaming answers (lower voice latency),
   re-processing of existing documents, security headers, the Redis-outage
   event-loop stall, a committed Playwright spec for the newer UI.

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5. Keep this file a condensed *current-state* snapshot;
detailed historical narrative (exact commits, PR numbers, test counts per
slice) belongs in `CHANGELOG.md`, not here.
