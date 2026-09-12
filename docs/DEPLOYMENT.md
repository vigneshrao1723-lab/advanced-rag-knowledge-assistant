# Deployment

**Status:** PARTIALLY IMPLEMENTED — local Docker Compose development and a
CI workflow exist and have been verified to work (`infra/`,
`.github/workflows/ci.yml`); a real hosting/production deployment target has
not been decided. As of this writing `infra/` and `.github/workflows/` exist
in the working tree but are not yet committed — see `PROJECT_STATE.md` and
`git status`.

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
- Verified (see `HANDOFF.md` for the full verification log): both images
  build; the stack starts; the pgvector extension is enabled in the running
  database; Alembic applies against the real container; the backend's
  liveness/readiness endpoints respond correctly with a real DB round-trip;
  the frontend serves and can reach the backend across origins (CORS).

## CI/CD (implemented)

- `.github/workflows/ci.yml` runs on pull requests and pushes to `main`:
  - `backend` job: `ruff check`, `mypy`, `pytest` (via `uv`).
  - `frontend` job: `eslint`, `tsc --noEmit`, `vitest`, `next build` (via
    `npm ci`).
  - `docker-build` job (after both pass): builds the backend and frontend
    images, and validates `docker compose config`.
- CI is a required gate in the workflow defined in `AGENTS.md` §6
  (... → Commit → Pull request → CI → Review → Merge) — no PR merges with
  failing CI. The workflow itself has not yet run on GitHub Actions, since
  nothing in this phase is committed/pushed yet; its constituent commands
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
