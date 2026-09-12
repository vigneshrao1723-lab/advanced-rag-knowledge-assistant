# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

Complete GitHub Issue #1 — Application Foundation. A prior session
implemented the backend/frontend/infra scaffolding; this session resumed
that work to run the full local verification pass Issue #1 requires (Docker
builds, Compose stack, PostgreSQL + pgvector, Alembic against the real
database, health/readiness, frontend↔backend integration) and to add the
CI workflow. No product functionality (auth, ingestion, retrieval,
generation, voice) was implemented — out of scope for this issue.

## Completed work

- Re-verified backend: `ruff check` clean, `mypy --strict` clean (30
  files), `pytest` 7/7 passing.
- Re-verified frontend: `eslint` clean, `tsc --noEmit` clean, `vitest` 3/3
  passing, `next build` succeeds (14 routes).
- Validated `infra/compose/docker-compose.yml` with `docker compose config`.
- Built both Docker images (`docker compose build backend frontend`) —
  succeeded.
- Started the full stack (`docker compose up -d`): Postgres+pgvector,
  backend, frontend.
- **Found and fixed a real bug**: the backend container crash-looped
  (`Restarting`, exit code 2) on first boot. `infra/docker/backend.Dockerfile`
  built `.venv` as root, then switched to `USER appuser` without transferring
  ownership; `docker-entrypoint.sh`'s `uv run alembic upgrade head` tries to
  resync the editable install at every container start and got
  `Permission denied` trying to write into the root-owned `.venv`. Fixed by
  adding `chown -R appuser:appuser /app` before the `USER appuser` line.
  Rebuilt and confirmed the backend now starts cleanly, runs the Alembic
  migration, and serves requests.
- **Found and fixed a second real bug**: the backend had no CORS
  middleware. `curl` against `/api/v1/health/ready` from the host worked
  (no browser CORS enforcement), which could have been mistaken for working
  frontend↔backend communication — but a real browser at
  `http://localhost:3000` fetching `http://localhost:8000` would have been
  silently blocked (verified: no `Access-Control-Allow-Origin` header
  before the fix). Added `CORSMiddleware` in `backend/app/main.py`, a new
  `cors_allowed_origins` setting in `backend/app/core/config.py` (default
  `http://localhost:3000`), and wired `CORS_ALLOWED_ORIGINS` through
  `.env.example` and `infra/compose/docker-compose.yml`. Re-verified:
  backend lint/typecheck/tests still pass; rebuilt the backend image;
  confirmed `Access-Control-Allow-Origin: http://localhost:3000` is now
  present on responses to requests carrying `Origin: http://localhost:3000`.
- Verified pgvector is actually enabled in the running container:
  `psql \dx` inside `compose-db-1` shows `vector 0.8.6`.
- Verified Alembic ran against the real container: migration `0001` (enable
  pgvector extension) applied; `alembic current` reports `0001 (head)`.
- Verified `/api/v1/health` (liveness) and `/api/v1/health/ready`
  (readiness, real DB round-trip) both return HTTP 200 from the running
  container.
- Verified the frontend serves (`HTTP 200` on `/`) and the page embedding
  the `BackendStatus` widget (`frontend/app/page.tsx`) renders (confirmed
  the "Backend status" / "Checking…" markup is present in the served HTML).
  **Not verified**: the widget's resolved end state
  ("Backend reachable, database ready") in an actual rendered DOM — that
  requires a real or headless browser executing the client-side `useEffect`
  fetch, which wasn't available in this environment without installing new
  browser binaries (judged out of scope for a one-off check). The
  CORS-enabled fetch itself was verified directly with `curl` using the
  frontend's exact origin header, which is the substantive risk the widget
  depends on.
- Created `.github/workflows/ci.yml`: backend job (ruff, mypy, pytest),
  frontend job (eslint, tsc, vitest, next build), and a docker-build job
  (builds both images with the same `context`/`file` arguments
  `docker/build-push-action` would use, plus `docker compose config`).
  Validated the YAML syntax and reproduced both Docker build invocations
  locally byte-for-byte (context= `backend`/`frontend`, file path relative
  to repo root) — they succeed. The workflow itself has not run on GitHub
  Actions since nothing is committed/pushed yet.
- Brought the stack down cleanly (`docker compose down`) after verification.
- Updated `PROJECT_STATE.md` component table and priorities to reflect the
  real, verified state of `backend/`, `frontend/`, `infra/`, and
  `.github/workflows/`.

## Remaining work

- Nothing in `backend/`, `frontend/`, `infra/`, `.github/workflows/`, or the
  `.env.example`/doc updates from this session is committed — see
  `git status`. This session was explicitly told not to commit or push.
- The CI workflow has never run on GitHub Actions (no push yet) — only its
  constituent commands were verified locally.
- The `BackendStatus` widget's resolved rendered state was not confirmed in
  an actual browser DOM (see above) — only the underlying CORS-enabled
  fetch path was confirmed directly.
- Everything in `PROJECT_STATE.md` marked `PLANNED` — all product
  functionality (auth, workspaces, ingestion, retrieval, generation, chat,
  search, voice, evaluation, audit logging beyond structured request logs).
- Implementation-detail items ADR 0003 explicitly leaves open: exact token
  lifetimes, refresh-token delivery mechanism, reuse-detection response,
  password hashing algorithm choice.

## Blockers

None. Docker/Compose access is confirmed working in the current shell
(`docker ps` succeeds; this was previously blocked by group membership in
an older shell, per the user).

## Tests run

- Backend: `uv run ruff check .` (pass), `uv run mypy .` (pass, 30 files),
  `uv run pytest -v` (7/7 pass).
- Frontend: `npm run lint` (pass), `npm run typecheck` (pass),
  `npm run test` (3/3 pass), `npm run build` (pass, 14 routes).
- `docker compose -f infra/compose/docker-compose.yml config` (valid).
- `docker compose -f infra/compose/docker-compose.yml build backend frontend`
  (both succeed, after the Dockerfile fix for backend).
- `docker compose -f infra/compose/docker-compose.yml up -d` — full stack
  healthy (db healthy, backend up, frontend up) after the fix.
- `psql \dx` inside `compose-db-1` — confirms `vector 0.8.6` extension.
- `alembic current` inside `compose-backend-1` — confirms `0001 (head)`.
- `curl http://localhost:8000/api/v1/health` — `200 {"status":"ok"}`.
- `curl http://localhost:8000/api/v1/health/ready` — `200
  {"status":"ready","checks":{"database":"ok"}}`.
- `curl -H "Origin: http://localhost:3000" http://localhost:8000/api/v1/health/ready`
  — `200` with `Access-Control-Allow-Origin: http://localhost:3000`.
- `curl http://localhost:3000/` — `200`, contains the `BackendStatus`
  widget's initial markup.
- Local reproduction of the CI docker-build job's exact `docker build -f
  infra/docker/<name>.Dockerfile <context>` invocations for both images —
  both succeed.

## Exact next recommended action

1. Review this working tree (backend, frontend, infra, `.github/workflows/`,
   and the doc updates) with the user/maintainer.
2. If approved: `git add` the reviewed files, commit (following
   `AGENTS.md` §6's commit conventions), push
   `issue-1-application-foundation`, and open a PR against `main`
   referencing GitHub Issue #1 (already filed in
   `vigneshrao1723-lab/advanced-rag-knowledge-assistant`) so CI actually
   runs on GitHub Actions for the first time — confirm it's green before
   merging.
3. After merge, begin GitHub Issue #2 (Authentication & Workspaces), per
   `docs/DECISIONS/0003-authentication-session-architecture.md`.
