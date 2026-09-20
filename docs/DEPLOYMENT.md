# Deployment

**Status:** PARTIALLY IMPLEMENTED — local Docker Compose development and a
CI workflow exist and have been verified to work (`infra/`,
`.github/workflows/ci.yml`, committed on `main` since Issue #1); a real
hosting/production deployment target has not been decided. Issue #2 adds a
required `SECRET_KEY` and a Postgres service container in CI for
integration tests — see below — currently in the working tree, not yet
committed; see `PROJECT_STATE.md` and `git status`.

## Principles

- Deployment follows the same modular-monolith philosophy as the
  application itself: one backend service, one frontend service, one
  PostgreSQL (+ pgvector) database — no premature infrastructure sprawl.
- Local development targets Docker Desktop + WSL2, matching the
  intended-technology direction in `README.md`.
- Containerization and CI are added when there is something real to build
  and test — not scaffolded speculatively ahead of application code.

## Local development setup (implemented)

- `infra/docker/backend.Dockerfile` — backend image (`python:3.13-slim`,
  `uv` for dependency management, runs as a non-root `appuser`, entrypoint
  applies pending Alembic migrations then starts `uvicorn`).
- `infra/docker/frontend.Dockerfile` — frontend image (multi-stage
  `node:22-alpine` build producing a Next.js standalone server bundle, runs
  as a non-root `appuser`).
- `infra/compose/docker-compose.yml` — wires together:
  - `db`: `pgvector/pgvector:pg16`, with a healthcheck (`pg_isready`).
  - `backend`: built from `backend.Dockerfile`, waits for `db` to be
    healthy, port `8000`.
  - `frontend`: built from `frontend.Dockerfile` (receives
    `NEXT_PUBLIC_API_URL` as a build arg, since Next.js inlines
    `NEXT_PUBLIC_*` variables at build time), port `3000`.
- Run locally with: `docker compose -f infra/compose/docker-compose.yml up --build`
- The backend requires `SECRET_KEY` (signs/verifies access tokens, Issue
  #2) — `docker-compose.yml` supplies a local-dev-only placeholder default;
  override via a `.env` file with a real generated value
  (`openssl rand -hex 32`) for anything beyond a throwaway local stack.
- Verified (see `HANDOFF.md` for the full verification log): both images
  build; the stack starts; the pgvector extension is enabled in the running
  database; Alembic applies migrations `0001`+`0002` against the real
  container; the backend's liveness/readiness endpoints respond correctly
  with a real DB round-trip; the frontend serves and can reach the backend
  across origins (CORS); a full register→login→create-workspace→
  cross-workspace-isolation flow was exercised against the running
  containers via curl.

## Browser E2E (Playwright, implemented)

- `frontend/e2e/` — TypeScript Playwright specs covering the
  authentication/password-recovery flows end-to-end through the real
  frontend, real backend, real PostgreSQL, real Redis, and real Mailpit
  (`frontend/playwright.config.ts`) — no mocks, matching this project's
  "no mock substitute for the real datastore" precedent (ADR 0002,
  extended by ADR 0006 §16) applied to the full stack. Covers app
  availability, registration, login, session persistence, logout,
  protected-route redirects, CSRF (a genuine positive case through the
  real UI and a genuine negative case — a state-changing request
  missing the `X-CSRF-Token` header — both against the real backend
  middleware), and the full forgot-password → Mailpit → reset-password →
  post-reset login → session-revocation flow.
- `frontend/e2e/fixtures/mailpit.ts` reads the password-reset email
  through Mailpit's own REST API (`http://localhost:8025`, already
  exposed by `infra/compose/docker-compose.yml`) — real SMTP capture,
  not a stub of the email provider.
- Run locally: start the stack (`docker compose -f
  infra/compose/docker-compose.yml up`, or the backend/frontend
  processes directly with a real Postgres/Redis/Mailpit reachable), then
  `cd frontend && npx playwright install chromium` (once) and `npm run
  test:e2e`. `PLAYWRIGHT_BASE_URL`/`PLAYWRIGHT_API_URL`/
  `PLAYWRIGHT_MAILPIT_URL` override the default `localhost:3000`/`8000`/
  `8025` if the stack is reachable elsewhere.
- Runs sequentially (`workers: 1`, `fullyParallel: false`), deliberately —
  the backend's own base rate limiter and deterministic abuse layer (ADR
  0006) key partly by source IP, and every request in a Playwright run
  shares one peer address; running specs in parallel (or firing many
  full-suite runs back-to-back with no gap) risks a real, correctly-
  functioning `429` unrelated to what any individual test checks. Each
  spec is deliberately economical with `register`/`login`/
  `forgot-password` calls for the same reason.

## CI/CD (implemented)

- `.github/workflows/ci.yml` runs on pull requests and pushes to `main`:
  - `backend` job: provisions a real `pgvector/pgvector:pg16` service
    container (Issue #2 — the auth/workspace integration and security
    tests need a real database, not a mock), runs Alembic migrations, then
    `ruff check`, `mypy`, `pytest` (via `uv`).
  - `frontend` job: `eslint`, `tsc --noEmit`, `vitest`, `next build` (via
    `npm ci`).
  - `e2e` job (after both pass): provisions real Postgres/Redis/Mailpit
    service containers, starts the real backend (`uvicorn`) and frontend
    (`next dev`) processes, waits for both to report ready, then runs the
    Playwright suite (`npm run test:e2e`). Uploads the HTML report (and,
    on failure, the backend/frontend server logs) as build artifacts —
    never secrets or runtime credentials.
  - `docker-build` job (after both pass): builds the backend and frontend
    images, and validates `docker compose config`.
- CI is a required gate in the workflow defined in `AGENTS.md` §6
  (... → Commit → Pull request → CI → Review → Merge) — no PR merges with
  failing CI. The Issue #2 changes to this workflow have not yet run on
  GitHub Actions, since they aren't pushed yet; their constituent commands
  were verified locally instead (see `HANDOFF.md`).

## CORS configuration (implemented)

The backend and frontend are different origins even in local development
(ports `8000` and `3000`), so the backend enables CORS via
`CORSMiddleware`, configured by the `CORS_ALLOWED_ORIGINS` environment
variable (comma-separated list, default `http://localhost:3000`). This will
need a real value once a non-local frontend origin exists.

## Target deployment environment

Not yet decided. This section will be filled in with a real, documented
decision (recorded as an ADR in `docs/DECISIONS/`) once the application is
functional enough that deployment is a near-term concern — not before, to
avoid committing to infrastructure the project doesn't yet need.

## Definition of Done — deployment-relevant items

Per `AGENTS.md` §7, when a change affects deployment: CI passes, the Docker
build succeeds, and deployment is verified before the change is considered
done.

## Related documents

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — target `infra/` and
  `.github/workflows/` structure.
- [`docs/DECISIONS/`](DECISIONS/) — where the eventual hosting/deployment
  decision will be recorded.
