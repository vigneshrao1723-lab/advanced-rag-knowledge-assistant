# Deployment

**Status:** IMPLEMENTED for local development (Docker Compose + CI); a
real hosting/production deployment target has not been decided (see
"Target deployment environment" below — a deliberate, documented gap,
not an oversight). `infra/` and `.github/workflows/ci.yml` have been
verified to work repeatedly, across every merged Issue #1–#7 PR, with
CI green on all four jobs (backend, frontend, E2E, Docker build) each
time. The full application — ingestion, retrieval, generation, chat,
voice, evaluation — runs end-to-end against this local stack; see
`README.md`'s "Quickstart" for the exact steps.

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
  `uv` for dependency management, `espeak-ng` for offline TTS — Issue #6
  — installed via `apt-get`, runs as a non-root `appuser`, entrypoint
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
- Verified repeatedly (see `HANDOFF.md` for the full verification log
  across every Issue #1–#7 slice): both images build; the stack starts;
  the pgvector extension is enabled in the running database; Alembic
  applies all migrations (`0001` through `0008` as of Issue #7) against
  the real container; the backend's liveness/readiness endpoints
  respond correctly with a real DB round-trip; the frontend serves and
  can reach the backend across origins (CORS); the full product flow —
  register → login → create workspace → upload/process a document to
  `READY` → ask a question in chat → grounded answer with citations →
  voice input/output — was exercised against the running containers via
  both the real browser UI and direct `curl` calls (Issue #6's own
  verification specifically drove the voice endpoints this way against
  a freshly rebuilt stack).

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
- `frontend/e2e/documents-chat.spec.ts` (Issue #5, Slice 5.1): the
  primary product flow end-to-end — register → create a workspace →
  upload a real document → poll for `READY` → open Chat → ask a
  question → a real grounded answer appears with its citation.
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
  - `backend` job: provisions real `pgvector/pgvector:pg16` and
    `redis:7.4-alpine` service containers (the auth/workspace/rate-
    limiting integration and security tests need a real database and a
    real Redis, not mocks), installs `espeak-ng` (Issue #6, the voice
    TTS backend's own tests need it), runs Alembic migrations, then
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
  failing CI. Every PR merged from Issue #1 through Issue #7 required
  all four jobs green on GitHub Actions before merge (not just verified
  locally) — see `HANDOFF.md`'s per-slice "Tests run" log and
  `CHANGELOG.md` for the specific PR numbers.

## CORS configuration (implemented)

The backend and frontend are different origins even in local development
(ports `8000` and `3000`), so the backend enables CORS via
`CORSMiddleware`, configured by the `CORS_ALLOWED_ORIGINS` environment
variable (comma-separated list, default `http://localhost:3000`). This will
need a real value once a non-local frontend origin exists.

## Target deployment environment

Not yet decided. The application is now functional end-to-end (Issues
#1–#7), so this is no longer "not yet a near-term concern" in the sense
the original wording meant — it is a deliberate scope boundary instead:
choosing a real cloud host/hosting model is a genuine infrastructure/
product decision (per `CLAUDE.md` §4, exactly the kind of choice this
project stops and asks a human about rather than deciding unilaterally),
not a code-quality or completeness gap. Local Docker Compose (above) is
the fully-supported, fully-verified way to run this project today. This
section will be filled in with a real, documented decision (recorded as
an ADR in `docs/DECISIONS/`) once a hosting target is actually chosen.

## Definition of Done — deployment-relevant items

Per `AGENTS.md` §7, when a change affects deployment: CI passes, the Docker
build succeeds, and deployment is verified before the change is considered
done.

## Related documents

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — target `infra/` and
  `.github/workflows/` structure.
- [`docs/DECISIONS/`](DECISIONS/) — where the eventual hosting/deployment
  decision will be recorded.
