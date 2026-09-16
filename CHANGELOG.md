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

### 2026-09-15 — `feat: implement distributed Redis rate limiting foundation` (b1f1b00)

*(Branch `issue-redis-rate-limiting`, committed locally — **not yet
pushed, no PR open**. See `HANDOFF.md` for exact state.)*

Implements the parts of [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
that don't require touching any endpoint, per this slice's explicit
scope — no authentication endpoint's behavior changes yet:

- Added the `redis` Python dependency (`backend/pyproject.toml`,
  `backend/uv.lock`).
- New Redis settings in `backend/app/core/config.py`: `REDIS_URL`
  (optional), explicit socket/connect timeouts (default 50ms, ADR §13),
  `TRUSTED_PROXY_CIDRS` (default empty, ADR §9a).
- New `backend/app/core/redis_client.py`: connection abstraction, an
  exception-free `is_redis_available()` check, `RedisUnavailableError`.
- New `backend/app/core/redis_keys.py`: centralized rate-limit key
  construction and an HMAC-SHA256 email identifier (ADR §14).
- New `backend/app/core/ip_resolution.py`: trusted-proxy-aware client IP
  resolution (ADR §9a) — not yet called from any endpoint.
- Extended `backend/app/core/rate_limit.py` with `RedisTokenBucketLimiter`
  / `DimensionSpec` / `TokenBucketResult` — the ADR §8/§10 multi-key
  atomic Lua token-bucket engine (one `EVAL` per operation, over every
  dimension key that operation has, all-or-nothing). The existing
  `FixedWindowRateLimiter` and every `enforce_*_rate_limit` function are
  unchanged; nothing calls the new engine yet.
- Added a pinned, healthcheck-gated `redis:7.4-alpine` service to
  `infra/compose/docker-compose.yml` and `.github/workflows/ci.yml` (ADR
  §16 — local dev/CI only); `.env.example` documents the new variables.
- 51 new backend tests (170 total, up from 119), including real-Redis
  integration tests that directly regression-test the multi-key
  atomicity property ADR 0006 §17 names (sequential and concurrent).
  `ruff`/`mypy` clean; full suite passes against real Postgres + real
  Redis. Independently re-validated in an isolated worktree immediately
  before this commit, from the staged tree alone.
- Documented a non-obvious Redis/Lua gotcha in `SOLVING.md`: Lua scripts
  silently truncate a returned float to an integer over RESP2, so the
  token-bucket script's retry-after value is computed and returned in
  integer milliseconds, not fractional seconds.
- Does **not** include Slice 2 (endpoint wiring) — that remains
  uncommitted working-tree-only on this branch, per an explicit
  Git-separation task. `PROJECT_STATE.md`/`HANDOFF.md`/`docs/SECURITY.md`/
  ADR 0006's "Implementation status" are updated separately to reflect
  this checkpoint accurately (see those files and their own history for
  the exact correction).

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
