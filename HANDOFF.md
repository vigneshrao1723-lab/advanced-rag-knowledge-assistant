# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Redis distributed rate limiting is fully merged into `main` — both
slices.** Issue #1 and Issue #2 are merged to `main`. ADR 0006's design
was adversarially reviewed and finalized as commit `7e439d2` (pushed,
then itself merged into `main`). Redis **Slice 1** (foundation +
token-bucket engine) was committed as `b1f1b00`, reconciled with a
documentation checkpoint (`c8aa2be`), pushed, opened as **PR #11**, and
**merged into `main` as squash commit `46ef03b`**. Redis **Slice 2**
(wiring that engine into every `enforce_*_rate_limit` dependency, plus
the observability/test-coverage fixes from its own security review — see
below) was then implemented on a fresh branch,
`issue-redis-rate-limiting-slice-2`, committed as `f61737f`, pushed,
opened as **PR #12**, verified green on GitHub Actions CI (3/3 checks),
and **merged into `main` as squash commit `5391a78`**. **`main`/
`origin/main` are currently at `5391a78`.** Both feature branches were
deleted on `origin` after their respective merges. Nothing is pending
review, push, or merge for either slice.

**What this means in practice:** every authentication endpoint's actual
rate-limiting behavior now goes through the Redis-backed engine first,
falling back to the pre-existing in-process limiter per ADR §13 — **this
is a real, observable change, now active in the committed codebase on
`main`.** Verified by automated tests (see "Tests run" below), by
GitHub Actions CI on PR #12 (backend/frontend/Docker-build checks all
passed), and, for the original wiring, by live testing against the
running Docker Compose stack in an earlier checkpoint (including a
genuine Redis outage and recovery). The deterministic abuse-detection
layer (ADR 0006 §11), Playwright, and Issue #3 are all still not
started — do not start any of them without an explicit go-ahead. See
"Next major task" below for what comes next.

Issue #2 (merged) covered: registration/login/logout/refresh with
PostgreSQL-backed sessions, HttpOnly cookie + CSRF browser authentication,
workspace CRUD/membership/RBAC, password recovery (backend and frontend),
audit logging, and the security documentation/ADRs for all of it.

## Completed work (Issue #2, merged in PR #10)

- **Cookie + CSRF authentication migration** (superseding the original
  design where tokens were returned in the JSON response body for the
  frontend to hold and send as `Authorization: Bearer`): access and
  refresh tokens are now delivered exclusively via `HttpOnly` cookies
  (`access_token` on `Path=/`; `refresh_token` narrowly scoped to
  `Path=/api/v1/auth`), never in a response body, never read by
  JavaScript. A double-submit `csrf_token` cookie (deliberately **not**
  `HttpOnly`) + `X-CSRF-Token` header protects every state-changing
  request, including login/register (login-CSRF defense). Cookie
  attributes (`COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`) and CORS
  (`CORS_ALLOWED_ORIGINS`, credentialed) are deployment-aware — see
  [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  for the full model, including the "different origin ≠ cross-site"
  distinction that governs `COOKIE_SAMESITE` (a subdomain split, or
  `localhost:3000` ↔ `localhost:8000`, is same-site despite being a
  different origin — don't set `SameSite=None` for those; it's an
  unforced weakening).
  - Backend: `app/core/cookies.py`, `app/core/csrf.py`,
    `app/core/dependencies.py` (`get_current_token_claims` reads the
    cookie, not a header), `app/main.py` (middleware ordering: CSRF →
    access-log → request-ID → CORS, added in that order so CORS ends up
    outermost and its headers land on CSRF/auth rejections too),
    `app/api/v1/auth.py`, `app/schemas/auth.py` (`AuthResponse = {user}`
    only, no token fields).
  - Frontend: `lib/api-client.ts` fully rewritten (`credentials:
    "include"` on every request, CSRF header attached on state-changing
    requests, `Authorization`/bearer logic and `localStorage`/
    `sessionStorage` token storage entirely removed —
    `lib/auth-storage.ts` deleted), `lib/csrf.ts` (new — reads the
    non-HttpOnly CSRF cookie), `lib/auth-context.tsx` rewritten (auth
    state derived from `getCurrentUser()` on mount, not from storage).
- **Password recovery** — backend and frontend, both complete:
  - Backend: `POST /api/v1/auth/forgot-password` and
    `POST /api/v1/auth/reset-password`
    (`app/services/password_reset_service.py`). Reset tokens are
    `secrets.token_urlsafe(32)` (256 bits), SHA-256-hashed at rest, never
    logged raw, single-use (`used_at`), expiring
    (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`). `forgot-password` always
    returns the same generic response/status regardless of whether the
    email exists, with a dummy Argon2 verification on the not-found path
    for timing equalization. A successful reset revokes every existing
    session for that user (`session_repository.revoke_all_for_user`) and
    reuses the existing Argon2id hashing. Email delivery via the
    `EmailProvider` abstraction (`app/services/email_provider.py`) —
    `console` (stdout, dev/test fallback) or `smtp` (local dev points it
    at Mailpit). **`ENVIRONMENT=production` + `EMAIL_PROVIDER=console`
    now fails at config-load time** (`app/core/config.py`'s
    `_validate_email_provider_for_production`) — this was a genuine
    defect found during audit: stdout is typically captured by log
    aggregation in real deployments, which would have leaked raw reset
    tokens into logs if `EMAIL_PROVIDER` were ever left unset in
    production.
  - Frontend: `app/forgot-password/page.tsx` (email input, generic
    success message, no existence leakage) and
    `app/reset-password/page.tsx` (reads `token` from the URL via
    `useSearchParams` inside a `Suspense` boundary — the page is
    statically prerendered, so the token is only resolved client-side
    after hydration, not server-rendered; this is correct Next.js
    behavior, not a bug, but it means a plain `curl` of the page shows
    the `Suspense` fallback, not the form — don't mistake that for a
    broken page). New password + confirm-password fields with
    client-side match validation (`lib/schemas.ts`'s
    `ResetPasswordFormSchema`), distinct UX for invalid/expired/
    already-used tokens (surfaces the backend's exact message), and a
    "Forgot password?" link added to `/login`.
- **Audit logging**: `app/core/audit.py` (`AuditEvent` string constants,
  not a DB enum, for extensibility) and
  `app/repositories/audit_log_repository.py`. Records registration,
  login success/failure, logout, session revocation, refresh-token reuse
  detection, password-reset request/success, workspace
  create/delete/membership changes, and authorization denials. Writes
  commit immediately/independently of the surrounding request's
  transaction. `user_id`/`workspace_id` use `ON DELETE SET NULL`.
- **Docs**: [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  (new — the cookie/CSRF model and the origin-vs-site distinction);
  `docs/SECURITY.md` corrected (previously stale: described "bearer
  access tokens" and listed audit logging as "not implemented" — both
  fixed to match the current implementation).
- **Tests**: backend went from 95 to **119** pytest tests this checkpoint
  (new: `tests/test_cookie_security.py`, `tests/test_csrf.py` additions,
  `tests/test_password_reset.py` additions, `tests/test_config.py`
  additions for the production email-provider guard). Frontend went from
  30 to **48** vitest tests (new: `lib/api-client.test.ts` and
  `lib/auth-context.test.tsx` regression tests proving no token ever
  reaches `localStorage`/`sessionStorage`/an `Authorization` header;
  `app/forgot-password/page.test.tsx`, `app/reset-password/page.test.tsx`).

## Completed work (Redis/abuse-protection architecture design)

- [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
  — the full design: what's wrong with the current in-process limiter
  (verified from code, not assumed — no cross-instance coordination,
  fixed-window boundary doubling, IP-only keying, no `X-Forwarded-For`
  handling, and the already-defined-but-never-emitted
  `AuditEvent.RATE_LIMITED`); a Redis token-bucket algorithm; hierarchical
  dimensions chosen per-operation (IP/account/session, never applied
  uniformly); a deterministic rule table for abuse detection (not a
  numeric score, not ML); `ALLOW`/`THROTTLE`/`STRICT_THROTTLE`/
  `TEMPORARY_BLOCK` semantics (`REJECT` explicitly left undefined — no
  operation in this system needs it yet); an operation-aware Redis
  failure policy; a Redis key namespace that never stores raw
  credentials/tokens/emails; an observability split (ordinary throttling
  → logs only, escalations → `audit_logs`); Docker/CI implications; and a
  full test strategy — all **design only**.
- **This ADR was then adversarially reviewed for architectural/security
  flaws (a separate, dedicated task) and corrected before this
  checkpoint** — read the ADR itself for the full reasoning, but the
  headline corrections, since they materially change the design from a
  first read of the summary above:
  - **Atomicity is per-operation, not per-key.** The first draft ran one
    independent Lua script per dimension key (e.g., separately for
    `login`'s IP bucket and account bucket) and treated each key's own
    atomicity as sufficient for the combined decision. It wasn't — a
    request could consume one dimension's bucket and then be rejected on
    another, a real partial-consumption/fairness bug. The corrected
    design runs **one Lua invocation per operation, over all of that
    operation's dimension keys together**, all-or-nothing (ADR §8, §10).
  - **Email keys use a keyed HMAC, not plain SHA-256** — a plain hash of
    a low-entropy identifier like an email is dictionary/rainbow-table-
    matchable and isn't a real privacy protection (ADR §14).
  - **The R3 distinct-IP-per-account signal uses a HyperLogLog, not a
    plain Redis `SET`** — a `SET` would let an attacker's own botnet
    inflate Redis memory in direct proportion to the attack the signal
    exists to detect (ADR §11).
  - **R2 (many login failures against one account) escalates to
    `STRICT_THROTTLE`, not a hard `TEMPORARY_BLOCK`** — a hard,
    account-scoped block triggerable by anyone who merely knows a
    victim's (non-secret) email is itself a denial-of-service vector
    against that victim. Only R3 (genuinely distributed source IPs, much
    harder to cheaply fake against a chosen victim) still triggers a
    hard block (ADR §11, §18).
  - **A full trusted-proxy / `X-Forwarded-For` design was added** (ADR
    §9a) — the first draft only flagged the gap; it's now fully
    specified: ignore the header unless a configured
    `TRUSTED_PROXY_CIDRS` trusts the immediate peer, then walk the
    header from the right (never trust a client-supplied leftmost entry).
  - **The Redis-failure section now states plainly what security
    guarantee is lost** in each scenario (single vs. multi-instance,
    which checks fail open vs. fall back) rather than leaving that
    implicit (ADR §13).
  - A full Redis cardinality/memory threat table (every structure: who
    can create it, its bound, its TTL) was added (ADR §18).
- **This is still design work only.** No Redis dependency, Docker
  service, or application code was added; no tests were added or
  modified; no existing code was changed — the adversarial review only
  edited the ADR and this documentation.

## Completed work (Redis implementation slice 1 — foundation + token-bucket engine)

**Merged into `main` as squash commit `46ef03b` via PR #11.** Implemented
the pieces of ADR 0006 that don't require touching any endpoint, per that
slice's explicit scope (superseded by slice 2 below, which wires all of
this in):

- **`redis` dependency** (`redis>=8.1.0` resolved, pinned in
  `backend/pyproject.toml`/`backend/uv.lock` via `uv add redis`, matching
  the project's existing lower-bound-only convention).
- **Settings** (`app/core/config.py`): `redis_url` (optional — `None`
  means the engine is simply unavailable, not a config error),
  `redis_socket_timeout_seconds`/`redis_socket_connect_timeout_seconds`
  (default `0.05`, validated `> 0`), `trusted_proxy_cidrs` (default `""`,
  ADR §9a) + `trusted_proxy_cidrs_list` property.
- **`app/core/redis_client.py`** (new): `build_redis_client()` (explicit
  URL + timeouts, never hardcoded), `get_redis_client()` (settings-backed,
  cached, returns `None` if unconfigured), `is_redis_available()` (never
  raises — catches `redis.RedisError`), `RedisUnavailableError`.
- **`app/core/redis_keys.py`** (new): `rate_limit_key(operation,
  dimension, value)` (ADR §14's `rl:{operation}:{dimension}:{value}`
  namespace) and `hash_account_identifier(email, key=...)`
  (HMAC-SHA256, ADR §14's corrected email-identifier design — never a
  plain hash).
- **`app/core/ip_resolution.py`** (new): `resolve_ip()` (pure function)
  and `resolve_client_ip()` (`Request` wrapper) implementing ADR §9a's
  trusted-proxy walk. Not called from any endpoint as of this Slice 1
  checkpoint — Slice 2 (below, now also merged) is what wires it in.
- **`app/core/rate_limit.py`** (extended, not replaced): `DimensionSpec`,
  `TokenBucketResult`, `RedisTokenBucketLimiter` — the ADR §8/§10 Lua
  token-bucket engine. One `EVAL` per operation, over every dimension key
  that operation has; reads/refills/checks all dimensions before writing
  any; writes nothing on rejection. `FixedWindowRateLimiter` and every
  `enforce_*_rate_limit` function are **byte-for-byte unchanged**.
- **`infra/compose/docker-compose.yml`** / **`.github/workflows/ci.yml`**:
  a pinned `redis:7.4-alpine` service, healthcheck-gated (`redis-cli
  ping`), matching the existing `mailpit`/`db` pattern. `backend`'s
  `depends_on: redis: condition: service_healthy` is container-startup
  ordering only (ADR §13 explicitly sanctions this — distinct from
  runtime readiness). `.env.example` documents the new variables.
- **A genuinely hard problem, documented in `SOLVING.md`**: Redis's
  Lua→RESP2 reply conversion silently truncates a returned float to an
  integer — the token-bucket script computes/returns `retry_after_ms` as
  an integer instead of fractional seconds specifically to survive this,
  with the unscaling done on the Python side.

## Completed work (Redis implementation slice 2 — wire the engine into every endpoint)

**Merged into `main` as squash commit `5391a78` via PR #12**, on top of
the merged Slice 1 (`46ef03b`):

- **`app/core/rate_limit.py`'s `enforce_*_rate_limit` functions rewritten**
  to attempt the Redis engine first, per ADR §9's exact per-operation
  dimensions, falling back to `FixedWindowRateLimiter` per ADR §13:
  - `register`: IP only. Tier B.
  - `login`: IP + account (email extracted from the JSON body via a new
    `_extract_email_from_json_body()` helper — a best-effort peek that
    never blocks normal Pydantic validation, since `Request.json()`
    caches the raw bytes). Tier A.
  - `refresh`: IP + session ID (parsed from the refresh-token cookie via
    the existing `parse_refresh_token()` in `app/core/security.py` — no
    database round-trip, per ADR §7's hot-path requirement). Tier A.
  - `forgot-password`: IP + account (same email-extraction approach as
    `login`). Tier A.
  - `reset-password`: IP only, per ADR §9's reasoning (the token's own
    256-bit entropy is the real defense). Tier A.
  - A shared `_check_or_fallback()` helper implements the tier logic once,
    used by all five functions.
  - `get_redis_client` is now injected via `Depends()` (not called as a
    plain function) specifically so tests can override it with
    `app.dependency_overrides` — this is what makes the Tier A/B tests
    below possible without needing to actually kill a real Redis.
- **A deliberate refinement of ADR §13's Tier B, resolving its own
  explicitly-left-open sub-decision** (full writeup: `SOLVING.md`'s
  2026-09-14 "ADR 0006 §13's Tier B..." entry; also recorded in ADR
  0006's "Implementation status" and §22): `get_redis_client()` returning
  `None` (Redis never configured — today's default everywhere) always
  falls back to `FixedWindowRateLimiter`, for every operation including
  `register`. Only a `RedisUnavailableError` from an *already-configured*
  client triggers Tier B's literal fail-open. Implementing the ADR's
  literal wording without this distinction would have made `register`
  unprotected by default in every environment that hasn't explicitly set
  `REDIS_URL` — i.e. every environment today.
- **`FixedWindowRateLimiter` gained `.limit`/`.window_seconds`
  properties** so the Redis dimensions' capacity/refill-rate are derived
  live from the same objects, never a second hardcoded copy of the same
  numbers (ADR §8 "Continuity with today's numbers").
- **New setting**: `rate_limit_hash_key` (`app/core/config.py`) —
  resolves ADR §14/§22's open "HMAC key location" decision by reusing
  `secret_key` unless explicitly overridden, avoiding a new required
  secret for a threat model that doesn't need key separation from JWT
  signing to be effective.
- **`backend/tests/conftest.py` fixed**: `_reset_rate_limiters` now also
  clears `rl:*` Redis keys between tests (via `SCAN`+`DELETE`), not just
  the in-process limiters — see `SOLVING.md`'s first 2026-09-14 entry for
  why this was necessary (52 previously-passing tests failed the moment
  the Redis path went live in tests, until this fix).
- **`tests/test_rate_limit_wiring.py`** (HTTP-level, through real
  endpoints; started at 5 tests, now 13 — see the review/fixes entry
  below for the 8 added since): a successful login creates the exact
  `rl:login:ip:*`/`rl:login:acct:*` keys ADR §14 specifies; Tier A
  fallback and Tier B fail-open, both via `app.dependency_overrides`
  pointing `get_redis_client` at an unreachable client; the
  "unconfigured vs. unreachable" distinction (`None` override still
  rate-limits `register`); a spoofed `X-Forwarded-For` does not let an
  attacker escape the IP bucket with `TRUSTED_PROXY_CIDRS` unset.
- **Live-verified against the real Docker Compose stack** (not just
  tests): a live login created real `rl:login:ip:*`/`rl:login:acct:*`
  keys (inspected directly via `redis-cli --scan`); `/api/v1/health/ready`
  stayed `200 ready` with Redis stopped; `register` failed open (7/7
  succeeded past the base limit of 5) only while Redis was actually down,
  and `login` still hit `429` at exactly the fallback limiter's threshold
  during that same outage (Tier A); stopping and restarting Redis
  mid-session, `register` went from failing open back to enforcing its
  limit at exactly 5 with no process restart.

### Slice 2 read-only security/architecture review, and the fixes it produced

A dedicated read-only review of the uncommitted Slice 2 diff (endpoint
wiring, Redis failure policy, HMAC construction, trusted-proxy IP
handling, test quality, observability, performance/failure modes,
documentation consistency) found 0 P0, 3 P1, 3 P2, 2 P3 findings. All 3
P1s and the most important P2 (HTTP-level test coverage) were then fixed,
still entirely within Slice 2's uncommitted working tree:

- **P1 — documentation staleness (this reconciliation).** `HANDOFF.md`,
  `PROJECT_STATE.md`, `docs/SECURITY.md`, and ADR 0006 still described
  "slices 1–2, uncommitted" as one unit, predating even Slice 1's own
  commit — corrected here to reflect Slice 1 merged (`46ef03b`, PR #11)
  and Slice 2 uncommitted, on the new branch name.
- **P1 — Redis-failure fallback was unobservable.** ADR 0006 §13
  explicitly requires a structured log line when the rate limiter
  degrades to its fallback on a genuine Redis outage; none existed.
  Added `_log_redis_fallback()` in `app/core/rate_limit.py`, using the
  project's existing `logging.getLogger("app.<domain>")` +
  `extra={...}` convention (matching `auth_service.py`/`access_log.py`).
  Logs only `operation` (a fixed, non-secret literal) and `policy`
  (`fail_open` or `fallback_to_in_process_limiter`) — never an email, IP,
  token, or secret. Fires only on a genuine `RedisUnavailableError`, not
  on the normal "Redis never configured" default state (which would be
  noisy and uninformative on every single request in every environment
  that hasn't opted into Redis).
- **P1 — stale docstrings.** `redis_client.py` and `ip_resolution.py`
  still said "not wired into any endpoint yet" (accurate when Slice 1
  alone was committed, false once Slice 2 lands) — corrected to describe
  their actual role as of this slice, including
  `resolve_client_ip()`'s own docstring, which had the same claim.
- **P2 — missing HTTP-level test coverage**, now closed: Redis-key-
  creation tests for `refresh` (proves the session dimension key holds
  only the session ID, never the refresh token's secret half) and
  `forgot-password` (mirroring the existing `login` test); a
  `reset-password` test proving it creates only an IP-dimension key,
  never an account/session one; Tier A fallback tests for `refresh`/
  `forgot-password`/`reset-password` (previously only `login`/`register`
  had them); an endpoint-driven multi-dimension atomicity regression test
  for `login` (proves `enforce_login_rate_limit` wires both dimensions
  into one `check_all()` call — a losing account-dimension check must
  never have touched a fresh IP's own bucket); and a cross-user
  account-isolation test (account A's exhausted bucket must not throttle
  account B, verified using `TestClient(app, client=(ip, port))` for two
  genuinely different peer IPs, so the shared-IP dimension can't confound
  the result). 8 new tests, `test_rate_limit_wiring.py` 5 → 13.
- **Remaining P2/P3, intentionally not addressed in this pass** (see
  "Explicitly NOT done" below): an endpoint-driven concurrency test under
  real HTTP load; ordinary `THROTTLE`/429 rejections still aren't logged
  (a broader, pre-existing gap, not introduced by Slice 2);
  `ip_resolution.py`'s docstring still slightly overstates `Forwarded`
  (RFC 7239) support that was never implemented (fails safe, not a
  security gap — explicitly out of scope per this task's own
  instruction not to expand into `Forwarded`-header work).
- Full suite re-verified after these fixes: **183/183 passing** (real
  Postgres + real Redis, re-run 3 times, no flakiness), `ruff`/`mypy`
  clean.

## Explicitly NOT done (do not assume otherwise)

- **Deterministic abuse/risk layer** (ADR 0006 §11/§12) — not started. No
  `AbuseDecisionEngine`, no rule table, no `abuse:*` Redis keys, no
  `STRICT_THROTTLE`/`TEMPORARY_BLOCK` escalation is reachable yet. (When
  you build this: it must remain deterministic, rule-based logic — never
  call it "AI" or claim ML/statistical evaluation unless an actual
  evaluated model backs that claim, per the ADR's explicit non-goal.)
- **`AuditEvent.RATE_LIMITED` is still never emitted** — the observability
  split (ADR §15) is designed but not implemented; no audit-logging code
  was added in either slice.
- **`client_ip()` (unconditional, no trusted-proxy handling) is still
  used elsewhere** — `app/api/v1/auth.py`'s audit/session IP recording
  and `app/core/dependencies.py`'s authorization-denial audit events
  still call `client_ip()`, not `resolve_client_ip()`. Only the
  rate-limit dimensions switched to the trusted-proxy-aware resolver;
  changing what IP audit logs/sessions record is a separate decision,
  deliberately out of scope here.
- **No multi-instance/concurrent-HTTP-load test exists** — the wiring is
  verified correct sequentially (tests) and against a single running
  backend instance (Docker). The distributed-coordination property this
  whole ADR exists for (§2.1) has not been exercised with more than one
  backend process under real concurrent load, since no such deployment
  exists.
- **Playwright browser E2E** — not started. No config, no test files, no
  dependency.
- **Issue #3 (document ingestion)** — not started.
- **Later RAG retrieval/generation features** — not started.
- **Endpoint-driven concurrency test under real HTTP load** — not added
  in the Slice 2 review-fix pass either; the property is proven at the
  engine level (`test_redis_rate_limiter.py`, merged with Slice 1) and
  sequentially at the endpoint level, not under genuinely concurrent HTTP
  traffic.
- **Ordinary `THROTTLE`/429 rejections still aren't logged** (ADR §15) —
  only the Redis-failure *fallback* path gained logging in this pass; a
  broader, pre-existing gap belonging with the future abuse-detection/
  observability work, not a Slice 2 regression.
- **Both Slice 1 (`46ef03b`, PR #11) and Slice 2 (`5391a78`, PR #12) are
  merged into `main`.** Both feature branches were deleted on `origin`
  after their respective merges.

## Next major task: the deterministic abuse-detection layer (ADR 0006 §11/§12)

**Both Redis slices are now merged — this is genuinely the next planned
piece of ADR 0006, but still requires its own explicit go-ahead before
any code is written**, same as every other unit of work in this
repository (`AGENTS.md` §6). Recorded here so the plan stays visible,
not as a standing instruction to start it. When it is time: **read
[ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
§11/§12 in full before writing any code.** This is the last major piece
of ADR 0006 that doesn't exist yet:

- **Rule table (§11)**: R1–R5, deterministic `if`-level checks against
  counters — not a numeric score, not ML. Needs its own signal-recording
  primitives (login-failure counters per IP/account, the HyperLogLog
  distinct-IP-per-account signal, reset-token-failure counters), all
  TTL-bound (§18's cardinality analysis).
- **Decision states (§12)**: `STRICT_THROTTLE` (a second, stricter token
  bucket activated for an escalation window) and `TEMPORARY_BLOCK`
  (checked first, before the ordinary bucket, per §6's flow diagram —
  this needs its own read-only "is this dimension currently blocked?"
  check wired in ahead of the `RedisTokenBucketLimiter.check_all()` calls
  slice 2 just added).
- **R2's severity is `STRICT_THROTTLE`, not `TEMPORARY_BLOCK`** — this
  was the account-lockout-as-DoS-vector correction from the design
  review; don't regress it.
- **Audit emission (§15)**: this is also where `AuditEvent.RATE_LIMITED`
  finally gets emitted (for `STRICT_THROTTLE`) alongside a new constant
  for `TEMPORARY_BLOCK`.
- **§11/§22's open numeric thresholds** (`N`, `M`, `W` per rule) need
  actual values chosen and documented with rationale — this repository
  has no incident history to derive them from; start conservative.
- Files likely touched: a new `app/core/abuse_detection.py` (or similar —
  not decided here), `app/core/audit.py` (new constant),
  `app/core/rate_limit.py`'s `enforce_*` functions (the block-check needs
  to run before `_check_or_fallback()`, per §6's flow).

After that: Playwright E2E, then GitHub Issue #3 — neither started.

## Blockers

None. Docker Compose, the local Postgres container, Mailpit, a local
Redis, and `gh` CLI access are all confirmed working in this environment.

## Tests run

- Baseline (before Redis, per Slice 1's explicit instruction):
  `uv run ruff check .` (pass), `uv run mypy .` (pass, 67 files),
  `uv run pytest -v` (**119/119 pass**, real Postgres).
- **Slice 1 (merged, `46ef03b`): 170/170 pass** (119 existing + 51 new),
  `mypy` clean (74 files) — independently re-validated in an isolated
  worktree before that commit; see PR #11's own record.
- **Slice 2, before this checkpoint's review-fix pass:** `uv run ruff
  check .` (pass), `uv run mypy .` (pass, 75 files), `uv run pytest -v`
  (**175/175 pass** — 170 from Slice 1 + 5 HTTP-level wiring tests,
  against real Postgres **and** real Redis).
- **Slice 2, after the review's P1/P2 fixes, pre-merge:** `uv run ruff
  check .` (pass), `uv run mypy .` (pass, **75 files**), `uv run pytest
  -v` (**183/183 pass** — 170 from Slice 1 + 13 from
  `test_rate_limit_wiring.py`, against real Postgres **and** real
  Redis). Re-ran the full suite 3 times to check for flakiness — none
  observed. This was the exact code committed as `f61737f` and merged
  as `5391a78` — **this 183/183 figure now describes the committed
  codebase on `main`**, not just a working tree.
- **PR #12, GitHub Actions CI (post-merge verification, independent of
  the local run above):** 3/3 checks passed — backend lint/typecheck/
  tests, frontend lint/typecheck/tests/build, Docker build check. This
  session's own Docker/WSL integration became unavailable shortly after
  the local 183/183 run above, so this CI result is the first
  re-verification of the merged code since then.
- New tests this checkpoint (8, added to `test_rate_limit_wiring.py`):
  Redis-key-creation tests for `refresh` and `forgot-password`; a
  `reset-password` test proving IP-only dimension creation; Tier A
  fallback tests for `refresh`/`forgot-password`/`reset-password`; an
  endpoint-driven multi-dimension atomicity test for `login`; a
  cross-user account-isolation test. See the "Slice 2 read-only
  security/architecture review" entry above for what each proves.
- Docker: full stack live-verification of the original wiring is
  unchanged from the prior checkpoint (see "Completed work" above) — not
  re-run this checkpoint, since the fixes were logging/docstring/test
  additions only, not a change to the wiring's runtime behavior.
- Frontend: untouched across every Redis checkpoint — not re-run (no
  frontend file changed).

## Exact next recommended action

Both Redis slices are merged into `main` (`46ef03b` via PR #11, `5391a78`
via PR #12) — nothing pending for either. The next work, in order:

1. **Implement the deterministic abuse-detection layer** (ADR §11/§12) —
   see "Next major task" above. Not started; requires its own explicit
   go-ahead before any code is written, per `AGENTS.md` §6's workflow.
2. **Then:** Playwright browser E2E for the authentication/
   password-recovery flows — not started.
3. **Then:** begin GitHub Issue #3 (Knowledge Ingestion) — not started.
