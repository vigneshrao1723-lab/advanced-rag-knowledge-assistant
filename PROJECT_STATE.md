# PROJECT_STATE.md

**Last updated:** 2026-09-22
**Current phase:** GitHub Issue #2 (Authentication & Workspaces) and the
full Redis distributed rate limiting + deterministic abuse-protection
layer (ADR 0006, Slices 1–3c) are **merged to `main`.** Browser E2E
coverage (Playwright) for authentication/password-recovery is also
**merged to `main`** — PR #16, squash commit `e1c4858`. GitHub Issue #3
(Knowledge Ingestion): **Slice 3.1 (document data model + migration) is
merged** — PR #17, squash commit `79d4787`. **Slice 3.2 (`StorageProvider`
abstraction) is merged** — PR #18, squash commit `941c1a7`. **Slice 3.2's
own pre-merge correctness/security review (a real gap: raw filesystem
errors/paths could escape the module) landed as a follow-up fix, also
merged** — PR #19, squash commit `5e6fdc2`. **Slice 3.3 (document upload
API) is merged** — PR #20, squash commit `a6762e2`, merged by the
repository owner. **`main`/`origin/main` are currently at `a6762e2`.**
**Slice 3.4 (text extraction) is IMPLEMENTED, TESTED, and on branch
`issue-3-slice-3-4-text-extraction`, not yet committed/pushed/PR'd** —
see "Component status" and "Immediate priorities" below, and
`HANDOFF.md` for exact detail. (repository:
`vigneshrao1723-lab/advanced-rag-knowledge-assistant`, currently checked
out on `issue-3-slice-3-4-text-extraction`)

This is the authoritative, living snapshot of the project's real state. If
this file ever disagrees with the actual repository contents, the repository
wins — fix this file.

**Committed and merged baseline:** the documentation/project-memory system
(`START_HERE.md`, `AGENTS.md`, etc.), `docs/DECISIONS/0001`–`0003`, and the
entire Issue #1 Application Foundation are merged to `main` (PR #9). Issue
#2 — Authentication & Workspaces, including the HttpOnly cookie + CSRF
authentication migration, password recovery (backend and frontend), audit
logging, and `docs/DECISIONS/0004`–`0005` — was implemented on branch
`issue-2-authentication-workspaces` (checkpoint commit `864d783`), opened
as **PR #10**, verified green on GitHub Actions CI (3/3 checks: backend
lint/typecheck/tests, frontend lint/typecheck/tests/build, Docker build
check), and **merged into `main` as commit `ec4225d`** — a squash/rebase
merge, so `ec4225d` has a single parent rather than being a two-parent
merge commit, but its tree content was verified byte-identical to the
approved `864d783` (`git diff 864d783 ec4225d` is empty). Issue #2 merged
into `main` at `ec4225d`; `main`/`origin/main` subsequently advanced
further via the ADR 0006 design-finalization commit (`7e439d2`, committed
directly to `main` in an earlier session) and then via Redis **Slice 1**
— implemented on branch `issue-redis-rate-limiting` (checkpoint commit
`b1f1b00`, documentation-reconciled as `c8aa2be`), opened as **PR #11**,
and **merged into `main` as squash commit `46ef03b`**. Redis **Slice 2**
(wiring that engine into every `enforce_*_rate_limit` dependency) was
then implemented on a fresh branch, `issue-redis-rate-limiting-slice-2`,
cut from the merged `main` (checkpoint commit `f61737f`), opened as
**PR #12**, verified green on GitHub Actions CI (3/3 checks), and
**merged into `main` as squash commit `5391a78`**. The deterministic
abuse-detection layer then landed in three further slices, each its own
branch/PR/squash-merge: Slice 3a (**PR #13**, squash commit `026dcf3`),
Slice 3b (**PR #14**, squash commit `42529e3`), Slice 3c (**PR #15**,
squash commit `75dd466`). Browser E2E coverage for authentication/
password-recovery (Playwright) followed on branch
`playwright-e2e-auth-validation`, opened as **PR #16**, and **merged into
`main` as squash commit `e1c4858`**. GitHub Issue #3 Slice 3.1 (document
data model + migration `0004`) was implemented on branch
`issue-3-slice-3-1-document-schema`, cut from `e1c4858`, opened as
**PR #17**, verified green on GitHub Actions CI (4/4 checks: backend
lint/typecheck/tests, frontend lint/typecheck/tests/build, Docker build
check, Playwright E2E), and **merged into `main` as squash commit
`79d4787`**. GitHub Issue #3 Slice 3.2 (`StorageProvider` abstraction)
was implemented on branch `issue-3-slice-3-2-storage-provider`, cut from
`79d4787`, opened as **PR #18**, verified green on GitHub Actions CI
(4/4 checks), and **merged into `main` as squash commit `941c1a7`**. A
correctness/security review of Slice 3.2 (raw filesystem errors/paths
could escape `StorageProvider`) landed its fix *after* PR #18 had
already been merged, on branch
`issue-3-slice-3-2-storage-error-handling-fix`, opened as **PR #19**,
verified green on GitHub Actions CI (4/4 checks), and **merged into
`main` as squash commit `5e6fdc2`**. **`main`/`origin/main` are
currently at `5e6fdc2`.** GitHub Issue #3 Slice 3.3 (document upload
API) was implemented on branch
`issue-3-slice-3-3-document-upload-api`, cut from `5e6fdc2`, opened as
**PR #20**, and **merged into `main` as squash commit `a6762e2`** by the
repository owner. **`main`/`origin/main` are currently at `a6762e2`.**
GitHub Issue #3 Slice 3.4 (text extraction) is implemented on branch
`issue-3-slice-3-4-text-extraction`, cut from `a6762e2` — not yet
committed/pushed/PR'd as of this line; see `HANDOFF.md` for exact
detail. The old
`issue-redis-rate-limiting`,
`issue-redis-rate-limiting-slice-2`, and other merged feature branches
were deleted on `origin` after their respective merges
(auto-delete-on-merge); some still exist as stale local branches only.
The old feature branch (`issue-2-authentication-workspaces`) still
exists locally and on `origin` (not deleted) but has no content not
already in `main`. Statuses like `IMPLEMENTED` describe content that
exists on disk and has been verified to run/pass; see `CHANGELOG.md` for
the exact commit history.

## Status legend

`IMPLEMENTED` · `PARTIALLY IMPLEMENTED` · `PLANNED` · `PROPOSED` ·
`EXPERIMENTAL` · `DEPRECATED` · `BLOCKED`

## Current architecture

The Application Foundation (Issue #1, merged) provides the FastAPI backend
skeleton, Next.js frontend, PostgreSQL + pgvector, Docker Compose, and CI.
Authentication & Workspaces (Issue #2, **merged**) adds the first real
feature vertical slice on top of it: registration/login/logout/refresh/
session management, HttpOnly-cookie + CSRF browser authentication,
password recovery, workspace CRUD/membership/roles, and audit logging —
enforced server-side end to end. Browser E2E coverage (Playwright) for
the authentication/password-recovery flows is merged. GitHub Issue #3
(Knowledge Ingestion): Slice 3.1 (merged) adds the
`documents`/`document_chunks` database schema (migration `0004`); Slice
3.2 (merged) adds the `StorageProvider` abstraction; Slice 3.3 (merged,
PR #20, `a6762e2`) adds the document upload endpoint
(`POST /api/v1/workspaces/{workspace_id}/documents`); Slice 3.4
(implemented, not yet merged) adds synchronous text extraction
(`POST .../documents/{document_id}/process`) — documents now reach
`PARSED` or `FAILED`; no chunking, embedding, retrieval, generation,
chat, search, or voice exists yet. Redis distributed rate limiting's
foundation and endpoint wiring are **both implemented, committed, and
merged into `main`** — Slice 1 (`46ef03b`, PR #11) and Slice 2
(`5391a78`, PR #12) — see the dedicated component-status row below. Every
`enforce_*_rate_limit` dependency now actually attempts the Redis-backed
engine in the committed codebase. The deterministic
abuse-detection layer does not exist yet — see "Known limitations."

## Component status

| Component | Status | Notes |
|---|---|---|
| Documentation architecture (`START_HERE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `PROJECT_STATE.md`, `HANDOFF.md`, `SOLVING.md`, `CHANGELOG.md`, `docs/*`) | IMPLEMENTED | Kept current with each checkpoint per `CLAUDE.md` §5. |
| `docs/DECISIONS/` ADR log | IMPLEMENTED | Six ADRs: modular monolith (0001), Postgres/pgvector (0002), authentication/session architecture (0003), Argon2id password hashing (0004), HttpOnly cookie + CSRF authentication (0005), Redis distributed rate limiting + deterministic abuse protection (0006 — **design only**; see the dedicated row below). |
| `.gitignore` / `.gitattributes` / `.env.example` | IMPLEMENTED | Placeholders only, no real secrets. Documents `SECRET_KEY` (required), `COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`, `FRONTEND_URL`, `EMAIL_PROVIDER`/`SMTP_*`. |
| GitHub remote & issues | IMPLEMENTED | Remote configured (`origin` → `vigneshrao1723-lab/advanced-rag-knowledge-assistant`). Real, filed GitHub issues `#1`–`#8` exist (confirmed via `gh issue list`): `#1` Application Foundation (merged, PR #9), `#2` Authentication & Workspaces (**merged, PR #10 → `main` commit `ec4225d`**), `#3` Knowledge Ingestion (not started), `#4` Hybrid RAG Pipeline, `#5` Product Experience, `#6` Voice, `#7` Evaluation/Security/Observability, `#8` CI/CD/Deployment/Finalization. Separate from these, `AGENTS.md` §9 documents a finer-grained `#1`–`#43` **internal planning baseline** — the two numbering schemes don't map 1:1. |
| Backend application (`backend/`) | IMPLEMENTED | Config, structured logging, request-ID middleware, centralized error handling, SQLAlchemy + Alembic, health/readiness (Issue #1) — plus (Issue #2) auth/workspace/password-recovery/audit-logging services, repositories, schemas, API routes, HttpOnly-cookie + CSRF middleware, plus (Redis Slices 1–2, both **merged into `main`** — `46ef03b` via PR #11, `5391a78` via PR #12) the Redis-backed token-bucket engine **and** its wiring into every `enforce_*_rate_limit` dependency — described in the "Distributed rate limiting" row below. Verified: GitHub Actions CI (3/3 checks: backend lint/typecheck/tests, frontend lint/typecheck/tests/build, Docker build check) passed for PR #12 before merge. Locally, `ruff`/`mypy` clean; the last full local `pytest` run against real Postgres + real Redis was **183/183 passing** (re-run 3 times, no flakiness) — from immediately before this repository's Docker/WSL integration became unavailable, on the exact code now merged (no Python file changed since). |
| Frontend application (`frontend/`) | IMPLEMENTED | Next.js 16 + TypeScript, Tailwind v4, shadcn/ui. `chat/collections/documents/evaluations/search` remain stub routes (later issues); `login/register/forgot-password/reset-password/dashboard/settings/workspace` are real, backed by `lib/auth-context.tsx` + `lib/workspace-context.tsx` + `lib/api-client.ts`. Authentication is cookie-only — see the "Authentication" row. Verified: `eslint` clean, `tsc --noEmit` clean, `vitest` **48/48 passing**, `next build` succeeds. |
| Database schema / migrations | IMPLEMENTED (for the scope built so far) | `0001` enables `pgvector` (Issue #1); `0002` adds `users`, `sessions`, `workspaces`, `workspace_members`; `0003` adds `password_reset_tokens` and `audit_logs` (Issue #2); `0004` adds `documents`/`document_chunks` (Issue #3 Slice 3.1, schema only — PR #17, not yet merged) — all verified applied and reversible against the real database, including an explicit downgrade/upgrade cycle for `0004`. Remaining `docs/DATA_MODEL.md` entities (`collections`, `conversations`, etc.) land with the features that need them. |
| Authentication | IMPLEMENTED | Registration, login, logout, Argon2id password hashing ([ADR 0004](docs/DECISIONS/0004-password-hashing-argon2id.md)), JWT access tokens + PostgreSQL-backed sessions with refresh rotation and reuse-detection revocation ([ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md)), session/device listing and revocation. **Tokens are delivered exclusively via HttpOnly cookies** (`access_token` on `Path=/`, `refresh_token` narrowly scoped to `Path=/api/v1/auth`) — never in a response body, never in an `Authorization` header, never read or stored by frontend JavaScript (no `localStorage`/`sessionStorage` token storage anywhere). CSRF protected via a double-submit cookie (`csrf_token`, deliberately non-`HttpOnly`) + `X-CSRF-Token` header on every state-changing request, including login/register. Cookie attributes (`COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`) and CORS (`CORS_ALLOWED_ORIGINS`, credentialed) are deployment-aware, not hardcoded for local dev. Full model, including the "different origin ≠ cross-site" distinction: [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md). **Password recovery** (backend + frontend) is implemented: `/forgot-password` and `/reset-password` pages; cryptographically random (256-bit), SHA-256-hashed-at-rest, single-use, expiring reset tokens; enumeration-resistant (identical response/timing for known vs. unknown email); a successful reset revokes every existing session for that user. Email delivery via a vendor-neutral `EmailProvider` abstraction (`console` dev fallback or `smtp`, e.g. Mailpit locally) — `ENVIRONMENT=production` with `EMAIL_PROVIDER=console` fails at config-load time rather than risk raw tokens reaching production logs via stdout capture. Audit logging (`app/core/audit.py`) records auth events, password-reset events, workspace membership changes, and authorization denials. Per-endpoint rate limiting (see "Known limitations" — still in-process, not yet Redis-backed). `backend/app/{core/security.py,core/cookies.py,core/csrf.py,core/rate_limit.py,core/audit.py,services/auth_service.py,services/password_reset_service.py,services/email_provider.py,api/v1/auth.py}`; frontend: `frontend/lib/{api-client.ts,auth-context.tsx,csrf.ts,schemas.ts}`, `frontend/app/{login,register,forgot-password,reset-password}/`. |
| Workspaces | IMPLEMENTED | CRUD, membership, four-role authorization matrix (OWNER/ADMIN/MEMBER/VIEWER — see `docs/API_CONTRACT.md`), server-side `require_workspace_role` dependency enforced on every workspace-scoped route, last-owner protection, audit-logged membership/role changes. `backend/app/{services/workspace_service.py,api/v1/workspaces.py,core/dependencies.py}`. Frontend: `/register`, `/login`, `/dashboard`, `/settings`, `/workspace` are real. |
| Document upload & ingestion pipeline | PARTIALLY IMPLEMENTED (upload + text extraction) | **Slice 3.1 — MERGED** (`79d4787`, PR #17): `documents`/`document_chunks` tables (migration `0004`) — a native `DocumentStatus` enum matching the documented lifecycle, workspace-scoped ownership and cascade delete, `UNIQUE(workspace_id, checksum_sha256)`/`UNIQUE(storage_key)`/`UNIQUE(document_id, chunk_index)` constraints. Deliberately no embedding column yet (see `docs/DATA_MODEL.md`). **Slice 3.2 — MERGED** (`941c1a7`, PR #18, plus its own correctness-review fix, `5e6fdc2`, PR #19): `StorageProvider` abstraction (`backend/app/services/storage_provider.py`) — a `Protocol` plus `LocalStorage`, path-traversal-safe (including symlink escapes), every operation guarding its own filesystem calls so no raw `OSError`/path ever escapes the module. **Slice 3.3 — MERGED** (`a6762e2`, PR #20): `POST /api/v1/workspaces/{workspace_id}/documents` (`backend/app/api/v1/documents.py`, `app/services/document_service.py`) — MEMBER-role-gated upload, extension/MIME/magic-byte validation (PDF/DOCX/TXT/MD/CSV only), a 50 MiB size limit enforced while streaming, SHA-256 checksum, workspace-scoped duplicate detection (`409`), storage-then-database ordering with a best-effort compensating delete on any DB failure after a successful storage write, a dedicated `document_upload` Redis rate-limit dimension (IP + user, Tier A, 20/60s), and `AuditEvent.DOCUMENT_UPLOADED`. **Slice 3.4 — IMPLEMENTED, TESTED, not yet committed/pushed/PR'd**: `POST .../documents/{document_id}/process` (`backend/app/ingestion/extraction.py`, `app/services/document_service.py::process_document`) — synchronous text extraction for the same five formats, moving `UPLOADED`/`PROCESSING`/`FAILED` to `PARSED` or `FAILED`. A pre-flight ZIP archive-safety check (member count/per-member/total uncompressed size/traversal) gates DOCX before `python-docx` ever runs; PDF page count and all formats' extracted-text size are capped; the `PROCESSING` transition commits as its own transaction before extraction runs (crash safety — see `HANDOFF.md`); a parsing failure is recorded as `FAILED` with a generic reason and returned as an ordinary `200`, never a `500`. A dedicated `document_process` Redis rate-limit dimension (same shape as upload) and `AuditEvent.DOCUMENT_PARSED`/`DOCUMENT_PARSING_FAILED`. **No chunking, embedding, vector indexing, or background/queued processing exists** — those are later slices. See `HANDOFF.md` for exact branch/commit detail. |
| Retrieval (dense / BM25 / hybrid / rerank) | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Generation & citations | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Conversations / chat | PLANNED | No code. |
| Search interface | PLANNED | No code. |
| Voice (STT/TTS) | PLANNED | Explicitly scoped to come after text RAG works; no code. |
| Evaluation harness | PLANNED | Metrics and methodology documented in `docs/EVALUATION.md`; **no evaluation has been run, no numbers exist.** |
| Distributed rate limiting / abuse protection (Redis) | Design: **DESIGNED**. Slice 1: **IMPLEMENTED, COMMITTED, PUSHED, MERGED** (`46ef03b`, PR #11). Slice 2: **IMPLEMENTED, COMMITTED, PUSHED, MERGED** (`5391a78`, PR #12). Abuse layer Slice 3a (Redis primitives): **IMPLEMENTED, REAL-REDIS VALIDATED, COMMITTED, PUSHED, MERGED** (`026dcf3`, PR #13). Abuse layer Slice 3b (decision engine + endpoint wiring): **IMPLEMENTED, REAL-REDIS VALIDATED, TEST-ISOLATION FIXED, COMPLETE-SUITE PASSING, COMMITTED, PUSHED, MERGED** (`42529e3`, PR #14). Abuse layer Slice 3c (abuse-escalation audit emission + HTTP-level test coverage): **IMPLEMENTED, REAL-REDIS VALIDATED, UNCOMMITTED** (working tree only; 6 new HTTP-level tests plus the complete 254-test backend suite — 3 consecutive runs against a real Redis + real PostgreSQL, all passing; **not** a production validation — see `HANDOFF.md` for exact method/evidence). | [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md) documents the full architecture; its "Implementation status" table tracks exact per-component Designed/Implemented/Tested/Committed/Production-validated state. **Slice 1 — merged into `main` as `46ef03b`** added the foundation: the `redis` Python dependency; Redis settings (`REDIS_URL`, socket timeouts, `TRUSTED_PROXY_CIDRS`) in `app/core/config.py`; a connection abstraction (`app/core/redis_client.py`); a centralized key-builder + HMAC-SHA256 email identifier (`app/core/redis_keys.py`); a trusted-proxy IP-resolution function (`app/core/ip_resolution.py`, ADR §9a); the multi-key atomic Lua token-bucket engine (`RedisTokenBucketLimiter`/`DimensionSpec` in `app/core/rate_limit.py`, ADR §8/§10 — one Lua `EVAL` per operation over all of that operation's dimension keys, all-or-nothing); and a `redis` service in `infra/compose/docker-compose.yml`/CI. **Slice 2 — merged into `main` as `5391a78`** wires all of it into every `enforce_*_rate_limit` dependency: `register`, `login`, `refresh`, `forgot-password`, `reset-password` now all attempt the Redis engine first (using `resolve_client_ip()` for IP, HMAC-hashed email for `login`/`forgot-password`'s account dimension, the refresh-token cookie's session ID for `refresh`), falling back to `FixedWindowRateLimiter` per ADR §13. **This is now active in the committed (`main`) codebase.** Also adds the `rate_limit_hash_key`/`RATE_LIMIT_HASH_KEY` setting the HMAC construction uses, structured logging on the Redis-failure fallback path (ADR §13's requirement, `_log_redis_fallback()`), and corrected the two stale "not wired into any endpoint yet" docstrings from Slice 1. `/api/v1/health/ready` still deliberately does not check Redis (ADR §13, unchanged). Tested: 170 tests committed with Slice 1, 13 additional HTTP-level tests committed with Slice 2 — **183 total, on `main`** — see `HANDOFF.md` for exact numbers and what remains (the deterministic abuse layer). **Slice 3a — merged into `main` as `026dcf3` (PR #13) — added the abuse layer's low-level Redis primitives**: `app/core/abuse_keys.py` (the `abuse:` key namespace) and `app/core/abuse_state.py` (atomic Lua-scripted record/reset operations for R1–R5's counters, R3's distinct-IP HyperLogLog, the strict-throttle bucket, and the temporary-block flag — reusing the existing `RedisTokenBucketLimiter`/`DimensionSpec` machinery for the strict bucket, no new engine). Real-Redis validated (32/32, 3 consecutive runs) before merge. **Slice 3b — merged into `main` as `42529e3` (PR #14) — added the deterministic decision engine**: `app/core/abuse_decision.py` (`check()`/`record_login_failure()`/`record_login_success()`/`record_forgot_password_request()`/`record_reset_validation_failure()`, a module-level R1–R5 rule table, `AbuseContext`/`AbuseDecision`/`AbuseRecordOutcome`) plus the one additive Slice 3a primitive it needed (`temporary_block_ttl_seconds()`), wired into `enforce_login_rate_limit`/`enforce_forgot_password_rate_limit`/`enforce_reset_password_rate_limit` (`app/core/rate_limit.py`) and the `login`/`forgot-password`/`reset-password` endpoints (`app/api/v1/auth.py`, post-outcome recording only — never in the pre-request dependency). `register`/`refresh` remain byte-for-byte unchanged (no rule targets them). A new `app/core/token_bucket_types.py` holds `DimensionSpec`/`TokenBucketResult`, extracted from `rate_limit.py` to break a genuine import cycle (`rate_limit.py` → `abuse_decision.py` → `abuse_state.py` → `rate_limit.py`) discovered while wiring this slice — `rate_limit.py` still re-exports both names unchanged, so no other call site needed to change. 33 new tests (`backend/tests/test_abuse_decision.py`) plus the unaffected 32 from Slice 3a — **65/65 passed 3 consecutive times against a real Redis and real PostgreSQL**, run inside the `compose-backend-1` container (the host shell's published-port path remained broken this session too). `ruff`/`mypy` clean (81 source files, host and container). **A genuine test-infrastructure gap was found and then fixed**: `tests/conftest.py`'s `_reset_rate_limiters` swept `rl:*` between tests but not the new `abuse:*` keys, so a full-suite run could accumulate real R4 state across the shared default test-client IP, causing 2 pre-existing `test_password_reset.py` tests and (in CI, with a different test-execution order) `test_rate_limit_wiring.py`'s forgot-password test to fail — reproduced from a freshly flushed Redis, confirmed via CI itself failing 3/248 for this exact reason on PR #14. **Fixed with a minimal, single-file change** extending the existing `rl:*` pattern-delete loop to also sweep `abuse:*`, under the same `RedisError` tolerance already in place — no production code touched. After the fix, the **complete 248-test backend suite passed 248/248, 3 consecutive runs** (real Postgres + real Redis, inside `compose-backend-1`), and CI confirmed 3/3 green on PR #14 before human merge. **Slice 3c (uncommitted, working-tree-only) adds abuse-escalation audit emission**: `app/api/v1/auth.py`'s `_audit_abuse_escalation()` helper emits `AuditEvent.RATE_LIMITED` on a `STRICT_THROTTLE` transition (R1/R2/R4) and the new `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` (`app/core/audit.py`) on a `TEMPORARY_BLOCK` transition (R3/R5) — called from `login`/`forgot-password`/`reset-password` only after the real outcome is known, exactly once per escalation (`AbuseRecordOutcome.newly_escalated`), never for an ordinary `ALLOW`. Metadata is limited to `rule`/`operation`/`dimension`, the already-HMAC-hashed `account_hash` when the dimension is account-scoped, and `block_ttl_seconds` for blocks — no raw email, password, token, or secret; `user_id` is always `None` (genuinely unavailable at this layer, never invented). No production abuse-decision code was modified — Slice 3c only consumes `AbuseRecordOutcome`'s existing return value. 6 new HTTP-level tests (`backend/tests/test_abuse_audit.py`) exercise the real `login`/`forgot-password`/`reset-password` endpoints end-to-end (real Redis, real PostgreSQL, no mocks) covering all of R1–R5, precedence, no-duplicate-audit-rows, no-audit-for-ordinary-ALLOW, safe metadata, and successful-login reset behavior — **passed 6/6, 3 consecutive runs**, alongside the complete **254-test backend suite passing 254/254, 3 consecutive runs**. `ruff`/`mypy` clean (82 source files). This was validated against the working tree, **not** a production validation. |
| Browser E2E (Playwright) | **IMPLEMENTED, VALIDATED, COMMITTED, PUSHED, MERGED** (`e1c4858`, PR #16) | `frontend/playwright.config.ts` + `frontend/e2e/` (`@playwright/test` ^1.63.0, Chromium). 19 tests across 3 spec files covering application availability, registration, login, session persistence/reload, logout, protected-route redirects, a genuine positive and negative CSRF case (through the real backend middleware, no mocking), and the full forgot-password → Mailpit (real REST-API email capture) → reset-password → post-reset login → session-revocation flow. Run against the real frontend/backend/PostgreSQL/Redis/Mailpit stack — no mocks. **19/19 passed, 3 consecutive clean runs** (spaced to respect the backend's own real `register` rate-limit window — see `HANDOFF.md` for the exact evidence, including two genuine findings from this validation that were fixed as test-code corrections, not application changes). `npm run lint`/`npm run typecheck`/`npx eslint e2e/` all clean; the existing 48 vitest tests are unaffected. `.github/workflows/ci.yml` gained a new `e2e` job. **Not** a production validation. |
| Observability / audit logging | IMPLEMENTED (auth/workspace scope) | Structured logging, request-ID propagation, and a JSON access log (`app/observability/`) from Issue #1, plus (Issue #2) a persistent `audit_logs` table (`app/core/audit.py`, `app/repositories/audit_log_repository.py`) capturing authentication, password-reset, workspace-membership, and authorization-denial events. Document-related audit events will be added when that surface exists (Issue #3). |
| Testing (unit/integration/E2E/security) | PARTIALLY IMPLEMENTED | Backend, **committed (`main`, `5391a78`)**: **183 pytest tests** (119 from Issue #2 + 51 from Redis Slice 1 + 13 from Redis Slice 2). Coverage includes real-database integration tests, cross-workspace-isolation/IDOR tests, CSRF tests (missing/mismatched/valid token, cross-client, login-CSRF, safe-method exemption), explicit `Set-Cookie` attribute assertions (HttpOnly/Path/SameSite), CORS preflight tests, an explicit "`Authorization: Bearer` alone does not authenticate and does not satisfy CSRF" test, password-reset security tests (enumeration resistance, single-use/expiry, cross-user isolation, session invalidation), real-Redis tests for the token-bucket engine (config validation, connection/availability, key construction/HMAC identifier, trusted-proxy IP resolution, first-request/consumption/rejection/TTL/cost semantics, multi-key all-or-nothing atomicity sequential and concurrent, the Redis-unavailable failure boundary), and HTTP-level wiring tests through the real endpoints — real-Redis key creation via `login`/`refresh`/`forgot-password`, an IP-only-dimension proof for `reset-password`, Tier A fallback and Tier B fail-open via dependency override for all five endpoints, the unconfigured-vs-unreachable distinction, spoofed-`X-Forwarded-For` ignored by default, an endpoint-driven multi-dimension atomicity regression test, and a cross-user account-isolation test. Verified both locally (183/183, real Postgres + real Redis, on the exact code now merged) and via GitHub Actions CI on PR #12 (backend lint/typecheck/tests check passed). **Slice 3a — merged (`026dcf3`, PR #13) — adds 32 tests for the abuse layer's Redis primitives (`tests/test_abuse_state.py`)**, real-Redis validated (32/32, 3 consecutive runs) before merge. **Slice 3b — merged (`42529e3`, PR #14) — added 33 tests for the decision engine (`tests/test_abuse_decision.py`)** plus a fix to `tests/conftest.py`'s `_reset_rate_limiters` (now sweeps `abuse:*` alongside `rl:*`, closing a real test-isolation gap that slice's own validation surfaced) — 248/248 passing, 3 consecutive runs, before merge; CI confirmed 3/3 green. **Slice 3c — merged (`75dd466`, PR #15) — added 6 HTTP-level tests (`tests/test_abuse_audit.py`)** exercising `login`/`forgot-password`/`reset-password` end-to-end for abuse-escalation audit emission — `ruff`/`mypy` clean (82 source files), 6/6 passing 3 consecutive times, and the complete **254-test backend suite passing 254/254, 3 consecutive runs**, real Postgres + real Redis, before merge; CI confirmed 3/3 green. **Not yet** a production validation. **Issue #3 Slice 3.1 — merged (`79d4787`, PR #17) — added 19 schema-only tests (`tests/test_document_schema.py`)**: table existence, FK validity/rejection, both unique constraints (including correct per-workspace/per-document, not global, scoping), cascade delete, nullable-field defaults, `DocumentStatus` persistence, database-assigned timestamps — real Postgres, no mocks. `ruff`/`mypy` clean (86 source files); the complete backend suite **273/273 passing** (254 pre-Slice-3.1 + 19 new), 3 consecutive runs, no regression in any existing test; CI confirmed 4/4 green (backend, frontend, Docker build, Playwright E2E — the first real Actions run of the `e2e` job). **Issue #3 Slice 3.2 — merged (`941c1a7`, PR #18 + fix `5e6fdc2`, PR #19) — 21 tests (`tests/test_storage_provider.py`)**: `StorageProvider`/`LocalStorage` save/read/delete/exists round-trips against a real filesystem (no mocks), nested-directory creation, non-colliding keys, rejection of path-traversal/absolute/empty keys on every operation, a symlink planted inside the root that would resolve outside it, and every operation's filesystem-failure handling (permission-denied on save/read/delete/exists all raise `StorageError`, never a raw `OSError`/`PermissionError`, and no error message contains the configured absolute storage root). **Issue #3 Slice 3.3 — merged (`a6762e2`, PR #20) — 76 tests**: 46 unit tests (`tests/test_document_service.py` — extension/MIME/magic-byte validation, streamed checksum/size-limit logic including exact-boundary cases, storage-key generation, five traversal/path-like filename patterns, all without a database) and 30 HTTP-level tests (`tests/test_document_upload.py` — authenticated/unauthenticated/MEMBER/VIEWER/non-member/cross-workspace, each supported format, unsupported extension/MIME/signature mismatch, oversized upload, checksum correctness, generated storage key and path-traversal-filename safety, exactly-one audit event, duplicate-in-same-workspace `409` and same-checksum-different-workspace success, storage failure, a genuine DB failure (FK violation) after a successful storage write with compensating cleanup, a genuine race-lost duplicate insert translated to `409`, cleanup-failure-never-leaks-a-path (including a non-`StorageError` cleanup failure — see below), malformed multipart input, real-Redis rate-limit key creation, rate-limit enforcement at the threshold, and Tier A fallback on an unreachable Redis) — all real Postgres/Redis/filesystem, no mocks, using a `get_storage_provider` dependency override for per-test storage isolation. **A pre-merge correctness review found and fixed one genuine gap**: `_cleanup_orphaned_storage_object()` only caught `StorageError`, but `StorageProvider` is an unenforced `Protocol` — a cleanup-time failure of any other exception type would have propagated uncaught, masking the original error. Broadened to catch `Exception`, with a regression test proving the original error (a real race-lost-duplicate `409`) still surfaces correctly. **Issue #3 Slice 3.4 — implemented, not yet committed — 51 new tests**: 27 unit tests (`tests/test_extraction.py` — per-format valid/malformed cases, a DOCX archive-safety check with four traversal-name patterns and member-count/per-member/total-size limits including one real 60 MB→~50 KB zip-bomb-shaped member at the true default threshold, a CSV field-size-limit failure, invalid-UTF-8 handling, the output-text budget) and 24 HTTP-level tests (`tests/test_document_processing.py` — per-format PARSED/FAILED transitions with correct audit events, a storage-read failure, an unexpected-exception path, a regression test proving the `PROCESSING` transition commits before extraction is attempted, authorization/lifecycle/retry behavior, and `document_process` rate-limit enforcement/fallback) — real Postgres/Redis/filesystem, no mocks. `ruff`/`mypy` clean (97 source files); the complete backend suite **421/421 passing** (370 pre-Slice-3.4 + 51 new), 3 consecutive runs, no regression in any existing test. Frontend: **48 vitest tests** — forms, auth state, nav, workspace switching/permission-sensitive UI, password-recovery pages, and explicit regression tests proving no auth token ever reaches `localStorage`/`sessionStorage`/an `Authorization` header — unaffected by Slices 3.3–3.4 (no frontend code changed), confirmed by re-running lint/typecheck/vitest. **Browser E2E** (see the dedicated "Browser E2E (Playwright)" row above, merged `e1c4858`, PR #16): 19 Playwright tests, 19/19 passing 3 consecutive clean runs against the real stack — document upload/retrieval/chat flows still have no E2E coverage, since no document UI exists yet. |
| CI/CD (`.github/workflows/`) | IMPLEMENTED | `.github/workflows/ci.yml` provisions a real `pgvector/pgvector:pg16` service container and runs Alembic migrations before lint/typecheck/pytest. Ran on GitHub Actions for PR #10 (Issue #2's cookie/CSRF/password-recovery work) — **3/3 checks passed** (backend lint/typecheck/tests, frontend lint/typecheck/tests/build, Docker build check) — before merge. |
| Docker / deployment (`infra/`) | IMPLEMENTED | `infra/docker/backend.Dockerfile`, `infra/docker/frontend.Dockerfile`, `infra/compose/docker-compose.yml` — runs `mailpit` (local dev SMTP capture, REST API on `:8025`) and a pinned `redis:7.4-alpine` service (healthcheck-gated, ADR 0006 §16), with `backend` depending on both being healthy at container-startup time only (not a runtime requirement — ADR 0006 §13). Verified this slice (Issue #3, Slice 3.4): backend image rebuilt with the new `pypdf`/`python-docx` dependencies, container came up healthy, and a full manual smoke test against the live stack (register → create workspace → upload a real 2-page PDF → process → `PARSED` with `page_count: 2`) succeeded end-to-end. |
| Skills system (`.agents/skills/`) | PARTIALLY IMPLEMENTED | Roster and process documented (`.agents/skills/README.md`); individual skill procedures not yet written. |

## Known limitations

- Ingestion, retrieval, generation, chat, search, and voice do not exist
  yet. `README.md` setup instructions are still deferred until an end user
  has something to actually do once logged in.
- No evaluation data or numbers exist. Any future mention of retrieval or
  generation quality metrics must come from an actual run recorded under
  `eval/results/` (once that directory exists) — never fabricated.
- Real GitHub issues `#1`–`#8` exist and are open (verified via
  `gh issue list --repo vigneshrao1723-lab/advanced-rag-knowledge-assistant`).
  `AGENTS.md` §9 separately documents a `#1`–`#43` internal planning
  baseline — those numbers are planning references only, don't confuse
  them with the real `#1`–`#8`.
- **Rate limiting in the committed (`main`) codebase is now Redis-backed
  when Redis is configured and reachable, with an in-process fallback
  otherwise** — every `enforce_*_rate_limit` dependency, as actually
  merged (`5391a78`, Slice 2 via PR #12, on top of Slice 1's engine at
  `46ef03b`), attempts `RedisTokenBucketLimiter` first (ADR §8/§10) and
  falls back to `FixedWindowRateLimiter` per ADR §13's operation-aware
  policy. This replaces the previous single-process-only behavior — see
  the "Distributed rate limiting" component-status row above for exactly
  what's wired in. This repository's own `infra/compose/docker-compose.yml`
  (local dev) and `.github/workflows/ci.yml` (backend test job) both set
  `REDIS_URL` by default, so the Redis path is what actually runs there;
  a hosting target outside this repository is not decided yet, and no
  production deployment of this project exists at all (ADR 0006 §1) —
  nothing here should be read as claiming production traffic has ever
  exercised this path. The deterministic abuse-detection layer (ADR §11)
  is merged (Slices 3a–3c, PRs #13–#15) — see the "Distributed rate
  limiting / abuse protection (Redis)" row above for exact detail.
- **Browser E2E (Playwright) is merged** (`e1c4858`, PR #16) — covers
  only the authentication/password-recovery surface (see the dedicated
  component-status row above). No document/chat/search UI exists yet for
  E2E coverage to extend to.
- Concurrency/race-condition behavior of the Redis token-bucket engine
  itself **is** tested against a real Redis instance, committed with
  Slice 1 (concurrent single-key and multi-key requests via `threading`,
  `backend/tests/test_redis_rate_limiter.py`). Concurrency behavior
  *through a real endpoint under genuinely concurrent HTTP load* has
  **not** been tested — `tests/test_rate_limit_wiring.py` (Slice 2,
  committed) covers only the wiring's sequential HTTP-level behavior,
  and no multi-process/multi-instance deployment of this
  project exists to test the distributed-coordination property against
  (the whole reason this ADR exists — see ADR 0006 §2.1) under real
  concurrent traffic from more than one backend process.
- The backend's CORS policy (`CORS_ALLOWED_ORIGINS`) defaults to
  `http://localhost:3000` for local development; a genuinely cross-site
  production deployment (frontend and backend on different registrable
  domains) requires the explicit configuration documented in
  [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md),
  which has not been exercised against a real deployment target since none
  is decided yet.
- Access-token revocation on logout/session-revoke/password-reset is
  bounded by the token's short TTL (`ACCESS_TOKEN_EXPIRE_MINUTES`, default
  15 minutes), not immediate — a deliberate, documented trade-off in
  [ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md)
  (stateless access-token validation, no DB round-trip on the hot path),
  not a defect. Tested explicitly for both the logout path
  (`backend/tests/test_workspaces.py`) and the password-reset path
  (`backend/tests/test_password_reset.py`).

## Immediate priorities

Issue #2 is done — PR #10 merged into `main`. Redis Slices 1–3c (the
full distributed rate limiter plus the deterministic abuse-detection
layer, ADR 0006 §8–§15) are all done and merged — PR #11 (`46ef03b`),
PR #12 (`5391a78`), PR #13 (`026dcf3`), PR #14 (`42529e3`), PR #15
(`75dd466`), each with CI green. Browser E2E coverage for the
authentication/password-recovery flows (Playwright) is done and merged
— PR #16 (`e1c4858`), CI green. GitHub Issue #3, Slice 3.1 (document data
model + migration) is done and merged — PR #17 (`79d4787`), CI green
(4/4 checks). Slice 3.2 (`StorageProvider` abstraction) is done and
merged — PR #18 (`941c1a7`), CI green. Slice 3.2's own pre-merge
correctness/security review fix is done and merged — PR #19 (`5e6fdc2`),
CI green. Slice 3.3 (document upload API) is done and merged — PR #20
(`a6762e2`), merged by the repository owner. `main`/`origin/main` are at
`a6762e2`. Nothing is pending review, push, or merge for any of the
above. **Slice 3.4 (text extraction) is implemented, tested, on branch
`issue-3-slice-3-4-text-extraction`, not yet committed/pushed/PR'd** —
see `HANDOFF.md` for exact status. The next work, in order:

1. Commit Slice 3.4, push the branch, open a PR, and get it reviewed and
   merged.
2. After that, with an explicit go-ahead: Slice 3.5 of GitHub Issue #3
   (not started; do not assume further detail without checking
   `HANDOFF.md`/the Issue #3 GitHub issue first).

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5.
