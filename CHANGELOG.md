# CHANGELOG.md

All notable changes to this project are recorded here, in chronological
order. Entries under **[Unreleased — working tree]** describe changes made
locally that have **not yet been committed** (see `git status`) — logged
honestly as such, not backdated to look committed. Entries under
**[Unreleased — committed]** are real commits, referenced by hash, that
haven't been part of a tagged release yet. This file is never backfilled
with invented history of either kind.

## [Unreleased — working tree]

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
