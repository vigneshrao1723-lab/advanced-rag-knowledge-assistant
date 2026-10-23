# Production Readiness Assessment

**Status:** Local development is fully verified. **No production hosting
target is chosen.** This document exists to make that decision
informed, not to recommend deciding it unilaterally — per `CLAUDE.md`
§4, choosing a real cloud host/provider is exactly the kind of
infrastructure decision this project stops and asks a human about.
Nothing in this document should be read as a deployment having
happened, or as a recommendation to proceed without the human decisions
listed in "What remains unverified" below.

## What is verified locally

- **Docker Compose stack**: `db` (pgvector/pg16), `redis`, `mailpit`,
  `backend`, `frontend` all start cleanly from a cold `down`/`up
  --build`, reach `healthy` (where a healthcheck is defined), and the
  full product flow works end-to-end through the real browser —
  register → login → workspace → upload → process → `READY` → ask →
  grounded answer with citation → source inspection → feedback →
  rename/delete conversation → logout → protected-route redirect — all
  re-verified via a real Playwright-driven browser session this pass,
  asserting actual response content (citation text, cited-chunk text,
  `aria-pressed` feedback state, post-delete empty list, post-logout
  redirect), not just HTTP 200.
- **Cross-workspace isolation**: re-verified via real `curl` calls with
  two independent users/workspaces — a document, a conversation, and
  the workspace resource itself are all `404` (non-leaking) when a
  second user's workspace tries to reach the first's.
- **Migrations**: Alembic is at head (`0009`), applies cleanly on a
  fresh database (the backend entrypoint runs `alembic upgrade head`
  automatically on container start), and every individual migration in
  this project's history has been verified reversible
  (`downgrade`/`upgrade` round-tripped against the real database) at
  the time it was added.
- **`.env.example`**: re-confirmed this pass to load cleanly as a
  literal `.env` with no edits (a dedicated regression test,
  `backend/tests/test_config.py::test_env_example_loads_cleanly_as_a_literal_env_file`,
  loads the real file directly).
- **No secrets committed**: `.env` is not tracked; a repository-wide
  scan for common real-secret patterns (API keys, AWS access keys,
  private key PEM blocks) found none.
- **Health/readiness**: `GET /api/v1/health` (liveness) and `GET
  /api/v1/health/ready` (readiness, does a real DB round-trip) both
  exist and respond correctly.
- **Non-root containers**: both the backend and frontend Docker images
  run as a dedicated `appuser`, not root.
- **Structured logging**: the backend emits JSON logs to stdout
  (`backend/app/observability/logging.py`), the standard shape most log
  aggregators (CloudWatch Logs, Google Cloud Logging, Loki, etc.) can
  ingest directly from container stdout with no extra shipping agent.
- **CI**: 4 required GitHub Actions jobs (backend, frontend, Playwright
  E2E, Docker build) green on every merged PR — most recently #37, #38,
  #39.
- **Local-dev document persistence**: `backend`'s storage root
  (`/app/data/documents`) is now a named Docker volume
  (`backend_documents`, matching `db_data`'s existing pattern), with the
  directory pre-created and `appuser`-owned in the image so a fresh
  volume mount doesn't default to root ownership (see `SOLVING.md`'s
  2026-10-23 entry for the exact permission bug this required fixing).
  Verified with a real upload followed by `docker compose up -d
  --force-recreate backend`: the file and its exact content survived.
  This is still a local-dev convenience only, not a production storage
  solution — see "No object storage" below, which remains a real gap.

## What remains unverified (genuinely untested in this project)

- **No production deployment has ever run.** Everything above is
  verified against local Docker Compose only. No multi-instance,
  real-network, or real-traffic scenario has been exercised.
- **No backup/restore procedure exists or has been tested.** Postgres
  data lives in a named Docker volume (`db_data`) that survives
  container restarts, but there is no scripted `pg_dump`/`pg_restore`
  (or equivalent managed-service snapshot) procedure, and none has been
  rehearsed. A host/volume loss today would lose all data.
- **No object storage.** `StorageProvider`'s only implementation is
  `LocalStorage` — uploaded documents are written to a local filesystem
  path (`storage_local_root`, default `./data/documents`). As of this
  pass, local Docker Compose persists this across a single-container
  recreation via a named volume (see "What is verified locally" above)
  — but that only helps a single, stationary backend instance with a
  local disk. A real multi-instance or ephemeral-filesystem production
  deployment (most container platforms — Fargate, Cloud Run, Fly.io,
  etc. — give each instance its own disposable filesystem, and a named
  Docker volume doesn't exist as a concept on most of them) still needs
  a real object-storage implementation of the existing `StorageProvider`
  abstraction (the codebase's own `storage_bucket` setting is already
  reserved for this) before documents could survive a redeploy or scale
  past one instance. This is new code, not configuration, and remains
  unbuilt.
- **Redis is explicitly optional infrastructure** (ADR 0006): every
  rate-limit dependency falls back to an in-process limiter if Redis is
  unreachable, which is correct and safe for a *single* backend
  process, but means rate limits are **not actually distributed** if a
  production deployment ever runs more than one backend instance
  without Redis configured and reachable — this has not been tested
  under real multi-instance concurrent load (the distributed-
  coordination property ADR 0006 exists for has only been unit-tested
  against a single real Redis instance, not exercised end-to-end from
  more than one backend process under real traffic).
- **No image registry/versioning.** `docker-compose.yml` uses `build:`
  for `backend`/`frontend` (no `image:` tag), and CI's `docker-build`
  job validates that the images build, but never pushes them anywhere.
  A real deployment needs a registry (a private Docker Hub repo, AWS
  ECR, GCP Artifact Registry, etc.) and a build-and-push CI step, which
  does not exist today.
- **No metrics/monitoring endpoint.** Structured JSON logs exist; there
  is no `/metrics` (Prometheus-style) endpoint or APM integration. Any
  production deployment would be flying with logs only, no dashboards,
  until one is added.
- **CORS/cookie/trusted-proxy settings are local-dev defaults.**
  `CORS_ALLOWED_ORIGINS` defaults to `http://localhost:3000`,
  `COOKIE_SAMESITE`/`COOKIE_SECURE`/`COOKIE_DOMAIN` default to the
  same-site-local-dev-safe values, and `TRUSTED_PROXY_CIDRS` defaults
  to empty (no proxy trusted) — all deliberately safe defaults (see
  [ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md),
  [ADR 0006](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
  §9a), but **none of them has been exercised against a real
  cross-site or behind-a-real-load-balancer deployment** — only
  unit/integration-tested against the documented intended behavior.
- **No rollback procedure beyond "redeploy the previous image" is
  documented or rehearsed.** Alembic migrations are individually
  reversible, but there is no tested, scripted "roll the whole stack
  back to the previous release" runbook.
- **Email delivery** (`EMAIL_PROVIDER=smtp`) has only ever been pointed
  at Mailpit (local SMTP capture) — never a real SMTP host/relay/
  transactional-email provider (SendGrid, SES, Postmark, etc.).

## Security and operational risks if deployed as-is today

1. **Data loss risk**: no tested backup/restore for Postgres. Uploaded
   documents now survive a single backend container's own recreation
   in local Compose (a named volume), but have no durability story at
   all on a multi-instance or ephemeral-filesystem production target
   (see "No object storage" above) — this remains a real production
   gap, just not a local-dev one anymore.
2. **Rate-limit bypass under scale-out**: without Redis configured and
   reachable, running more than one backend instance means each
   instance enforces rate limits independently — a real
   defense-in-depth gap for a multi-instance deployment, not a local
   single-instance one.
3. **No deployment-time secret-management story**: `.env.example`
   documents every variable, but there is no integration with a real
   secrets manager (AWS Secrets Manager, GCP Secret Manager, Vault,
   etc.) — a real deployment would need to decide how `SECRET_KEY`,
   `DATABASE_URL`, `SMTP_PASSWORD`, etc. reach the running containers
   without landing in a committed file or a CI log.
4. **No observability beyond logs**: a real incident today would be
   diagnosed from raw JSON log lines only, with no dashboards or
   alerting wired to anything.
5. **CORS/cookie/proxy settings must be explicitly reconfigured**
   before any cross-site or behind-a-load-balancer deployment, or
   authentication will either not work (cookies rejected) or be
   silently weaker than intended (trusted-proxy IP spoofing if
   `TRUSTED_PROXY_CIDRS` is set wrong). This is documented
   (`ADR 0005`/`ADR 0006` §9a) but unexercised against a real target.

## Two or three suitable hosting approaches (trade-offs, not a decision)

These are evidence-based options to inform the human decision this
document exists to support — not a recommendation to proceed with any
of them. Approximate cost language reflects each provider's own
published pricing as of this project's existing knowledge; always
re-check current pricing before deciding, since this changes
frequently and this document cannot verify it live.

1. **A single small VM running Docker Compose as-is** (e.g. a $5–20/mo
   VPS — DigitalOcean Droplet, Hetzner, a small AWS Lightsail/EC2
   instance). **Lowest effort, closest to what's actually verified** —
   the exact `docker compose up --build` flow already proven locally
   would run largely unchanged. Trade-offs: no horizontal scaling, no
   managed backups, the operator becomes responsible for OS patching,
   TLS termination, and backup scheduling. Best fit if the goal is "get
   this running on the public internet quickly" rather than
   production-grade resilience.
2. **Managed Postgres + managed Redis + a container platform for the
   two app images** (e.g. AWS RDS for Postgres with the `pgvector`
   extension enabled + AWS ElastiCache for Redis + ECS Fargate or App
   Runner for backend/frontend; or the equivalent on GCP — Cloud SQL +
   Memorystore + Cloud Run; or a PaaS like Render/Railway/Fly.io, which
   bundle managed Postgres and often a Redis add-on). **Addresses the
   backup/durability and scale-out gaps above directly** — managed
   Postgres gives real automated backups/point-in-time-restore, managed
   Redis makes the rate limiter's distributed-coordination property
   actually meaningful across multiple instances. Trade-offs: real
   recurring cost (roughly $15–60+/mo for the smallest managed-Postgres
   + managed-Redis tiers, scaling with usage), and `StorageProvider`
   still needs a real object-storage implementation (S3/GCS) added
   before documents survive a redeploy — this is new code, not just
   configuration, and is explicitly out of scope to build without a
   provider decision first.
3. **A fully managed container platform (Fly.io, Render, Railway) with
   their bundled Postgres+pgvector and Redis add-ons.** Middle ground
   between options 1 and 2: less operational burden than a bare VM
   (managed TLS, managed restarts, often one-command deploys from this
   repo's existing Dockerfiles), real managed-Postgres backups, often
   cheaper than a full hyperscaler setup at this project's current
   scale. Trade-offs: less control than a hyperscaler, and the same
   object-storage gap as option 2 — `StorageProvider` still needs a
   real implementation before documents are durable.

**None of these can be selected by this agent.** Per `CLAUDE.md` §4,
this is a genuine product/infrastructure decision — cost, account
ownership, data-residency/compliance requirements, and who operates it
all matter and are the project owner's call.

## Exact human decisions and credentials needed before deployment

1. **Choose a hosting provider/approach** (one of the above, or
   another) — an explicit decision, recorded as a new ADR in
   `docs/DECISIONS/` once made, per this project's existing convention.
2. **Provision real infrastructure accounts/credentials**: a cloud
   provider account, a container registry, a managed Postgres instance
   (with the `pgvector` extension available/enabled), and — if chosen
   — a managed Redis instance and an object-storage bucket.
3. **Generate and securely store a real `SECRET_KEY`**
   (`openssl rand -hex 32`) — never reuse the local-dev placeholder.
4. **Choose and configure a real SMTP provider** for password-reset
   email (SendGrid, SES, Postmark, etc.) and its credentials.
5. **Decide the real frontend/backend origins** and set
   `CORS_ALLOWED_ORIGINS`, `COOKIE_SAMESITE`/`COOKIE_DOMAIN`/
   `COOKIE_SECURE`, and `FRONTEND_URL` accordingly (same-site vs.
   genuinely cross-site changes which values are correct — see
   [ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md)).
6. **If deploying behind a load balancer/reverse proxy**, decide and
   set `TRUSTED_PROXY_CIDRS` to that proxy's real address range — never
   a wildcard, per ADR 0006 §9a's safe-by-default design.
7. **Decide a backup/restore procedure and rehearse it** at least once
   before real user data exists in the target environment.
8. **If keeping uploaded documents past the first redeploy matters**,
   decide and fund an object-storage approach before launch — this
   needs new `StorageProvider` implementation code, not just config.
9. **Decide a monitoring/alerting approach** (even a minimal one —
   e.g. the hosting platform's own basic uptime check) before relying
   on this in any way that matters if it goes down.

## Provider-neutral deployment checklist

Use this regardless of which hosting approach is chosen:

- [ ] Hosting provider/approach decided and recorded as an ADR.
- [ ] Real `SECRET_KEY` generated and stored outside version control
      (a secrets manager or the platform's own encrypted env-var store
      — never a committed file).
- [ ] Real `DATABASE_URL` pointing at a real, backed-up Postgres
      instance with the `pgvector` extension available.
- [ ] `ENVIRONMENT=production` set (this already activates this
      project's existing production-only safety checks — e.g. refusing
      to start with `EMAIL_PROVIDER=console` in production, since that
      would print password-reset tokens to logs).
- [ ] Real SMTP provider configured (`EMAIL_PROVIDER=smtp`,
      `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD`/
      `SMTP_FROM_EMAIL`/`SMTP_USE_TLS`).
- [ ] `CORS_ALLOWED_ORIGINS` set to the real frontend origin(s) only.
- [ ] `COOKIE_SAMESITE`/`COOKIE_SECURE`/`COOKIE_DOMAIN` set correctly
      for the real same-site-vs-cross-site deployment shape.
- [ ] `FRONTEND_URL` set to the real frontend origin (used to build
      password-reset links).
- [ ] If behind a reverse proxy/load balancer: `TRUSTED_PROXY_CIDRS`
      set to its real address range.
- [ ] If running more than one backend instance: `REDIS_URL` set to a
      real, reachable Redis instance (otherwise rate limiting silently
      degrades to per-instance, not distributed).
- [ ] If documents must survive a redeploy or scale past one instance:
      a real object-storage `StorageProvider` implementation built and
      configured (`STORAGE_PROVIDER`, `STORAGE_BUCKET` and the
      corresponding credentials) — not available today.
- [ ] A real container registry set up and a build-and-push CI step
      added (does not exist today — CI only builds, never pushes).
- [ ] Database backup/restore procedure decided, configured, and
      rehearsed at least once.
- [ ] Alembic migrations run as an explicit, observed deployment step
      (the existing backend entrypoint already does this automatically
      on container start — confirm this is the desired behavior for
      the chosen platform, since some platforms prefer a separate
      migration step before traffic is routed to new instances).
- [ ] `docker compose config` (or the target platform's equivalent)
      validated against the real production environment variables
      before first deploy.
- [ ] Health (`/api/v1/health`) and readiness (`/api/v1/health/ready`)
      wired into the platform's own health-check mechanism.
- [ ] A monitoring/alerting approach decided, even a minimal one.
- [ ] A rollback procedure decided and documented (at minimum: how to
      redeploy the previous container image and, if needed, downgrade
      the database to the matching migration).

## Related documents

- [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) — the verified local Docker
  Compose setup this assessment is built on top of.
- [`docs/SECURITY.md`](SECURITY.md) — the security model this
  assessment assumes is already correct (auth, CSRF, workspace
  isolation, rate limiting) and does not re-litigate.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — the provider-abstraction
  pattern (`StorageProvider`, `EmailProvider`, etc.) a real deployment
  would extend, not replace.
- [`docs/DECISIONS/`](DECISIONS/) — where the eventual hosting decision
  will be recorded as a new ADR once made.
