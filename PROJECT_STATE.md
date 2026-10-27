# PROJECT_STATE.md

**Last updated:** 2026-10-27  
**Current phase:** Feature-completion sprint (Issue #41) — complete. All 7 items (Collections, Standalone search, full document viewer, answer regeneration, document management, command palette, recursive chunking) are merged into `main`. Before this, the 72-hour release sprint (PRs #37/#38: shared indigo/slate design tokens, vertically centered auth screens, documents drag-and-drop dropzone, redesigned chat experience, dashboard quick actions, settings/workspace polish) had already shipped. `main`/`origin/main` are at `4a17a38` (PR #49, merged 2026-10-24).

This is the authoritative living snapshot. The current repository contents and latest test runs take precedence over old counts in this file.

**Release audit (2026-10-27, [Issue #50](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/50)):** `main` was re-verified from scratch against a fresh Docker Compose stack (see `docs/PRODUCTION_READINESS.md` "Release audit"). Two defects were found and fixed (PR #51, merged as `6a6e44e`): non-Latin-1 download filenames returned 500, and the document filename filter treated `%`/`_` as wildcards. A larger evaluation fixture was added. Several limitations were verified but deliberately **not** changed (no relevance gate before generation, Redis-outage event-loop stall, near-dead lexical search for natural-language questions, no security response headers) — they are listed under "Known limitations" and need an owner decision. **The project is not declared production-ready:** no production target exists, and those limitations plus the backup/domain/secrets work in `docs/PRODUCTION_READINESS.md` remain open.

Test baseline verified in the audit: backend 825 passed + 2 skipped inside the Docker image (13 of those are new tests added by the audit; the skips are the intentional full-checkout `.env.example` test and the new fixture-validity module, both of which need a repository checkout and pass on the host), frontend 113/113 (lint/tsc/build clean), Playwright 21/21, `ruff`/`mypy` clean.

**Feature-completion sprint (started 2026-10-23, [Issue #41](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/41)):** All 7 items — Collections, Standalone search, the full document viewer, answer regeneration, document management, the command palette, and recursive chunking — are now implemented. See the Component status table and `docs/REQUIREMENTS_MATRIX.md` §1–7.

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
| Generation & citations | IMPLEMENTED | #4 — `build_context()` (budgeted, deduped, order-preserving), `LocalGroundedExtractiveProvider` (grounded by construction — quotes evidence, never paraphrases beyond it), `create_citations()`. The fixed no-evidence answer (zero citations) is returned only when retrieval returns **no chunks at all** (e.g. an empty workspace). There is **no relevance threshold**: an off-topic question in a non-empty workspace still gets a "Based on the available documents…" answer built from the nearest chunks, with citations (verified live and in the large eval fixture, 3/3 unanswerable queries) — a known limitation, see "Known limitations". The answer is never fabricated beyond the retrieved text. |
| Conversations / chat | IMPLEMENTED (ask flow + history + rename/delete/feedback/regenerate) | #4/#5/#41 — create conversation, post message (full retrieval+generation pipeline synchronously), list messages with real persisted citations. Rename (`PATCH`)/delete (`DELETE`) conversations and message feedback (`PUT .../feedback`, `UP`/`DOWN`, `messages.feedback` migration `0009`) added in the final quality-hardening pass. Regenerate (`POST .../regenerate`, Issue #41) re-runs retrieval+generation for an assistant message's original question, replacing its content/citations in place and clearing prior feedback. All workspace/role/IDOR-tested (cross-workspace, cross-conversation, VIEWER-cannot-mutate). Search conversations is a client-side title filter over the already-fetched list (no backend endpoint needed). Not implemented: conversational context/query rewriting across turns — deliberately deferred as lower-value relative to effort. |
| Product frontend (Documents, Chat) | IMPLEMENTED (primary flow, design-polished) | #5/#8 + 72-hour design sprint (PRs #37/#38) — real `app/documents/page.tsx` (drag-and-drop dropzone, format/size guidance, icon status badges, upload, live-polling status list, retry, and — as of Issue #41 — rename/delete/download and a filename-search/status-filter UI) and `app/chat/page.tsx` (card-framed conversation list with search/rename/delete, message thread, citations with click-to-inspect source text plus a "View in document" deep link, thumbs-up/down feedback, a "Regenerate" control, voice controls, a composer that wraps correctly on mobile), consuming the real backend APIs. `login/register/forgot-password/reset-password` share a new vertically-centered `AuthShell`. `dashboard` has quick-action cards plus real (never fabricated) document/conversation counts. `settings/workspace` are icon-polished; Settings' session list shows a parsed device label (e.g. "Chrome on Linux") instead of the raw User-Agent string. One shared indigo/slate design-token update (`globals.css`) makes every shadcn-based page consistent with the landing page/nav. Collections (`app/collections/page.tsx`/`[id]/page.tsx`), standalone search (`app/search/page.tsx`), the full document viewer (`app/documents/[id]/page.tsx`), and a global command palette (`components/command-palette.tsx`, mounted in `AppShell`) were added in the feature-completion sprint (Issue #41) — see their own rows below. Deferred, documented, not forgotten: the `/chat/[id]` deep-link route. |
| Voice (STT/TTS) as a mode within chat | IMPLEMENTED | #6 — `PocketSphinxSpeechToTextProvider` (offline, empirically weaker accuracy against synthetic audio — honestly documented, not hidden) + `EspeakTextToSpeechProvider` (subprocess-based, after `pyttsx3` was found to corrupt state across calls). `POST .../voice-messages` calls the *exact same* `post_message()` the text flow uses — no duplicated pipeline. `GET .../messages/{id}/audio` synthesizes on demand, nothing persisted. See [ADR 0008](docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md). |
| Evaluation harness | IMPLEMENTED | #4/#7/#41 — `evaluation_runs`/`evaluation_results` tables (migration `0008`); `eval/scripts/run_retrieval_evaluation.py` compares 4 retrieval methods × 3 chunking strategies (structure-aware, fixed-size, recursive) against real Postgres (12 persisted runs). Real, non-fabricated results: dense/hybrid/hybrid+reranked reach Recall@3=1.0/MRR=1.0/nDCG@3=1.0/HitRate@3=1.0/Precision@3=0.33 on all three chunking strategies; lexical-only is genuinely weaker (0.71 across those metrics). See `docs/EVALUATION.md`. |
| Observability / audit logging | IMPLEMENTED | #1/#2/#3/#7 — structured JSON logging, request-ID propagation, persistent `audit_logs` (auth/password-reset/workspace/document-lifecycle/`CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED` events), per-stage retrieval/generation latency + character-count token-usage-proxy structured logs (`caplog`-tested). |
| Testing (unit/integration/security) | IMPLEMENTED | Backend: **812 passing, 1 intentional skip** (`ruff`/`mypy` clean) — the 1 skip is a regression test that only applies against a full repository checkout (CI/host), not inside the Docker image, which deliberately excludes everything outside `backend/`; re-confirmed passing (not skipped) when run on the host against the real `.env.example`. Frontend: **113/113** vitest, `eslint`/`tsc --noEmit` clean, `next build` succeeds. Playwright: **21/21**. |
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

- Voice's real-world speech-recognition accuracy is materially weaker than
  a modern hosted/neural ASR system, especially against synthetic
  (TTS-generated) audio — an accepted, honestly documented limitation of
  `PocketSphinxSpeechToTextProvider`, not a defect. See
  [ADR 0008](docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md).
- **No relevance gate**: off-topic questions get an answer with citations
  instead of "I don't have enough information" (see Generation row). With
  the local hashing embedder no similarity cutoff separates on- from
  off-topic queries (measured), so a fix needs a content-word-overlap gate
  or a real embedding model — an owner decision.
- **Redis outage can stall the API** when the Redis hostname stops
  resolving (each rate-limited request ~4 s; `/health` blocked 3.4 s),
  because the sync Redis call runs on the event loop and DNS is outside the
  50 ms socket timeouts. Running without `REDIS_URL` on a single instance
  avoids it; a proper fix changes ADR 0006's failure policy.
- **Lexical search AND-semantics**: `plainto_tsquery` returned 0 chunks for
  14 of 16 natural-language eval questions, so hybrid ≈ dense-only.
- **No security response headers** (nosniff, frame-ancestors, referrer
  policy, HSTS/CSP); `/docs` and `/openapi.json` are public in production
  mode; 0-byte uploads are accepted then end `FAILED`; 429s have no
  `Retry-After`. Details: `docs/PRODUCTION_READINESS.md`.
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
  structure-aware and recursive are still indistinguishable. All numbers
  come from local deterministic providers — no real LLM or embedding model
  has ever been evaluated, so faithfulness and prompt-injection resistance
  of a real LLM are unmeasured.
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

**After the 2026-10-27 audit:** the single next action is the owner's
hosting decision (`docs/PRODUCTION_READINESS.md` "Recommendation": Option A,
single Droplet + Compose + Caddy, is the recommended choice; Options B/C are
the alternatives). Separately, decide whether to fix the relevance-gate and
Redis-outage findings before real users depend on answers.

The 72-hour release sprint that began 2026-10-23 is complete. PR #37 (CI
fixes + landing page/nav) and PR #38 (the full design pass: auth
centering, documents dropzone, chat redesign, dashboard, mobile fix)
are both merged. A small follow-on fix (Active Sessions showing a raw
User-Agent string instead of a human-readable device label, found via
live visual QA) has also been applied and verified.

A full requirements audit against Issues #1–#8 confirmed every issue's
core, demonstrable scope is implemented, tested, and working
end-to-end — see each issue's closing comment on GitHub for the
PR-referenced evidence. Genuinely remaining, explicitly deferred with a
reason (not silently dropped):

- **A decided production hosting target** — deliberately not invented;
  per `CLAUDE.md` §4 this is a real infrastructure decision for a human.
  Local Docker Compose is the fully-verified, fully-supported way to
  run this project today.

None of the above blocks the project's core, demonstrated success
criteria (see `docs/PROJECT_BRIEF.md` "Success criteria" — all 5 are
genuinely true and re-verified this sprint). Do not describe the item
above as done.

**Feature completion sprint (started 2026-10-23, tracked as
[Issue #41](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/41)):**
all 7 items now have a full, evidence-based `COMPLETE` entry (status,
acceptance criteria, dependencies/risks, effort/priority, next slice)
in [`docs/REQUIREMENTS_MATRIX.md`](docs/REQUIREMENTS_MATRIX.md). The
only scope remaining under Issue #41 is the production-deployment
decision above, which is explicitly a human decision, not an
implementation gap.

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5. Keep this file a condensed *current-state* snapshot;
detailed historical narrative (exact commits, PR numbers, test counts per
slice) belongs in `CHANGELOG.md`, not here.
