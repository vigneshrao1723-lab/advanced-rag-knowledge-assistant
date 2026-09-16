# PROJECT_STATE.md

**Last updated:** 2026-09-16
**Current phase:** GitHub Issue #2 — Authentication & Workspaces — **merged
to `main`.** Next planned phase: Redis distributed rate limiting +
deterministic abuse protection — design **complete**
([ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)).
**Implementation Slice 1 (Redis foundation + token-bucket engine) is
IMPLEMENTED and COMMITTED** — commit `b1f1b00` on branch
`issue-redis-rate-limiting`, not yet pushed, no PR open. **Slice 2
(wiring that engine into every `enforce_*_rate_limit` dependency) is
IMPLEMENTED but exists only as uncommitted working-tree changes** on the
same branch, on top of the Slice 1 commit. The deterministic
abuse-detection layer does not exist in either form. See "Immediate
priorities" and `HANDOFF.md`.
(repository: `vigneshrao1723-lab/advanced-rag-knowledge-assistant`,
currently checked out on `issue-redis-rate-limiting`)

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
further via the ADR 0006 design-finalization commits (`b7fa773`,
`b18a330`, `7e439d2`), committed directly to `main` in an earlier
session — **`main`/`origin/main` are currently at `7e439d2`**, not
`ec4225d`. The `issue-redis-rate-limiting` branch (this checkout) shares
that same tip and adds Redis implementation work on top of it (see
below). The old feature branch (`issue-2-authentication-workspaces`) still
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
enforced server-side end to end. Ingestion, retrieval, generation, chat,
search, and voice still do not exist. Redis distributed rate limiting is
**partially implemented**: Slice 1 (the token-bucket engine and its
supporting infrastructure) is implemented **and committed** (`b1f1b00`
on `issue-redis-rate-limiting`, not pushed); Slice 2 (wiring that engine
into every `enforce_*_rate_limit` dependency) is implemented but exists
only as **uncommitted working-tree changes** on the same branch — see
the dedicated component-status row below. The deterministic
abuse-detection layer does not exist yet — see "Known limitations."

## Component status

| Component | Status | Notes |
|---|---|---|
| Documentation architecture (`START_HERE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `PROJECT_STATE.md`, `HANDOFF.md`, `SOLVING.md`, `CHANGELOG.md`, `docs/*`) | IMPLEMENTED | Kept current with each checkpoint per `CLAUDE.md` §5. |
| `docs/DECISIONS/` ADR log | IMPLEMENTED | Six ADRs: modular monolith (0001), Postgres/pgvector (0002), authentication/session architecture (0003), Argon2id password hashing (0004), HttpOnly cookie + CSRF authentication (0005), Redis distributed rate limiting + deterministic abuse protection (0006 — **design only**; see the dedicated row below). |
| `.gitignore` / `.gitattributes` / `.env.example` | IMPLEMENTED | Placeholders only, no real secrets. Documents `SECRET_KEY` (required), `COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`, `FRONTEND_URL`, `EMAIL_PROVIDER`/`SMTP_*`. |
| GitHub remote & issues | IMPLEMENTED | Remote configured (`origin` → `vigneshrao1723-lab/advanced-rag-knowledge-assistant`). Real, filed GitHub issues `#1`–`#8` exist (confirmed via `gh issue list`): `#1` Application Foundation (merged, PR #9), `#2` Authentication & Workspaces (**merged, PR #10 → `main` commit `ec4225d`**), `#3` Knowledge Ingestion (not started), `#4` Hybrid RAG Pipeline, `#5` Product Experience, `#6` Voice, `#7` Evaluation/Security/Observability, `#8` CI/CD/Deployment/Finalization. Separate from these, `AGENTS.md` §9 documents a finer-grained `#1`–`#43` **internal planning baseline** — the two numbering schemes don't map 1:1. |
| Backend application (`backend/`) | IMPLEMENTED | Config, structured logging, request-ID middleware, centralized error handling, SQLAlchemy + Alembic, health/readiness (Issue #1) — plus (Issue #2) auth/workspace/password-recovery/audit-logging services, repositories, schemas, API routes, HttpOnly-cookie + CSRF middleware, plus (Redis Slice 1, **committed** `b1f1b00` on `issue-redis-rate-limiting`) the Redis-backed token-bucket engine and its supporting infrastructure — **not yet wired into any endpoint**; the wiring itself (Slice 2) exists only as uncommitted working-tree changes on the same branch — described in the "Distributed rate limiting" row below. Verified on the **committed** state alone (Slice 1 only, isolated worktree): `ruff check` clean, `mypy` clean (74 files), `pytest` **170/170 passing** (real Postgres + real Redis). The full working tree (Slice 1 + uncommitted Slice 2) separately verifies at `ruff`/`mypy` clean, `pytest` **175/175 passing** — not yet part of any commit. |
| Frontend application (`frontend/`) | IMPLEMENTED | Next.js 16 + TypeScript, Tailwind v4, shadcn/ui. `chat/collections/documents/evaluations/search` remain stub routes (later issues); `login/register/forgot-password/reset-password/dashboard/settings/workspace` are real, backed by `lib/auth-context.tsx` + `lib/workspace-context.tsx` + `lib/api-client.ts`. Authentication is cookie-only — see the "Authentication" row. Verified: `eslint` clean, `tsc --noEmit` clean, `vitest` **48/48 passing**, `next build` succeeds. |
| Database schema / migrations | IMPLEMENTED (for this issue's scope) | `0001` enables `pgvector` (Issue #1); `0002` adds `users`, `sessions`, `workspaces`, `workspace_members`; `0003` adds `password_reset_tokens` and `audit_logs` (Issue #2) — all verified applied and reversible against the real container. Remaining `docs/DATA_MODEL.md` entities (`documents`, `document_chunks`, `collections`, etc.) land with the features that need them. |
| Authentication | IMPLEMENTED | Registration, login, logout, Argon2id password hashing ([ADR 0004](docs/DECISIONS/0004-password-hashing-argon2id.md)), JWT access tokens + PostgreSQL-backed sessions with refresh rotation and reuse-detection revocation ([ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md)), session/device listing and revocation. **Tokens are delivered exclusively via HttpOnly cookies** (`access_token` on `Path=/`, `refresh_token` narrowly scoped to `Path=/api/v1/auth`) — never in a response body, never in an `Authorization` header, never read or stored by frontend JavaScript (no `localStorage`/`sessionStorage` token storage anywhere). CSRF protected via a double-submit cookie (`csrf_token`, deliberately non-`HttpOnly`) + `X-CSRF-Token` header on every state-changing request, including login/register. Cookie attributes (`COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`) and CORS (`CORS_ALLOWED_ORIGINS`, credentialed) are deployment-aware, not hardcoded for local dev. Full model, including the "different origin ≠ cross-site" distinction: [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md). **Password recovery** (backend + frontend) is implemented: `/forgot-password` and `/reset-password` pages; cryptographically random (256-bit), SHA-256-hashed-at-rest, single-use, expiring reset tokens; enumeration-resistant (identical response/timing for known vs. unknown email); a successful reset revokes every existing session for that user. Email delivery via a vendor-neutral `EmailProvider` abstraction (`console` dev fallback or `smtp`, e.g. Mailpit locally) — `ENVIRONMENT=production` with `EMAIL_PROVIDER=console` fails at config-load time rather than risk raw tokens reaching production logs via stdout capture. Audit logging (`app/core/audit.py`) records auth events, password-reset events, workspace membership changes, and authorization denials. Per-endpoint rate limiting (see "Known limitations" — still in-process, not yet Redis-backed). `backend/app/{core/security.py,core/cookies.py,core/csrf.py,core/rate_limit.py,core/audit.py,services/auth_service.py,services/password_reset_service.py,services/email_provider.py,api/v1/auth.py}`; frontend: `frontend/lib/{api-client.ts,auth-context.tsx,csrf.ts,schemas.ts}`, `frontend/app/{login,register,forgot-password,reset-password}/`. |
| Workspaces | IMPLEMENTED | CRUD, membership, four-role authorization matrix (OWNER/ADMIN/MEMBER/VIEWER — see `docs/API_CONTRACT.md`), server-side `require_workspace_role` dependency enforced on every workspace-scoped route, last-owner protection, audit-logged membership/role changes. `backend/app/{services/workspace_service.py,api/v1/workspaces.py,core/dependencies.py}`. Frontend: `/register`, `/login`, `/dashboard`, `/settings`, `/workspace` are real. |
| Document upload & ingestion pipeline | PLANNED | Pipeline states documented in `docs/RAG_DESIGN.md`; no code. |
| Retrieval (dense / BM25 / hybrid / rerank) | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Generation & citations | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Conversations / chat | PLANNED | No code. |
| Search interface | PLANNED | No code. |
| Voice (STT/TTS) | PLANNED | Explicitly scoped to come after text RAG works; no code. |
| Evaluation harness | PLANNED | Metrics and methodology documented in `docs/EVALUATION.md`; **no evaluation has been run, no numbers exist.** |
| Distributed rate limiting / abuse protection (Redis) | Design: **DESIGNED**. Slice 1: **IMPLEMENTED and COMMITTED** (`b1f1b00`, not pushed). Slice 2: **IMPLEMENTED, UNCOMMITTED** (working tree only). Abuse layer: **NOT STARTED**. | [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md) documents the full architecture; its "Implementation status" table tracks exact per-component Designed/Implemented/Tested/Committed/Production-validated state. **Slice 1 — committed as `b1f1b00` on `issue-redis-rate-limiting`** added the foundation: the `redis` Python dependency; Redis settings (`REDIS_URL`, socket timeouts, `TRUSTED_PROXY_CIDRS`) in `app/core/config.py`; a connection abstraction (`app/core/redis_client.py`); a centralized key-builder + HMAC-SHA256 email identifier (`app/core/redis_keys.py`); a trusted-proxy IP-resolution function (`app/core/ip_resolution.py`, ADR §9a); the multi-key atomic Lua token-bucket engine (`RedisTokenBucketLimiter`/`DimensionSpec` in `app/core/rate_limit.py`, ADR §8/§10 — one Lua `EVAL` per operation over all of that operation's dimension keys, all-or-nothing); and a `redis` service in `infra/compose/docker-compose.yml`/CI. **None of this is wired into any endpoint in the committed state** — every `enforce_*_rate_limit` dependency as actually committed today still calls only `FixedWindowRateLimiter`, unchanged. **Slice 2 exists only as uncommitted working-tree changes on top of the Slice 1 commit** — it would wire the engine into every `enforce_*_rate_limit` dependency (`register`, `login`, `refresh`, `forgot-password`, `reset-password` attempting the Redis engine first, using `resolve_client_ip()` for IP, HMAC-hashed email for `login`/`forgot-password`'s account dimension, the refresh-token cookie's session ID for `refresh`, falling back to `FixedWindowRateLimiter` per ADR §13), and adds the `rate_limit_hash_key`/`RATE_LIMIT_HASH_KEY` setting the HMAC construction uses — but **none of this is active in the committed codebase** until Slice 2 is itself reviewed and committed. `/api/v1/health/ready` still deliberately does not check Redis (ADR §13, unchanged). Tested: 51 new backend tests are committed with Slice 1 (170 total); 5 additional HTTP-level wiring tests exist only in the uncommitted Slice 2 working tree (175 total there) — see `HANDOFF.md` for exact numbers and what remains (Slice 2 review/commit, then the deterministic abuse layer). |
| Browser E2E (Playwright) | **NOT STARTED** | No Playwright infrastructure, config, or tests exist. Do not assume otherwise from a mention of Mailpit or "E2E" elsewhere — Mailpit is used today only via direct REST-API verification (curl/Python), not through a Playwright-driven browser. |
| Observability / audit logging | IMPLEMENTED (auth/workspace scope) | Structured logging, request-ID propagation, and a JSON access log (`app/observability/`) from Issue #1, plus (Issue #2) a persistent `audit_logs` table (`app/core/audit.py`, `app/repositories/audit_log_repository.py`) capturing authentication, password-reset, workspace-membership, and authorization-denial events. Document-related audit events will be added when that surface exists (Issue #3). |
| Testing (unit/integration/E2E/security) | PARTIALLY IMPLEMENTED | Backend, **committed** state (`b1f1b00`): **170 pytest tests** (119 from Issue #2 + 51 from Redis Slice 1). Backend, **full working tree** (Slice 1 + uncommitted Slice 2): **175 pytest tests** (170 + 5 from the uncommitted Slice 2 HTTP-level wiring tests) — not yet part of any commit. Coverage includes real-database integration tests, cross-workspace-isolation/IDOR tests, CSRF tests (missing/mismatched/valid token, cross-client, login-CSRF, safe-method exemption), explicit `Set-Cookie` attribute assertions (HttpOnly/Path/SameSite), CORS preflight tests, an explicit "`Authorization: Bearer` alone does not authenticate and does not satisfy CSRF" test, password-reset security tests (enumeration resistance, single-use/expiry, cross-user isolation, session invalidation), real-Redis tests for the token-bucket engine (config validation, connection/availability, key construction/HMAC identifier, trusted-proxy IP resolution, first-request/consumption/rejection/TTL/cost semantics, multi-key all-or-nothing atomicity sequential and concurrent, the Redis-unavailable failure boundary), and (new) HTTP-level wiring tests through the real endpoints (real-Redis key creation via a live `login` call, Tier A fallback and Tier B fail-open via dependency override, the unconfigured-vs-unreachable distinction, spoofed-`X-Forwarded-For` ignored by default). Frontend: **48 vitest tests** — forms, auth state, nav, workspace switching/permission-sensitive UI, password-recovery pages, and explicit regression tests proving no auth token ever reaches `localStorage`/`sessionStorage`/an `Authorization` header. **No E2E browser suite exists** — Playwright has not been introduced (see the dedicated row above); this project's own live-Docker verification (curl/Python against the running containers) is not a substitute for it and is not represented as one. |
| CI/CD (`.github/workflows/`) | IMPLEMENTED | `.github/workflows/ci.yml` provisions a real `pgvector/pgvector:pg16` service container and runs Alembic migrations before lint/typecheck/pytest. Ran on GitHub Actions for PR #10 (Issue #2's cookie/CSRF/password-recovery work) — **3/3 checks passed** (backend lint/typecheck/tests, frontend lint/typecheck/tests/build, Docker build check) — before merge. |
| Docker / deployment (`infra/`) | IMPLEMENTED | `infra/docker/backend.Dockerfile`, `infra/docker/frontend.Dockerfile`, `infra/compose/docker-compose.yml` — runs `mailpit` (local dev SMTP capture, REST API on `:8025`) and, new this slice, a pinned `redis:7.4-alpine` service (healthcheck-gated, ADR 0006 §16 — local dev/CI only, not yet consumed by any request path) with `backend` depending on both being healthy at container-startup time only (not a runtime requirement — ADR 0006 §13). Verified: backend image rebuilt with the new `redis` dependency, full stack (db/mailpit/redis/backend) starts healthy, `/api/v1/health/ready` stays `200 ready` with Redis stopped, and a register call still succeeds unchanged (see `HANDOFF.md` for exact results). |
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
- **Rate limiting in the committed codebase is still exclusively the
  in-process `FixedWindowRateLimiter`** — every `enforce_*_rate_limit`
  dependency, as actually committed (`b1f1b00`), is byte-for-byte
  unchanged from before the Redis work and calls only the in-process
  limiter, same as pre-Redis behavior. The Redis-backed
  `RedisTokenBucketLimiter` engine exists and is committed (Slice 1) but
  **is not called from any endpoint in the committed state.** Wiring it
  in — every `enforce_*_rate_limit` dependency attempting
  `RedisTokenBucketLimiter` first (ADR §8/§10) and falling back to
  `FixedWindowRateLimiter` per ADR §13 — is Slice 2, implemented but
  **uncommitted, working-tree-only** on `issue-redis-rate-limiting`; see
  the "Distributed rate limiting" component-status row above for the
  exact split. This repository's own `infra/compose/docker-compose.yml`
  (local dev) and `.github/workflows/ci.yml` (backend test job) both set
  `REDIS_URL` by default (committed with Slice 1), so a real Redis is
  present in those environments — but nothing in the *committed* codebase
  actually queries it yet. No production deployment of this project
  exists at all (ADR 0006 §1). The deterministic abuse-detection layer
  (ADR §11) does not exist in either committed or uncommitted form. See
  `HANDOFF.md` for exactly what remains.
- **No browser-based E2E suite (Playwright) exists.** Do not infer
  otherwise from Mailpit's presence — Mailpit is verified today only via
  its REST API, not through a Playwright-driven real browser.
- Concurrency/race-condition behavior of the Redis token-bucket engine
  itself **is** tested against a real Redis instance, committed with
  Slice 1 (concurrent single-key and multi-key requests via `threading`,
  `backend/tests/test_redis_rate_limiter.py`). Concurrency behavior
  *through a real endpoint under genuinely concurrent HTTP load* has
  **not** been tested — `tests/test_rate_limit_wiring.py` (Slice 2,
  uncommitted) covers only the wiring's sequential HTTP-level behavior,
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

Issue #2 is done — PR #10 merged into `main` at commit `ec4225d`, CI green
(`main`/`origin/main` have since advanced further, to `7e439d2`, via the
ADR 0006 design-finalization commits). Nothing is pending review, push, or
merge for Issue #2. The next work, in order:

1. **Review, push, and open a PR for Redis Slice 1** — commit `b1f1b00`
   on branch `issue-redis-rate-limiting` (foundation + token-bucket
   engine, not wired into any endpoint), committed locally, **not yet
   pushed, no PR open**. This is the immediate next action.
2. **After Slice 1 is reviewed/merged: review and commit Slice 2**
   (wiring the engine into every `enforce_*_rate_limit` dependency) —
   implemented but still uncommitted working-tree-only on the same
   branch; see `HANDOFF.md` for the exact state.
3. **After Slice 2: implement the deterministic (non-ML) abuse-detection
   layer** (ADR §11/§12) — not started in either committed or uncommitted
   form. Do not start this before Slice 1/2 are reviewed and committed.
4. Introduce Playwright browser E2E coverage for the authentication/
   password-recovery flows — not yet started, no config or dependency
   exists.
5. After the above, begin GitHub Issue #3 (Knowledge Ingestion) — not
   started.

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5.
