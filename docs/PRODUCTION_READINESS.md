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
- **Migrations**: Alembic is at head (`0010`), applies cleanly on a
  fresh database (the backend entrypoint runs `alembic upgrade head`
  automatically on container start), and every individual migration in
  this project's history has been verified reversible
  (`downgrade`/`upgrade` round-tripped against the real database) at
  the time it was added. Re-verified in the 2026-10-27 release audit: the
  full chain `upgrade head` → `downgrade base` → `upgrade head` ran
  cleanly against a scratch database (17 public tables afterwards).
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
  E2E, Docker build) green on every merged PR (most recently #49 and the
  2026-10-27 audit fix PR — see `CHANGELOG.md`).
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

## Release audit, 2026-10-27 (what was actually exercised)

Run against a freshly built, disposable Docker Compose project
(`-p ragaudit`, fresh volumes, disposable accounts) at `main` @ `52985a9`,
then re-run on the fix branch. Nothing was deployed anywhere. Evidence is
scripted HTTP against the real containers, a headless-Chromium run of the
real UI, and the full test suites:

- **Auth**: register/login/logout, refresh rotation + replayed-token
  rejection, CSRF (missing/wrong header → 403), cookie-only auth (a `Bearer`
  header alone does not authenticate), full password recovery through real
  SMTP → Mailpit (enumeration-resistant, single-use token, pre-reset refresh
  revoked, old password rejected), brute-force → 429, spoofed
  `X-Forwarded-For` ignored by default, no password/JWT in backend logs.
- **Workspaces/authorization**: roles (OWNER/MEMBER/VIEWER), last-owner
  protection, ~40 non-member and cross-workspace requests (every endpoint,
  including a document/chunk/conversation/message ID from workspace A used
  through workspace B's own path) → 404; VIEWER mutation attempts → 403;
  denied attempts are audited.
- **Documents**: PDF/DOCX/TXT/MD/CSV upload → READY; bad extension, wrong
  magic bytes, bad MIME, 50 MB+ (413), duplicate (409), malformed PDF
  (FAILED with reason); traversal filename never reaches the storage key;
  stored files survive backend container recreation (6/6 SHA-256 identical);
  rename/filter/download (byte-identical)/delete (row, chunks, citations,
  collection link, stored file all removed; chat text untouched).
- **RAG**: search ranks the right document first for every type; answers are
  grounded with citations that resolve to real chunks; regenerate keeps the
  message id, clears feedback, replaces citations without stale rows;
  prompt-injection text in a document is only quoted as inert evidence.
- **Voice** (local providers): TTS → WAV → STT round-trip works through the
  voice endpoint (transcript accuracy is poor, as documented in ADR 0008);
  garbage/oversize audio → 4xx.
- **Operations**: DB stopped → `/health/ready` 503 while `/health` stays 200,
  no stack trace in the API error, recovers by itself when the DB returns;
  production mode refuses `EMAIL_PROVIDER=console`, sets `Secure` cookies,
  enforces the CORS allowlist.
- **Tests**: backend 825 passed + 2 skipped in the image (one intentional
  full-checkout skip, one fixture-validity module that skips without
  `eval/`), `ruff`/`mypy` clean; frontend lint/tsc/113 vitest/build clean;
  Playwright 21/21; headless-Chromium run of the Issue #41 UI (collections,
  search page, document rename/download/delete, citation → viewer with the
  cited chunk highlighted, regenerate, command palette incl. `Ctrl+K` while a
  text field is focused, no horizontal overflow at 375 px) 29/30, the one
  "failure" being the expected pre-login `GET /users/me` 401.

### Defects found and fixed (PR #51, Issue #50)

1. Downloading a document whose filename has non-Latin-1 characters (CJK,
   emoji — even an upload named `データ.txt`) returned HTTP 500.
2. The document filename filter treated `%`/`_` as SQL LIKE wildcards.

### Verified limitations found and NOT fixed (need an owner decision)

1. **~~No relevance gate before generation.~~ FIXED 2026-10-28 (#55):** off-topic questions now get the fixed no-evidence answer; the original finding: off-topic questions still got a
   "Based on the available documents…" answer with citations (3/3
   unanswerable eval queries; also reproduced live). `docs/EVALUATION.md`
   "Larger fixture" has the measurements and why a similarity threshold
   doesn't work with the local hashing embedder. Previous docs implied the
   no-evidence answer covers this; it only fires for an empty workspace.
2. **Redis outage can stall the whole API.** With the Redis *hostname*
   unresolvable (container stopped), every rate-limited request took ~4 s
   and `GET /health` itself took 3.4 s while a request was stalled: the
   sync Redis call (DNS resolution is not covered by the 50 ms socket
   timeouts) runs on the event loop. The in-process fallback does engage
   afterwards. Mitigations: run without `REDIS_URL` on a single instance,
   or fix with a circuit breaker / threadpool call (changes ADR 0006's
   failure policy → needs ADR review).
3. **~~Lexical search is near non-functional for natural-language questions~~ FIXED 2026-10-28 (#55; OR matching, 0 of 16 empty results):** original finding:
   (AND semantics: 0 results for 14 of 16 eval questions), so hybrid
   behaves as dense-only.
4. **No security response headers** (`X-Content-Type-Options`,
   `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`, HSTS, CSP) from
   either service; HSTS/TLS belong to the host/proxy, the rest are a small
   `next.config.ts` `headers()` + middleware change (not made; a CSP needs
   care with Next.js inline scripts, and `Permissions-Policy` must keep
   `microphone` for voice).
5. **`/docs` and `/openapi.json` are public in production mode** (fine for
   a portfolio demo; decide deliberately).
6. **Empty (0-byte) uploads are accepted** and then end `FAILED` with a
   reason at processing time — honest but wasteful; low severity.
7. **429 responses carry no `Retry-After` header.**
8. `infra/compose/docker-compose.yml` publishes Postgres (5432), Redis
   (6379) and Mailpit on all host interfaces with the default `ragpass`
   password — correct for local dev, **unsafe on a public host**. A
   production compose/runtime config must not reuse it as-is.
9. Voice/STT peak memory and behavior under load were not profiled; idle
   container memory was measured (backend ≈123 MiB, frontend ≈57 MiB,
   Postgres ≈43 MiB, Redis ≈6 MiB).

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

## Hosting options compared (research, not a decision)

Prices were read from each provider's own page on **2026-10-27**. Several
pages carry no "last updated" date; treat every figure as "as of that
fetch" and re-check before paying. INR figures assume **₹95 per USD** —
the latest RBI reference rate found for USD/INR was 94.5975 on 30-Jun-2026
(no October 2026 rate could be verified), so INR is an estimate that moves
with the exchange rate. Taxes (GST), payment-card FX fees and a domain name
are **not** included; domain price was not researched (**unknown**). Nothing
here has been provisioned, purchased or deployed.

**Hetzner was excluded**: its own cloud pages list every Cost-Optimized and
Regular Performance plan as currently unavailable for new orders.

**Constraint that applies to every option — same-site cookies.** Auth uses
HttpOnly cookies with `SameSite=Lax` and a double-submit CSRF cookie
(ADR 0005). The browser must see frontend and API as the *same site*. Two
different provider-assigned hostnames (e.g. `x.onrender.com` and
`y.onrender.com`) are very likely different sites (whether a given
provider domain is on the Public Suffix List was not verified), which would
silently break login. Use either one hostname with path routing
(`/api/*` → backend, everything else → frontend) or two subdomains of a
domain you own (and set `COOKIE_DOMAIN`, `CORS_ALLOWED_ORIGINS`,
`FRONTEND_URL`, `NEXT_PUBLIC_API_URL` accordingly). Either way, **buying a
domain is effectively required**.

### Option A — One small VPS running the existing Compose stack (DigitalOcean Droplet)

| Item | Detail |
|---|---|
| Hosting | 1 Droplet; Caddy (or nginx) in front: auto-TLS, single hostname, `/api/*` → backend:8000, rest → frontend:3000. Production compose file with **no published db/redis ports**. |
| Postgres + pgvector | `pgvector/pgvector:pg16` container on the same VM (already verified). **No managed PITR.** |
| Redis | Omit (`REDIS_URL` unset): the in-process limiter is correct for one process and avoids the Redis-outage stall above. |
| Object storage | Not needed for a single VM: documents live on the VM disk (named volume), included in Droplet backups. A S3-compatible `StorageProvider` (new code) is only needed to scale out; Cloudflare R2 is the candidate (free tier 10 GB-month storage, 1 M Class A / 10 M Class B ops per month, zero egress; $0.015/GB-month beyond; Cloudflare R2 pricing page, 2026-10-27). |
| SMTP | Amazon SES: $0.10 per 1,000 emails (SES pricing page, 2026-10-27); needs a verified domain and moving out of the sandbox (not verified here). Brevo's free-tier limits could not be read (page returned no pricing) → **unknown**. |
| Secrets | `.env` on the VM, `chmod 600`, never in git; generate `SECRET_KEY` with `openssl rand -hex 32`. No secrets manager. |
| Backups/restore/rollback | Droplet weekly backups cost 20% of the Droplet price (DO page). Droplet backups are crash-consistent disk images, not a database-aware dump → add a nightly `pg_dump` shipped off-site (e.g. R2) and **rehearse a restore**. Rollback = `docker compose up` the previous image tag + `alembic downgrade` to the matching revision (all 10 migrations verified reversible). |
| Monitoring/alerts | None built in beyond provider CPU/disk graphs; add an external uptime check on `/api/v1/health/ready` and ship JSON logs from `docker logs`. No `/metrics` endpoint exists. |
| Cost (est.) | 1 GiB/1 vCPU Droplet $6.00 (idle stack ≈230 MiB measured, peak unmeasured → tight); **2 GiB/1 vCPU $12.00 recommended**. +20% weekly backups = **$14.40/mo ≈ ₹1,370/mo** (or $7.20 ≈ ₹685 with the 1 GiB size). Plus domain (unknown), plus SES pennies. |
| Operational complexity | Highest: OS patching, firewall (only 22/80/443), TLS renewals, backups, log rotation are yours. |
| Migration effort | **Lowest**: no application code changes; write a production compose file + Caddyfile + backup script. |
| Limitations | Single point of failure; no horizontal scale; deploys cause brief downtime; DB restore is only as good as the dumps you rehearse. |

### Option B — Render (managed PaaS: 2 web services + managed Postgres + persistent disk)

| Item | Detail |
|---|---|
| Hosting | Backend and frontend as Docker web services (Dockerfiles already exist). Single instance each because a persistent disk (below) pins the backend to one instance. |
| Postgres + pgvector | Render Postgres; `pgvector` supported (Render docs: "support a wide variety of popular extensions (`pgvector`, `postgis`, …)"; enable with `CREATE EXTENSION vector;`). PITR listed: 3 days on Hobby, 7 days on Pro and above (workspace-plan prices not researched → unknown). |
| Redis | Omit for one instance, or Render Key Value: Free 25 MB (no persistence), 256 MB $10/mo. |
| Object storage | Render persistent disk $0.25/GB/month mounted at `/app/data/documents` → `LocalStorage` works unchanged (disk requires a paid web service — not verified on the pricing page). R2/S3 provider only needed to scale out. |
| SMTP | As Option A (SES or another SMTP relay). |
| Secrets | Render environment variables / secret files (encrypted at rest by the platform — not verified here). |
| Backups/restore/rollback | Managed PITR (above); app rollback via redeploying a previous deploy/commit; `alembic downgrade` still manual. The backend entrypoint runs migrations at every container start — fine for one instance. |
| Monitoring/alerts | Platform logs/metrics and health-check-based restarts (point the health check at `/api/v1/health/ready`); alert channels not researched. |
| Cost (est.) | Backend 1 CPU/2 GB **$25** (0.5 CPU/512 MB at $7 is cheaper but likely too small for an unprofiled voice/PDF path) + frontend 0.5 CPU/512 MB **$7** + Postgres 1 GB **$19** (256 MB at $6 is too small for pgvector indexes of any size) + 5 GB disk **$1.25** = **$52.25/mo ≈ ₹4,960/mo**; a bare-minimum variant ($7+$7+$19+$1.25 = $34.25 ≈ ₹3,250/mo) is possible but unsized. Plus domain (unknown). Free-plan limits (spin-down, free Postgres expiry) were **not verifiable** from the pricing page. |
| Operational complexity | Low: no OS, TLS or proxy to run. |
| Migration effort | Low–medium: `render.yaml`/dashboard setup, env vars, custom domain wiring for same-site cookies, disk mount. No app code changes. |
| Limitations | Single instance (disk), disk-attached deploys are not zero-downtime, ~3.5× Option A's cost. |

### Option C — Fly.io machines + Neon (serverless Postgres) [+ Upstash Redis]

| Item | Detail |
|---|---|
| Hosting | Two Fly Machines (backend, frontend) + one Fly volume. shared-cpu-1x: 256 MB $2.19, 512 MB $3.69, 1 GB $6.70/mo; the page lists no 2 GB shared-cpu-1x (shared-cpu-2x 2 GB $13.39); RAM above preset $6.00/GB (Fly pricing page, 2026-10-27, undated). New organisations have no free tier. |
| Postgres + pgvector | **Neon**: Free = $0, 1 GB storage/project, 100 CU-hours, **scale-to-zero after 5 min that cannot be disabled on Free**, 6-hour restore window; pgvector supported on all plans. Launch: usage-priced ($0.35/GB-month, $0.106/CU-hour, up to 7-day restore). (Fly's own Managed Postgres starts at $38/mo, pgvector not mentioned → not considered.) |
| Redis | Omit, or Upstash: Free 250 MB / 500 K commands per month; Fixed 250 MB $10/mo (Upstash pricing page, 2026-10-27). |
| Object storage | Fly volume ($0.15/GB-month, snapshots $0.08/GB-month, first 10 GB free) with `LocalStorage` on one machine; R2 for scale-out as above. |
| SMTP | As Option A. |
| Secrets | `fly secrets` (platform feature; not researched in detail). |
| Backups/restore/rollback | Neon restore window above (free: 6 h only); Fly volume snapshots; `fly deploy` previous image to roll back. |
| Monitoring/alerts | Fly metrics/logs; alerting not researched. |
| Cost (est.) | Backend 1 GB $6.70 + frontend 512 MB $3.69 + 1–5 GB volume $0.15–0.75 + Neon Free $0 = **≈ $10.5–11.2/mo ≈ ₹1,000–1,060/mo** + egress ($0.12/GB for India, $0.02/GB NA/EU) + domain (unknown). **Neon compute for always-on use is unknown/unbounded**: `/api/v1/health/ready` does a DB round-trip, so platform health checks would keep a Free database awake and could exhaust the 100 CU-hour allowance (minimum CU size not verified). |
| Operational complexity | Medium: three vendors, CLI-driven deploys, free-tier quirks. |
| Migration effort | Medium: `fly.toml`s, Neon connection string; cold-start behavior (first query after suspend, pool reconnects) is **untested** against this app. |
| Limitations | Scale-to-zero latency and connection resets untested; free-tier restore window is only 6 h; most moving parts. |

### Recommendation (for a student portfolio project)

**Option A (single Droplet, Compose + Caddy), 2 GiB size.** Rationale:
lowest cost (≈₹1,370/mo against ≈₹4,960 for Render), **zero application code
changes**, the exact stack that was verified end to end, and a single
hostname with path routing makes the cookie/CORS/CSRF model work without
extra moving parts. It deliberately drops Redis (one process), which also
removes the Redis-outage stall finding. Accept and document its
weaknesses: you run backups and patching. Mandatory before going live:
production compose without published DB/Redis ports and with a real DB
password, `ENVIRONMENT=production`, nightly off-site `pg_dump` **with a
rehearsed restore**, firewall, an external uptime check, and the security
headers item above. Choose Option B instead if you would rather pay roughly
₹3,500 more per month to not operate a server and to get managed PITR;
Option C is cheapest on paper but has the most unverified behavior.

Availability of the chosen Droplet size/region from India and the
card/payment route for a USD-billed provider were **not verified**; whether
student credits apply to DigitalOcean was **not researched**. This is a
recommendation only: per `CLAUDE.md` §4 the choice, the account, the spend
and the domain are the owner's decision.

Sources (all fetched 2026-10-27): [Render pricing](https://render.com/pricing.md) ·
[Render extensions](https://render.com/docs/postgresql-extensions) ·
[Fly.io pricing](https://docs.fly.io/about/pricing) ·
[Neon pricing](https://neon.com/pricing) ·
[Upstash Redis pricing](https://upstash.com/pricing/redis.md) ·
[DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets) ·
[Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/) ·
[Amazon SES pricing](https://aws.amazon.com/ses/pricing/) ·
[Hetzner Cloud](https://www.hetzner.com/cloud/regular-performance/) ·
USD/INR from the RBI reference-rate archive (as listed by search results; 30-Jun-2026 value).

## Deployment impact of the AI and voice components (2026-10-28)

The hosting comparison above was researched **before** the app had a language model
or a neural speech recogniser. It is now materially out of date on sizing and cost:

| Component | Measured footprint (development machine) |
|---|---|
| Backend with Whisper "small" loaded | ≈ **1.2 GiB** RAM (was ≈ 0.12 GiB idle) |
| Speech model files | 464 MB on disk |
| Local LLM (qwen2.5:3b-instruct, 8192-token context) | ≈ 1.2 GiB RAM in the Ollama container **and 2.3 GB of GPU memory** (100 % on an RTX 3050 4 GB) |
| Docker images | backend 2.28 GB (was 1.14), frontend 0.31 GB, Ollama **8.47 GB** |
| Answer time | 7–17 s on that GPU; CPU-only generation was **not measured** and is expected to be far slower |

Consequences for the options:

- **A 1 vCPU / 2 GiB droplet (the earlier Option A) cannot run this**: Postgres + frontend
  + the backend with Whisper loaded already approach 2 GiB, and there is no GPU for the
  model. Minimum for the app with local Whisper is roughly the 4 GiB tier ($24/mo ≈ ₹2,280
  at the same ₹95/USD assumption, before backups) — 2 GiB would need a smaller Whisper
  (`tiny`/`base`) or hosted speech.
- **The language model needs a decision of its own** (none of these were researched or
  priced here — their cost is **unknown**):
  1. a **hosted OpenAI-compatible API** (set `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`):
     pay per use, and the question, recent history and retrieved passages leave the
     server — an explicit privacy/cost choice;
  2. a **GPU host** running Ollama: much more expensive than the plans above;
  3. a CPU-only local model: not recommended (unmeasured; likely too slow).
- Speech can stay local (CPU) on a ≥ 4 GiB host, or use a self-hosted/hosted
  `/audio/transcriptions` server (audio leaves the machine).
- Browser speech and microphone access need HTTPS (or localhost): another reason a
  domain and TLS are mandatory.

So the practical shape of a public deployment is now: a ≥ 4 GiB app host **plus** a hosted
LLM endpoint, with the monthly cost dominated by an LLM bill that has not been estimated.
The earlier ranking of Options A/B/C by app-host price alone should not be relied on until
that bill is researched.

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
- [ ] A domain bought and DNS configured so frontend and API are the same
      site (see "Constraint that applies to every option").
- [ ] A production compose/runtime config that does **not** publish
      Postgres/Redis/Mailpit ports and does not use the `ragpass` default.
- [ ] Security response headers added (see audit limitation 4).
- [ ] Decision recorded on the relevance-gate and Redis-outage findings
      (audit limitations 1–2) before real users depend on answers.

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
