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

### 2026-09-11 — `chore: configure Git line endings` (a059965)

- Added `.gitattributes` (`* text=auto eol=lf`).

### 2026-09-11 — `chore: initialize project architecture and documentation` (a7d81cf)

- Initial repository scaffold: empty placeholder docs (`AGENTS.md`,
  `CHANGELOG.md`, `CLAUDE.md`, `GEMINI.md`, `HANDOFF.md`,
  `PROJECT_STATE.md`, `SOLVING.md`, `START_HERE.md`, `docs/*.md`),
  `.env.example`, `.gitignore`.
