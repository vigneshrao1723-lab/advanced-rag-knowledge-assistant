# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Redis distributed rate limiting — Slice 1 is committed locally; Slice 2
exists only as uncommitted working-tree changes on top of it, both on
branch `issue-redis-rate-limiting`.** Issue #1 and Issue #2 are merged to
`main` (Issue #2 merged as `ec4225d`; `main`/`origin/main` have since
advanced further, to `7e439d2`, via the ADR 0006 design-finalization
commits, committed directly to `main` in an earlier session — that is
`main`'s current tip, not `ec4225d`). ADR 0006's design was adversarially
reviewed and finalized as part of that same `7e439d2` commit (pushed).

- **Slice 1 (Redis foundation + token-bucket engine): IMPLEMENTED and
  COMMITTED** as commit `b1f1b00` on `issue-redis-rate-limiting`, on top
  of `7e439d2`. **Not yet pushed. No PR open.** Independently validated
  in isolation before the commit: 170/170 tests pass (119 baseline + 51
  new), `ruff`/`mypy` clean. This is the current committed checkpoint —
  the next action is to review, push, and open a PR for it.
- **Slice 2 (wiring that engine into every `enforce_*_rate_limit`
  dependency): IMPLEMENTED but UNCOMMITTED** — real code sitting in the
  working tree on top of the Slice 1 commit, not part of any commit, not
  pushed, no PR. Every authentication endpoint's *actually committed*
  rate-limiting behavior is still the pre-existing in-process limiter,
  unchanged — Slice 2's Redis-first behavior is real and tested (see
  below) but **not active in the committed codebase** until it is itself
  reviewed and committed.
- The deterministic abuse-detection layer (ADR 0006 §11), Playwright, and
  Issue #3 are all still not started, in either committed or uncommitted
  form — **do not start any of them next.** The next action is Slice 1
  push/PR review; abuse detection is two steps away (after Slice 1
  merges, then after Slice 2 is reviewed and committed). See "Exact next
  recommended action" below for the full order.

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

Branch `issue-redis-rate-limiting`, **committed as `b1f1b00`, not yet
pushed.** Implemented the pieces of
ADR 0006 that don't require touching any endpoint, per that slice's
explicit scope (superseded by slice 2 below, which wires all of this in):

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
  trusted-proxy walk. **Not called from any endpoint yet** — see scope
  boundary above.
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

Branch `issue-redis-rate-limiting`, **uncommitted working-tree changes**,
on top of the Slice 1 commit (`b1f1b00`). **Not part of any commit — do
not treat this as active in the committed codebase:**

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
- **New test file `tests/test_rate_limit_wiring.py`** (5 tests, HTTP-level
  through real endpoints): a successful login creates the exact
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
- **Slice 1 is committed locally (`b1f1b00`) but not pushed, with no
  open PR. Slice 2 remains fully uncommitted, working-tree-only, not
  pushed, no open PR.**

## Later task: the deterministic abuse-detection layer (ADR 0006 §11/§12)

**Not the next action — do not start this yet.** Two steps come first:
(1) Slice 1 (`b1f1b00`) is reviewed, pushed, and merged; (2) Slice 2's
uncommitted endpoint wiring is itself reviewed and committed on top of
that. Only after both of those is this the last major piece of ADR 0006
that doesn't exist yet. Recorded here so the plan is visible, not as a
go-ahead. When it is time: **read [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
§11/§12 in full before writing any code.**

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

## Tests run (Redis implementation slices 1–2)

- Baseline (before slice 1, per that slice's explicit instruction):
  `uv run ruff check .` (pass), `uv run mypy .` (pass, 67 files),
  `uv run pytest -v` (**119/119 pass**, real Postgres).
- **Slice 1 (committed, `b1f1b00`): 170/170 pass** (119 existing + 51
  new), `mypy` clean (74 files). Independently re-validated in an
  isolated worktree built from the staged tree alone, immediately before
  the commit — not just claimed.
- Slice 2 (uncommitted working tree, on top of the Slice 1 commit):
  `uv run ruff check .` (pass), `uv run mypy .` (pass, **75 files**),
  `uv run pytest -v` (**175/175 pass** — 170 from Slice 1 + 5 new
  HTTP-level wiring tests, against real Postgres **and** real Redis).
  Re-ran the full suite 3 times to check for flakiness now that most auth
  tests exercise the real Redis path — none observed. **This 175/175
  figure describes the working tree, not the committed codebase** — the
  committed state (`b1f1b00`) is 170/170.
- New tests this slice (5, `test_rate_limit_wiring.py`): real-Redis key
  creation via a live `login` call (and HMAC-hash verification against
  independently-computed expected values); Tier A fallback for `login`
  via an unreachable-client dependency override; Tier B fail-open for
  `register` via the same technique; the "unconfigured (`None`) vs.
  unreachable" distinction for `register`; spoofed `X-Forwarded-For`
  ignored by default.
- Docker: full stack (`db`, `mailpit`, `redis`, `backend`) rebuilt and
  started, all four healthy. Live-verified (see "Completed work" above
  for the exact sequence): real key creation inspected via
  `redis-cli --scan`, login capped at capacity 5 across a real session,
  `/api/v1/health/ready` independent of Redis, Tier A/B behavior during
  a real stop/restart of the `redis` container, self-healing on
  recovery — all observed directly against running containers, not
  inferred from code.
- Frontend: untouched across both slices — not re-run (no frontend file
  changed).

## Exact next recommended action

Slice 1 and Slice 2 are being reviewed/landed as two separate units of
work (an explicit Git-separation decision, not the original one-PR plan
`AGENTS.md` §6 would default to) — follow this order, one step at a time:

1. **Review, then push, `issue-redis-rate-limiting` and open a PR for
   Slice 1 alone** (commit `b1f1b00` — foundation + token-bucket engine,
   not wired into any endpoint). This is the immediate next action.
2. **After Slice 1 is reviewed and merged:** review Slice 2's uncommitted
   working-tree changes (the endpoint wiring) on their own merits, then
   commit and push them (a separate commit/PR).
3. **Only after Slice 2 is committed and merged:** implement the
   deterministic abuse-detection layer (ADR §11/§12) — see "Later task"
   above. **Do not start this before Slice 1 and Slice 2 have both
   landed.**
4. **Then:** Playwright browser E2E for the authentication/
   password-recovery flows — not started.
5. **Then:** begin GitHub Issue #3 (Knowledge Ingestion) — not started.
