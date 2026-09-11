# Deployment

**Status:** PROPOSED — no deployment, Docker, or CI configuration exists yet
(`infra/` and `.github/workflows/` are not present in the repository). This
document records the intended approach.

## Principles

- Deployment follows the same modular-monolith philosophy as the
  application itself: one backend service, one frontend service, one
  PostgreSQL (+ pgvector) database — no premature infrastructure sprawl.
- Local development targets Docker Desktop + WSL2, matching the
  intended-technology direction in `README.md`.
- Containerization and CI are added when there is something real to build
  and test — not scaffolded speculatively ahead of application code.

## Target local development setup (not yet implemented)

- `infra/docker/` — Dockerfiles for the backend and frontend services.
- `infra/compose/` — Docker Compose configuration wiring backend, frontend,
  and PostgreSQL (with the `pgvector` extension) together for local
  development.

## Target CI/CD (not yet implemented)

- `.github/workflows/` — GitHub Actions workflows covering, at minimum: lint,
  type-check, backend tests, frontend tests, and a Docker build check on
  pull requests.
- CI is a required gate in the workflow defined in `AGENTS.md` §6
  (... → Commit → Pull request → CI → Review → Merge) — no PR merges with
  failing CI.

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
