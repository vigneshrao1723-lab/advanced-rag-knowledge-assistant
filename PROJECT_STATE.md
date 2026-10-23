# PROJECT_STATE.md

**Last updated:** 2026-10-23  
**Current phase:** 72-hour release sprint — complete. The frontend design pass (PR #38, merged on top of PR #37's CI fixes) is now in `main`: shared indigo/slate design tokens, vertically centered auth screens, a real documents drag-and-drop dropzone, a fully redesigned chat experience (sidebar, bubbles, citations, feedback, playback, a mobile composer-wrap fix), dashboard quick actions with real counts, and settings/workspace polish — including a real post-merge fix (the Active Sessions list was showing the raw User-Agent string instead of a human-readable device label). `main`/`origin/main` are at the commit recorded in the "Immediate priorities" section below.

This is the authoritative living snapshot. The current repository contents and latest test runs take precedence over old counts in this file. The current main baseline, re-verified fresh after every merge: backend 759 passed + 1 intentional skip, frontend 91/91, Playwright 21/21, with ruff/mypy/eslint/TypeScript/build checks clean.

**Feature-completion sprint (started 2026-10-23, [Issue #41](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/41)):** Collections (priority 1 of 7) is now implemented — see the Component status table and `docs/REQUIREMENTS_MATRIX.md` §1. The remaining six items (search, document viewer, regenerate/retry, document management, command palette, recursive chunking) are tracked there, not yet started.

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
| Generation & citations | IMPLEMENTED | #4 — `build_context()` (budgeted, deduped, order-preserving), `LocalGroundedExtractiveProvider` (grounded by construction — quotes evidence, never paraphrases beyond it), `create_citations()`. No-evidence-found returns an honest fixed answer, zero citations, never fabricated content. |
| Conversations / chat | IMPLEMENTED (ask flow + history + rename/delete/feedback; no regenerate/retry) | #4/#5 — create conversation, post message (full retrieval+generation pipeline synchronously), list messages with real persisted citations. Rename (`PATCH`)/delete (`DELETE`) conversations and message feedback (`PUT .../feedback`, `UP`/`DOWN`, `messages.feedback` migration `0009`) added in the final quality-hardening pass, closing a real Issue #5 "Chat" requirement gap — all workspace/role/IDOR-tested (cross-workspace, cross-conversation, VIEWER-cannot-mutate). Search conversations is a client-side title filter over the already-fetched list (no backend endpoint needed). Not implemented: regenerate/retry a response, conversational context/query rewriting across turns — both deliberately deferred as lower-value relative to effort. |
| Product frontend (Documents, Chat) | IMPLEMENTED (primary flow, design-polished) | #5/#8 + 72-hour design sprint (PRs #37/#38) — real `app/documents/page.tsx` (drag-and-drop dropzone, format/size guidance, icon status badges, upload, live-polling status list, retry) and `app/chat/page.tsx` (card-framed conversation list with search/rename/delete, message thread, citations with click-to-inspect source text, thumbs-up/down feedback, voice controls, a composer that wraps correctly on mobile), consuming the real backend APIs. `login/register/forgot-password/reset-password` share a new vertically-centered `AuthShell`. `dashboard` has quick-action cards plus real (never fabricated) document/conversation counts. `settings/workspace` are icon-polished; Settings' session list shows a parsed device label (e.g. "Chrome on Linux") instead of the raw User-Agent string. One shared indigo/slate design-token update (`globals.css`) makes every shadcn-based page consistent with the landing page/nav. Deferred, documented, not forgotten: standalone document search UI, collections, command palette, per-conversation/per-document deep-link routes, a full in-document citation viewer beyond source inspection, regenerate/retry. |
| Voice (STT/TTS) as a mode within chat | IMPLEMENTED | #6 — `PocketSphinxSpeechToTextProvider` (offline, empirically weaker accuracy against synthetic audio — honestly documented, not hidden) + `EspeakTextToSpeechProvider` (subprocess-based, after `pyttsx3` was found to corrupt state across calls). `POST .../voice-messages` calls the *exact same* `post_message()` the text flow uses — no duplicated pipeline. `GET .../messages/{id}/audio` synthesizes on demand, nothing persisted. See [ADR 0008](docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md). |
| Evaluation harness | IMPLEMENTED | #4/#7 — `evaluation_runs`/`evaluation_results` tables (migration `0008`); `eval/scripts/run_retrieval_evaluation.py` compares 4 retrieval methods × 2 chunking strategies against real Postgres. Real, non-fabricated results: dense/hybrid/hybrid+reranked reach Recall@3=1.0/MRR=1.0/nDCG@3=1.0/HitRate@3=1.0/Precision@3=0.33 on both chunking strategies; lexical-only is genuinely weaker (0.71 across those metrics). See `docs/EVALUATION.md`. |
| Observability / audit logging | IMPLEMENTED | #1/#2/#3/#7 — structured JSON logging, request-ID propagation, persistent `audit_logs` (auth/password-reset/workspace/document-lifecycle/`CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED` events), per-stage retrieval/generation latency + character-count token-usage-proxy structured logs (`caplog`-tested). |
| Testing (unit/integration/security) | IMPLEMENTED | Backend: **759 passing, 1 intentional skip** (`ruff`/`mypy` clean) — the 1 skip is a regression test that only applies against a full repository checkout (CI/host), not inside the Docker image, which deliberately excludes everything outside `backend/`; re-confirmed passing (not skipped) when run on the host against the real `.env.example`. Frontend: **91/91** vitest, `eslint`/`tsc --noEmit` clean, `next build` succeeds. Playwright: **21/21**. |
| Browser E2E (Playwright) | IMPLEMENTED | `frontend/e2e/` — 20/20 tests passing (app availability, auth/session/CSRF/password-recovery, and `documents-chat.spec.ts`'s full upload→process→READY→chat→cited-answer flow) against a freshly rebuilt real Docker stack. Voice has no Playwright E2E (judged disproportionately expensive vs. real-device audio automation) but is fully unit/HTTP-level tested and was manually verified end-to-end via `curl`. |
| CI/CD (`.github/workflows/ci.yml`) | IMPLEMENTED | backend (lint/typecheck/pytest against real Postgres+Redis service containers, `espeak-ng` installed), frontend (lint/typecheck/vitest/build), e2e (Playwright against real services), docker-build (image builds + `docker compose config`) — all required, green on every merged PR #9–#32. |
| Docker / deployment (`infra/`) | IMPLEMENTED for local development | `infra/docker/*.Dockerfile`, `infra/compose/docker-compose.yml` (db/redis/mailpit/backend/frontend). Uploaded documents now persist across a backend container recreate via a named volume (`backend_documents`, matching `db_data`'s pattern — see `SOLVING.md` 2026-10-23). A real hosting/production target is a deliberate, undecided scope boundary — see `docs/DEPLOYMENT.md` "Target deployment environment", `docs/PRODUCTION_READINESS.md`, and CLAUDE.md §4 (this is exactly the kind of infrastructure decision this project stops and asks a human about). |
| Collections | IMPLEMENTED | Issue #41 — `collections`/`collection_documents` schema (migration `0010`), workspace-role-gated CRUD + document association API (`app/api/v1/collections.py`), real `app/collections/page.tsx`/`[id]/page.tsx` (create/list/rename/delete, add/remove documents). 15 backend + 9 frontend tests, plus an 11-step real-browser verification (create → add document → reload and confirm persistence → remove → rename → delete). See `docs/REQUIREMENTS_MATRIX.md` §1. |
| Skills system (`.agents/skills/`) | PARTIALLY IMPLEMENTED | Roster documented (`.agents/skills/README.md`); individual skill procedures not yet written. |
| Standalone search (outside chat) | PLANNED | No code. |

## Known limitations

- Search (standalone retrieval without generation) does not exist —
  retrieval is only reachable through the chat/ask flow today.
- Voice's real-world speech-recognition accuracy is materially weaker than
  a modern hosted/neural ASR system, especially against synthetic
  (TTS-generated) audio — an accepted, honestly documented limitation of
  `PocketSphinxSpeechToTextProvider`, not a defect. See
  [ADR 0008](docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md).
- Evaluation numbers (`eval/results/retrieval_evaluation.json`,
  `evaluation_runs`/`evaluation_results`) describe a small deterministic
  fixture document set and this project's current local/deterministic
  providers only — not production-scale quality. Any future retrieval/
  generation quality claim must come from an actual run recorded under
  `eval/results/`/`evaluation_runs` — never fabricated.
- Chunking-strategy comparison covers two strategies (structure-aware, a
  naive fixed-size baseline); a `recursive` third strategy and a
  size/overlap sweep are not implemented. The eval fixture's documents are
  each short enough to become exactly one chunk under either chunker, so
  the two currently produce identical retrieval metrics on that fixture —
  an artifact of fixture scale, not a claim the chunkers are equivalent in
  general.
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

The 72-hour release sprint that began 2026-10-23 is complete. PR #37 (CI
fixes + landing page/nav) and PR #38 (the full design pass: auth
centering, documents dropzone, chat redesign, dashboard, mobile fix)
are both merged. A small follow-on fix (Active Sessions showing a raw
User-Agent string instead of a human-readable device label, found via
live visual QA) has also been applied and verified.

A full requirements audit against Issues #1–#8 confirmed every issue's
core, demonstrable scope is implemented, tested, and working
end-to-end — see each issue's closing comment on GitHub for the
PR-referenced evidence. Genuinely remaining, all explicitly deferred
with a reason (not silently dropped):

- **Standalone retrieval/search UI** — retrieval is only reachable
  through the chat/ask flow; `/search` is an honest `PageStub`.
- **Command palette** (`Ctrl+K`) — not built.
- **Full in-document citation viewer with contextual highlighting** —
  source inspection (viewing the exact cited chunk's text) is
  implemented; a document-wide viewer with in-context highlighting is
  not. `/documents/[id]` is an honest `PageStub`.
- **Regenerate/retry a response** — not implemented.
- **Document management beyond list/get/upload/process** — no
  filter/sort/search/rename/delete/download endpoints for documents
  (conversations have rename/delete; documents do not).
- **A `recursive` chunking strategy** — only `structure-aware` (the
  real pipeline's own strategy) and a `fixed-size` naive baseline
  (evaluation-comparison only) exist.
- **A decided production hosting target** — deliberately not invented;
  per `CLAUDE.md` §4 this is a real infrastructure decision for a human.
  Local Docker Compose is the fully-verified, fully-supported way to
  run this project today.

None of the above blocks the project's core, demonstrated success
criteria (see `docs/PROJECT_BRIEF.md` "Success criteria" — all 5 are
genuinely true and re-verified this sprint). Do not describe any item
in the list above as done.

**Feature completion sprint (started 2026-10-23, tracked as
[Issue #41](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/41)):**
every item in the list above now has a full, evidence-based entry
(status, acceptance criteria, dependencies/risks, effort/priority, next
slice) in [`docs/REQUIREMENTS_MATRIX.md`](docs/REQUIREMENTS_MATRIX.md).
Update that file, not this list, as each item actually ships — this
section stays a condensed pointer.

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5. Keep this file a condensed *current-state* snapshot;
detailed historical narrative (exact commits, PR numbers, test counts per
slice) belongs in `CHANGELOG.md`, not here.
