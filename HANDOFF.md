# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

Implement GitHub Issue #2 — Authentication & Workspaces, on branch
`issue-2-authentication-workspaces`. Issue #1 (Application Foundation) is
already merged to `main` (PR #9). Full scope: registration, login, logout,
JWT access tokens + PostgreSQL-backed sessions with refresh rotation and
reuse-detection revocation (per ADR 0003), session/device management,
workspace CRUD/membership/four-role authorization, server-side workspace
isolation, and a minimal frontend vertical slice
(`/register`, `/login`, `/dashboard`, `/settings`, `/workspace`).

## Completed work

- **Backend**: `users`, `sessions`, `workspaces`, `workspace_members`
  SQLAlchemy models + Alembic migration `0002` (applied and verified
  reversible against the real Postgres container).
- **Security primitives** (`app/core/security.py`): Argon2id password
  hashing (new [ADR 0004](docs/DECISIONS/0004-password-hashing-argon2id.md)),
  JWT access tokens (15 min default) carrying `sub`+`sid` claims, opaque
  `<session_id>.<secret>` refresh tokens (only a SHA-256 hash of the secret
  is ever persisted).
- **Auth service/API** (`app/services/auth_service.py`,
  `app/api/v1/auth.py`): register, login (generic error message either way,
  resists enumeration), refresh (rotation; reuse of a rotated-out token
  revokes the session), logout, session list/revoke. Rate-limited
  (`app/core/rate_limit.py`, in-process fixed-window) on
  register/login/refresh.
- **Workspace service/API** (`app/services/workspace_service.py`,
  `app/api/v1/workspaces.py`): CRUD, membership, role changes, with the
  OWNER/ADMIN/MEMBER/VIEWER matrix documented in
  `docs/API_CONTRACT.md`. Every workspace-scoped route resolves
  `workspace_id` through `app/core/dependencies.py`'s
  `require_workspace_role`, which 404s for both nonexistent workspaces and
  ones the caller isn't a member of (never 403 — avoids confirming
  existence to non-members).
- **Backend tests**: 69 pytest tests total — unit (password hashing,
  JWT encode/decode, refresh-token parsing, rate limiter) and integration
  (`tests/test_auth.py`, `tests/test_workspaces.py`) against a **real**
  Postgres via SQLAlchemy's "join an external transaction" pattern
  (`tests/conftest.py` — each test rolls back cleanly even though app code
  calls `session.commit()`). Explicit security tests: cross-workspace
  IDOR attempts (404 for a non-member on every workspace endpoint),
  auth-bypass (missing/garbage/expired/wrong-signature tokens, revoked
  sessions), refresh-token reuse detection, and rate-limit triggering.
- **CI** (`.github/workflows/ci.yml`): added a `pgvector/pgvector:pg16`
  service container and an Alembic-migration step to the backend job, so
  the new integration tests actually run in CI against a real database.
- **Frontend**: `lib/api-client.ts` (Zod-validated API boundary, automatic
  401→refresh→retry-once), `lib/auth-context.tsx`, `lib/workspace-context.tsx`,
  `components/protected-route.tsx`. Real `/register`, `/login` forms;
  `/dashboard` and `/settings` (profile + session/device list with revoke)
  behind auth; `/workspace` (list/create/switch/rename/delete +
  member list/add/role-change/remove, all gated in the UI by role and
  enforced server-side regardless). Nav shows current user, a workspace
  selector, and logout when authenticated.
- **Frontend tests**: 22 vitest tests (up from 3) — register/login form
  validation and error handling, Nav auth-state/workspace-selector/logout,
  workspace-page permission-sensitive rendering (OWNER vs VIEWER),
  auth-storage round-trip.
- **Fixed two non-obvious bugs** (full write-ups in `SOLVING.md`):
  (1) a Postgres native-enum double-`CREATE TYPE` in the Alembic migration;
  (2) Testing-Library's automatic cleanup never running because
  `vitest.config.mts` doesn't set `globals: true` — fixed by an explicit
  `afterEach(cleanup)` in `vitest.setup.ts`.
- **New ADR**: [`docs/DECISIONS/0004-password-hashing-argon2id.md`](docs/DECISIONS/0004-password-hashing-argon2id.md).
- Verified end-to-end against the real Docker Compose stack: both images
  rebuilt with the new backend dependencies (`argon2-cffi`, `pyjwt`), full
  stack starts healthy, migrations apply, and a live
  register→get-current-user→create-workspace→list→refresh→
  cross-workspace-isolation-check flow was exercised via curl against the
  running containers (see "Tests run" below for exact commands/results).
- Updated `docs/API_CONTRACT.md` (concrete auth/workspace schemas +
  authorization matrix, previously deferred), `docs/SECURITY.md` (marks
  auth/authorization/rate-limiting/relevant security tests as
  implemented), `docs/DATA_MODEL.md` and `docs/ARCHITECTURE.md` (new
  tables/modules marked implemented), `README.md`, `PROJECT_STATE.md`.

## Remaining work

- Nothing for Issue #2's own scope is outstanding against its Definition of
  Done (see below) — remaining items are deliberately out of scope for
  this issue: email verification, password reset, full profile editing,
  audit logging of auth events (Issue #7), browser-based E2E (Playwright).
- Everything above is uncommitted in the working tree on
  `issue-2-authentication-workspaces` — see `git status`.
- The CI workflow's new Postgres-service block has not yet run on real
  GitHub Actions (no push yet) — its constituent commands (including
  `alembic upgrade head`) were verified locally instead.

## Blockers

None. Docker Compose, the local Postgres container, and `gh` CLI access
are all confirmed working in this environment.

## Tests run

- Backend: `uv run ruff check .` (pass), `uv run mypy .` (pass, 54 files),
  `uv run pytest -v` (69/69 pass, against real Postgres on
  `localhost:5432`, credentials `raguser`/`ragpass`/`ragdb`).
- Frontend: `npm run lint` (pass), `npm run typecheck` (pass — verified
  from a clean `.next`-free state), `npm run test` (22/22 pass), `npm run
  build` (pass, 14 routes).
- `docker compose -f infra/compose/docker-compose.yml config` (valid,
  including the new `SECRET_KEY` env var and no schema errors).
- `docker compose -f infra/compose/docker-compose.yml build` — both images
  rebuilt successfully with the new backend dependencies.
- `docker compose -f infra/compose/docker-compose.yml up -d` — full stack
  healthy (db healthy, backend healthy, frontend up); `alembic current`
  inside the backend container confirms `0002 (head)`; `\dt` inside the db
  container confirms `users`/`sessions`/`workspaces`/`workspace_members`
  exist.
- Live curl-driven flow against the running containers: register → 201
  with real tokens; `GET /api/v1/users/me` → 200 with the registered
  email; `POST /api/v1/workspaces` → 201, caller is `OWNER`;
  `GET /api/v1/workspaces` → lists it; `POST /api/v1/auth/refresh` → 200,
  rotated tokens; a second, unrelated registered user attempting
  `GET /api/v1/workspaces/{first_user's_workspace_id}` → **404** (verified
  cross-workspace isolation against the real database, not just in unit
  tests).
- CORS re-verified: `Access-Control-Allow-Origin: http://localhost:3000`
  present on a cross-origin request to the running backend.
- Stack shut down cleanly (`docker compose down`) after verification.

## Exact next recommended action

1. Review this working tree (backend, frontend, migration, CI change, new
   ADR, and doc updates) with the user/maintainer.
2. If approved: commit (small logical commits are fine — e.g. backend,
   frontend, docs — or one commit if the reviewer prefers), push
   `issue-2-authentication-workspaces`, and open a PR against `main`
   referencing GitHub Issue #2, so CI (including the new Postgres-backed
   integration tests) runs on GitHub Actions for the first time; confirm
   green before merging.
3. After merge, begin GitHub Issue #3 (Knowledge Ingestion).
