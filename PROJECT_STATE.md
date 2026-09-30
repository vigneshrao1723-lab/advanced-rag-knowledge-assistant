# PROJECT_STATE.md

**Last updated:** 2026-09-29
**Current phase:** GitHub Issues #1–#8 are all implemented, tested, and
merged to `main` — the full original 5-day plan is complete. A final
project-completion / requirements-audit / quality-hardening pass (not
tied to a specific numbered issue) is now **in progress**, working
directly on `main` — see "Immediate priorities". `main`/`origin/main`
are at `a4afb2e` (Issue #8's merge commit, PR #33) as of the point this
pass began.
(repository: `vigneshrao1723-lab/advanced-rag-knowledge-assistant`)

This is the authoritative, living snapshot of the project's real state. If
this file ever disagrees with the actual repository contents, the
repository wins — fix this file. For the exact commit-by-commit,
PR-by-PR history behind every item below, see `CHANGELOG.md`; this file
intentionally stays a condensed *current-state* snapshot rather than a
running narrative, to keep it honest and readable as the project grows.

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
| Conversations / chat | IMPLEMENTED (ask flow + history; no rewrite/regenerate/feedback) | #4/#5 — create conversation, post message (full retrieval+generation pipeline synchronously), list messages with real persisted citations. Not implemented: rename/delete/search conversations, regenerate/retry, feedback, conversational context/query rewriting across turns. |
| Product frontend (Documents, Chat) | IMPLEMENTED (primary flow) | #5/#8 — real `app/documents/page.tsx` (upload, live-polling status list, retry) and `app/chat/page.tsx` (conversation list, message thread, citations with click-to-inspect source text, voice controls), consuming the real backend APIs. `login/register/forgot-password/reset-password/dashboard/settings/workspace` also real. Deferred, documented, not forgotten: standalone document search UI, per-conversation/per-document deep-link routes, message feedback, rename/delete conversations. |
| Voice (STT/TTS) as a mode within chat | IMPLEMENTED | #6 — `PocketSphinxSpeechToTextProvider` (offline, empirically weaker accuracy against synthetic audio — honestly documented, not hidden) + `EspeakTextToSpeechProvider` (subprocess-based, after `pyttsx3` was found to corrupt state across calls). `POST .../voice-messages` calls the *exact same* `post_message()` the text flow uses — no duplicated pipeline. `GET .../messages/{id}/audio` synthesizes on demand, nothing persisted. See [ADR 0008](docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md). |
| Evaluation harness | IMPLEMENTED | #4/#7 — `evaluation_runs`/`evaluation_results` tables (migration `0008`); `eval/scripts/run_retrieval_evaluation.py` compares 4 retrieval methods × 2 chunking strategies against real Postgres. Real, non-fabricated results: dense/hybrid/hybrid+reranked reach Recall@3=1.0/MRR=1.0/nDCG@3=1.0/HitRate@3=1.0/Precision@3=0.33 on both chunking strategies; lexical-only is genuinely weaker (0.71 across those metrics). See `docs/EVALUATION.md`. |
| Observability / audit logging | IMPLEMENTED | #1/#2/#3/#7 — structured JSON logging, request-ID propagation, persistent `audit_logs` (auth/password-reset/workspace/document-lifecycle/`CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED` events), per-stage retrieval/generation latency + character-count token-usage-proxy structured logs (`caplog`-tested). |
| Testing (unit/integration/security) | IMPLEMENTED | Backend: **727/727 passing** (`ruff`/`mypy` clean) — the prior 5 `test_password_reset.py` failures were a real test-environment bug (the Docker Compose backend service's own `EMAIL_PROVIDER=smtp` default leaked into `docker compose run` test invocations, defeating the capsys-based reset-link capture those tests need), fixed by force-setting `EMAIL_PROVIDER=console` unconditionally in `backend/tests/conftest.py` — a hard test requirement, not an infra location that should vary by environment. Frontend: 71/71 vitest, `eslint`/`tsc --noEmit` clean, `next build` succeeds. Playwright: 20/20. |
| Browser E2E (Playwright) | IMPLEMENTED | `frontend/e2e/` — 20/20 tests passing (app availability, auth/session/CSRF/password-recovery, and `documents-chat.spec.ts`'s full upload→process→READY→chat→cited-answer flow) against a freshly rebuilt real Docker stack. Voice has no Playwright E2E (judged disproportionately expensive vs. real-device audio automation) but is fully unit/HTTP-level tested and was manually verified end-to-end via `curl`. |
| CI/CD (`.github/workflows/ci.yml`) | IMPLEMENTED | backend (lint/typecheck/pytest against real Postgres+Redis service containers, `espeak-ng` installed), frontend (lint/typecheck/vitest/build), e2e (Playwright against real services), docker-build (image builds + `docker compose config`) — all required, green on every merged PR #9–#32. |
| Docker / deployment (`infra/`) | IMPLEMENTED for local development | `infra/docker/*.Dockerfile`, `infra/compose/docker-compose.yml` (db/redis/mailpit/backend/frontend). A real hosting/production target is a deliberate, undecided scope boundary — see `docs/DEPLOYMENT.md` "Target deployment environment" and CLAUDE.md §4 (this is exactly the kind of infrastructure decision this project stops and asks a human about). |
| Skills system (`.agents/skills/`) | PARTIALLY IMPLEMENTED | Roster documented (`.agents/skills/README.md`); individual skill procedures not yet written. |
| Standalone search (outside chat), collections | PLANNED | No code. |

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

Issues #1–#8 are done and merged to `main` (`a4afb2e`). A final
project-completion / requirements-audit / quality-hardening pass is in
progress:

1. Fixed the real cause of `test_password_reset.py`'s 5 failures
   (backend now 727/727) and two deprecation warnings — see `SOLVING.md`.
2. Implemented source inspection end-to-end (backend endpoint, frontend
   UI, tests at every layer) after finding it was genuinely missing
   despite prior documentation implying otherwise.
3. Ran an independent background requirements audit across every spec
   area — clean except one finding (`.env.example` completeness), fixed.
4. Fixed `.env.example` completeness and a real, latent config-loading
   bug (`env_ignore_empty=True`) found while verifying that fix — see
   `SOLVING.md`.
5. Full regression (backend 727/727, frontend 71/71, Playwright 20/20,
   `ruff`/`mypy`/`eslint`/`tsc` clean, Docker/Alembic verified) — all
   green, against a freshly rebuilt stack.
6. Remaining: commit this work on a feature branch, push, open a PR,
   confirm CI green, merge — following the same workflow used for every
   prior issue.

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5. Keep this file a condensed *current-state* snapshot;
detailed historical narrative (exact commits, PR numbers, test counts per
slice) belongs in `CHANGELOG.md`, not here.
