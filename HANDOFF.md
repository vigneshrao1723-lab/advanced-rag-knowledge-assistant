# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Everything through Redis Slices 1–3c and Playwright E2E is merged into
`main`.** In order: Redis Slice 1 (foundation + token-bucket engine) —
PR #11, squash commit `46ef03b`. Slice 2 (endpoint wiring) — PR #12,
squash commit `5391a78`. Slice 3a (abuse-state Redis primitives) —
PR #13, squash commit `026dcf3`. Slice 3b (decision engine + R1–R5
endpoint wiring, plus a `tests/conftest.py` test-isolation fix) — PR #14,
squash commit `42529e3`. Slice 3c (abuse-escalation audit emission) —
PR #15, squash commit `75dd466`. Browser E2E (Playwright) for
authentication/password-recovery — PR #16, squash commit `e1c4858`.
**`main`/`origin/main` are at `e1c4858`.** Nothing is pending review,
push, or merge for any of the above. Full per-item implementation detail
is preserved below under its own "Completed work" section — not repeated
here, per this file's own "don't append a history" instruction.

**GitHub Issue #3 (Knowledge Ingestion), Slice 3.1 (document data model +
migration) is now IMPLEMENTED, TESTED, COMMITTED, and PUSHED, on branch
`issue-3-slice-3-1-document-schema`, opened as **PR #17**, awaiting
review** — schema only (`documents`/`document_chunks` tables, migration
`0004`); no upload API, storage, extraction, chunking, background
processing, or embedding code. See "Completed work (Issue #3 — Slice 3.1:
document data model + migration)" below for full detail, and "Exact next
recommended action" at the end of this file for the branch/commit/PR
identifiers. **Do not start Slice 3.2 or any later Issue #3 slice without
an explicit go-ahead** — this slice's own scope stops at the schema.

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

## Completed work (Redis abuse layer — Slice 3a: primitives only)

**Uncommitted, working-tree-only.** Implements only the low-level,
fully-parameterized Redis/Lua primitives ADR 0006 §11/§12/§14 needs —
explicitly not the rule table, not `AbuseDecisionEngine`, not endpoint
wiring (all Slice 3b/3c, not started). No existing file was modified
except the two documentation files noted below; `register`/`refresh`/
`login`/`forgot-password`/`reset-password` are byte-for-byte unchanged
from Slice 2.

- **`app/core/abuse_keys.py`** (new): key builders for the `abuse:`
  namespace, mirroring `redis_keys.py`'s role for `rl:` —
  `failcount_key`, `distinct_ips_key`, `strict_throttle_key`, `block_key`.
- **`app/core/abuse_state.py`** (new): atomic Lua-scripted primitives,
  with no knowledge of R1–R5 as named rules (fully parameterized —
  thresholds/windows are Slice 3b's rule table, not hardcoded here):
  - `record_login_failure()` — **one Lua invocation** that atomically
    increments the IP failcount (R1) and account failcount (R2), adds the
    IP to the account's distinct-IP HyperLogLog (R3), and escalates each
    dimension independently once its own threshold is crossed. Multi-
    signal atomicity matches the same "check all → decide → write all"
    pattern Slice 1's `_TOKEN_BUCKET_LUA` already established.
  - `record_ip_failure()` — the shared primitive behind R4/R5
    (forgot-password/reset-password IP counters), parameterized by an
    `escalation: Literal["strict", "block"]` argument (passed to Lua as a
    **numeric** flag, not a string — a deliberate risk-reduction choice
    made because the script could not be execute-tested live this
    session; the codebase's existing Lua scripts never pass string
    ARGVs, so this also matches convention).
  - **Fixed-window counters**: TTL is set only when a counter is first
    created (`count == 1`), never refreshed by later increments — a
    deliberate simplicity choice, not a sliding window.
  - **STRICT_THROTTLE**: created via `HSETNX` (never resets an
    already-escalated/partially-consumed bucket) reusing the existing
    `RedisTokenBucketLimiter`/`DimensionSpec` bucket shape — no new
    bucket engine. Its TTL **does refresh** on every re-escalation, to
    keep the throttle alive while abuse continues.
  - **TEMPORARY_BLOCK**: created via `SETNX`, TTL **set once at creation
    and never refreshed** by a later crossing — this asymmetry with
    STRICT_THROTTLE is exactly what guarantees ADR §12's "never permanent
    or indefinite" requirement; there is no manual-unblock path, and a
    successful login must never remove it (verified — see next bullet).
  - `reset_account_state()` — the successful-login decay: deletes the
    account-scoped failcount (R2) and the distinct-IP HyperLogLog (R3)
    only. **Never touches R1 (IP failcount), block state, or strict-
    throttle state.** Concurrency semantics (a reset racing a concurrent
    failure) are "last write wins," documented in-code as a deliberate,
    bounded, self-healing, non-exploitable choice — **no generation/
    version counter was introduced**, matching this project's own prior
    analysis that one isn't needed (an attacker cannot trigger their own
    account's success without already having the correct credential).
  - `is_strict_throttle_active()` / `is_temporarily_blocked()` — plain
    `EXISTS` reads, unused by anything yet, provided for Slice 3b's
    future `check()`.
  - Every primitive raises `RedisUnavailableError` on any
    `redis.RedisError` — never swallows, never introduces a second
    fallback limiter (matches ADR §13's existing outage contract exactly;
    the abuse layer relies on the same fail-open/fallback policy Slice 2
    already implements for the base rate limiter).
- **`tests/test_abuse_state.py`** (new, 32 tests): failcount creation/
  increment/TTL/expiry; HLL creation/repeated-IP/distinct-IP counting/
  threshold boundary/expiry/reset-on-success; R2 reset vs. R1-not-reset;
  block creation/TTL/expiry/not-removed-by-success; strict-throttle
  not-created-by-ordinary-failures/created-only-after-escalation/correct
  capacity/does-not-reset-consumed-tokens-on-re-escalation/TTL/expiry;
  multi-signal atomicity; concurrent-failure-increment and concurrent-
  reset-vs-failure race tests (real `threading`, asserting only bounded,
  non-negative, valid final states — no mocks); cross-account isolation;
  shared-IP-multiple-accounts; one-account-multiple-IPs; Redis-
  unavailable (all 5 primitives); no raw email/secret ever stored in a
  Redis value; a bounded-TTL sweep across every key type. Uses small
  fast test thresholds (e.g. 3/1–2s), not the real R1–R5 production
  values — this slice tests the mechanism, not the rule table.
  - **`ruff`/`mypy` clean** on all three new files. Test collection on
    the host succeeds (`pytest --collect-only` → 215 tests: 183 existing +
    32 new).
  - **Real-Redis validated**: after the host shell's own path to the
    Dockerized Redis/Postgres published ports was confirmed broken (an
    environment fault, not a code defect — see "Tests run" below), the 32
    tests were copied into and run inside the already-running
    `compose-backend-1` container, over the Docker-internal `db`/`redis`
    hostnames, and **passed 3 consecutive times (32/32 each run)**. This
    is not the same as a clean host-side run of the current 215-test full
    suite, and not a production validation — see "Tests run" for the
    full method and caveats.
- **Documentation updated this slice**: ADR 0006 (§22's now-resolved
  open decisions moved into a new "Resolved during the abuse-layer
  design/readiness review" subsection — the full R1–R5 threshold/window
  table, the corrected 60-second token-bucket timing derivation replacing
  an earlier wrong "~2 minutes" estimate, the strict/block TTL-asymmetry
  rationale, and the decay policy; the "Implementation status" table's
  abuse-layer row split into 7 granular per-component rows, all
  Tested=No/Committed=No with an explicit Docker-unavailable note) and
  `PROJECT_STATE.md` (component-status rows updated). `docs/SECURITY.md`
  was reviewed and needs **no change** — it already states the abuse
  layer doesn't exist yet, which remains true since Slice 3a changes zero
  runtime behavior (unused primitives, no wiring).

**Slice 3a note (superseded by the entry above): Slice 3a has since been
committed and merged into `main` as squash commit `026dcf3` (PR #13).**

## Completed work (Redis abuse layer — Slice 3b: decision engine + endpoint wiring)

**Superseded by the current-task summary above: Slice 3b has since been
committed and merged into `main` as squash commit `42529e3` (PR #14),
including the `tests/conftest.py` test-isolation fix.** The record below
is kept as accurate history of that slice's own implementation/
validation, not as the current status.

Implements the deterministic
decision layer on top of Slice 3a's primitives and wires it into the
three operations R1–R5 actually target — `login`, `forgot-password`,
`reset-password`. `register`/`refresh` are untouched (no rule in R1–R5
targets them).

- **`app/core/abuse_decision.py`** (new): a module-level rule table
  (`_BLOCK_DIMENSIONS`/`_STRICT_DIMENSIONS` per operation — the data
  that makes `TEMPORARY_BLOCK` deterministically dominate
  `STRICT_THROTTLE`, since block dimensions are always resolved in full
  before any strict dimension is even inspected) plus a stateless
  `check()`/`record_*()` API:
  - `check(client, context) -> AbuseDecision` — pre-request, read-only
    (`EXISTS`/`TTL` only). Returns `temporary_blocked` (with
    `retry_after_seconds` sourced from the new `temporary_block_ttl_seconds()`
    primitive) and a list of already-escalated `strict_dimensions`
    (`DimensionSpec`s) for the caller to fold into its own
    `check_all()` — never a separate Redis round trip, which would
    reopen the partial-consumption race ADR 0006 §10 already closed once.
  - `record_login_failure()` / `record_login_success()` /
    `record_forgot_password_request()` / `record_reset_validation_failure()`
    — four explicitly-named functions, not one function overloaded with
    a `succeeded` flag that would sometimes mean "always true"
    (forgot-password has no real success/failure branch to key off —
    see ADR's enumeration-resistance design). Each returns an
    `AbuseRecordOutcome` (`rule_id`/`action`/`newly_escalated`/
    `operation`/`dimension`) with enough detail for a future Slice 3c to
    decide what, if anything, to audit.
  - Fails open unconditionally on `RedisUnavailableError` (logged,
    never re-raised) and is a no-op when `client` is `None` — simpler
    than the base limiter's operation-aware Tier A/B split, since the
    abuse layer is defense-in-depth on top of the base token bucket, not
    a replacement for it.
  - Never imports `app.core.audit` or touches PostgreSQL — audit
    emission stays Slice 3c's job.
- **`app/core/abuse_state.py`** (additive change only): one new
  primitive, `temporary_block_ttl_seconds()` — a plain `TTL` read,
  returning remaining seconds or `None`. Added because
  `is_temporarily_blocked()`'s existing boolean isn't enough to build an
  accurate `Retry-After`; its own signature/contract is unchanged.
- **`app/core/token_bucket_types.py`** (new — a deviation from the
  original file plan, explained below): `DimensionSpec`/
  `TokenBucketResult`, extracted out of `rate_limit.py`.
  `rate_limit.py` re-exports both names unchanged (`from
  app.core.rate_limit import DimensionSpec` still works everywhere it
  already did), so no other existing call site needed to change.
  **Why this file exists:** wiring `rate_limit.py` to call
  `abuse_decision.check()` created a real circular import
  (`rate_limit.py` → `abuse_decision.py` → `abuse_state.py` →
  `rate_limit.py`, since `abuse_state.py` already imported
  `DimensionSpec` from `rate_limit.py`) — confirmed by an actual
  `ImportError` at runtime, not just suspected. This was the minimal fix
  (move one dependency-free dataclass pair to a leaf module both sides
  can import from) rather than a broader refactor; verified afterward
  that the full app (`create_app()`) and a full `mypy .` (81 files)
  both pass cleanly.
- **`app/core/rate_limit.py`** (modified): `enforce_login_rate_limit`/
  `enforce_forgot_password_rate_limit`/`enforce_reset_password_rate_limit`
  each now call `abuse_decision.check()` first — an active
  `TEMPORARY_BLOCK` raises `429` immediately, before the base
  `check_all()` even runs; any active `STRICT_THROTTLE` dimension is
  appended to the *same* dimension list passed to `_check_or_fallback()`,
  so strict-bucket consumption stays atomic with the base bucket's own
  consumption in one Lua invocation. `enforce_register_rate_limit`/
  `enforce_refresh_rate_limit` are byte-for-byte unchanged.
- **`app/api/v1/auth.py`** (modified): `login`/`forgot-password`/
  `reset-password` gained post-outcome recording:
  - `login`: `auth_service.login()` is wrapped in `try/except
    HTTPException` — a caught exception calls `record_login_failure()`
    then re-raises; a normal return calls `record_login_success()`.
    Recording happens **only after the real outcome is known**, never
    in the pre-request dependency (this is the exact bug the stale ADR
    §6 diagram — now corrected — would have caused if implemented
    literally).
  - `forgot-password`: `record_forgot_password_request()` is called
    unconditionally, right after `password_reset_service.request_password_reset()`
    (which itself never raises).
  - `reset-password`: a caught `HTTPException` is inspected for
    `detail["code"]` — only `reset_token_invalid`/`_expired`/
    `_already_used` triggers `record_reset_validation_failure()`; a
    successful reset records nothing.
- **`tests/test_abuse_decision.py`** (new, 33 tests): rule-table shape,
  `AbuseContext` construction, per-rule threshold behavior (below/exact/
  already-active) for all of R1–R5, TTL expiry and the block's
  non-refreshing TTL, R1+R2/R2+R3/R1+R2+R3 simultaneous-escalation and
  precedence tests (confirming `TEMPORARY_BLOCK` always dominates,
  by construction of `check()`'s dimension ordering, not by chance),
  block-expiry-falls-through-to-strict, account/IP isolation,
  successful-login reset scoping (R2/R3 cleared, R1 and active
  escalations untouched), R4's unconditional recording, R5's
  failure-only recording, Redis-unavailable/unconfigured fail-open and
  no-op paths, concurrent-failure races (real `threading`, reusing
  Slice 3a's established pattern), strict-dimension-atomic-with-base-
  dimension (using `RedisTokenBucketLimiter.check_all()` directly to
  prove no partial consumption), and no raw email/secret leakage.
  - **Two test-design bugs found and fixed during this slice's own
    validation** (not defects in `abuse_decision.py`/`abuse_state.py`
    themselves): the original R1-isolation test reused the same account
    across all 10 calls, so R2 co-escalated and the test asserted the
    wrong `rule_id`; the original R2-isolation test used a fresh IP per
    call, which tripped R3's lower threshold (5) before R2's (10) ever
    fired. Both fixed by controlling which dimension varies per call so
    only the rule under test can possibly cross its threshold.
  - `ruff`/`mypy` clean. **33/33 passed, 3 consecutive runs**, plus the
    unaffected 32 from Slice 3a (**65/65 combined**), against real Redis
    + real PostgreSQL inside `compose-backend-1`.
- **Full pre-existing suite, run inside the same container, from a
  freshly flushed Redis, with `EMAIL_PROVIDER=console` overridden to
  isolate the already-known, already-documented Slice-3a-era artifact**:
  **238 passed, 2 failed** (240 collected). Both failures
  (`test_reset_token_does_not_affect_other_users`,
  `test_password_reset_does_not_retroactively_invalidate_an_already_issued_access_token`)
  were diagnosed precisely, not assumed: a direct diagnostic script
  showed the `forgot-password` call itself returning `429`, not a
  print-capture problem. Root cause: `tests/conftest.py`'s
  `_reset_rate_limiters` autouse fixture sweeps `rl:*` Redis keys
  between tests but **not** the new `abuse:*` keys this slice's wiring
  creates — so `abuse:failcount:forgot-password:ip:testclient` (every
  `TestClient` request shares the same fixed `"testclient"` peer
  address) accumulates across every test in the session that calls
  `forgot-password`, and once R4's threshold (10) is crossed, later
  `forgot-password` calls from the same fixed IP get `STRICT_THROTTLE`d
  for real. Confirmed reproducible from a genuinely clean Redis (not an
  artifact of repeated same-session reruns) by flushing Redis and
  running the full suite once, cleanly, twice (with and without the
  `EMAIL_PROVIDER` override) — both times, exactly these same 2 tests
  failed with the identical `429` root cause. `test_abuse_decision.py`/
  `test_abuse_state.py` were unaffected throughout (each has its own
  dedicated `abuse:*`-sweeping cleanup fixture, scoped to just those
  files).

**Test-isolation fix (same branch, follow-up commit `46a2860`):**
`tests/conftest.py`'s `_reset_rate_limiters` extended to also sweep
`abuse:*` between tests, mirroring the existing `rl:*` pattern-delete
loop exactly, under the same `RedisError` tolerance already in place —
one file, no production code touched, no test skipped/xfailed/reordered,
no sleeps added. Confirmed CI itself hit the identical root cause on PR
#14 before this fix (3/248 failed: the same 2 `test_password_reset.py`
tests plus `test_rate_limit_wiring.py::test_successful_forgot_password_creates_the_redis_ip_and_account_dimension_keys`,
which failed there with the same `429 == 200` signature — a different
specific test than locally, purely because CI's test-execution order
differs, not a different root cause). After the fix: the 3 previously-
failing tests pass individually and together; the complete **248-test
backend suite passed 248/248, 3 consecutive runs** (real Postgres + real
Redis, inside `compose-backend-1`, `EMAIL_PROVIDER=console` to match
CI's own environment — confirmed via `.github/workflows/ci.yml` that CI
never sets `EMAIL_PROVIDER` at all, so it was never affected by this
container's separate `EMAIL_PROVIDER=smtp` runtime artifact). No new
regression test was added — the existing suite (specifically the
forgot-password wiring test that was one of the 3 originally failing)
already directly demonstrates the fix, and adding another would have
been redundant. `ruff`/`mypy` clean (host and container, 81 source
files — the fixture change touches only a test file).
- **Documentation updated this slice**: ADR 0006 (§6's flow diagram
  corrected — the original placed `record(outcome)` inside the
  pre-request dependency, which is unreachable since outcomes aren't
  known until the endpoint body runs; the "Implementation status" table
  updated for Slice 3a's merge and Slice 3b's new components),
  `PROJECT_STATE.md`, this file. `docs/SECURITY.md` was reviewed and
  needs **no change**: it describes the *committed* (`main`) codebase's
  security posture, and Slice 3b is not committed — `main` genuinely
  still has zero reachable abuse escalation, so its "the deterministic
  abuse-detection layer does not exist yet" statement remains accurate.
  **This will need updating the moment Slice 3b actually merges** — done,
  see the Slice 3c entry below (`docs/SECURITY.md` was updated for both
  Slice 3b's live escalation and Slice 3c's audit emission in the same
  pass, once Slice 3b had actually merged).

## Completed work (Redis abuse layer — Slice 3c: audit emission + HTTP-level tests)

**Uncommitted, working-tree-only.** Adds abuse-escalation audit emission
on top of Slice 3b's now-merged decision engine — no production
abuse-decision code modified, only consumed.

- **`app/core/audit.py`** (additive): one new constant,
  `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` — no existing constant or
  the `record()` function's signature changed.
- **`app/api/v1/auth.py`** (modified): a new `_audit_abuse_escalation()`
  helper, called from `login`/`forgot-password`/`reset-password` right
  after each `record_login_failure()`/`record_forgot_password_request()`/
  `record_reset_validation_failure()` call:
  - Fires only when `outcome.newly_escalated` is `True` — never on an
    already-escalated repeat, never for an ordinary `ALLOW` (this
    function is only ever called with the result of a `record_*` call,
    itself only reached after a real outcome is known).
  - Event type: `AuditEvent.RATE_LIMITED` for `STRICT_THROTTLE`,
    `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` for `TEMPORARY_BLOCK`.
  - Metadata: `rule`/`operation`/`dimension` always; `account_hash`
    (already HMAC-hashed, never raw) when the dimension is
    account-scoped; `block_ttl_seconds` (600, from
    `abuse_state.TEMPORARY_BLOCK_TTL_SECONDS`) for blocks. Never a raw
    email, password, reset token, or refresh token.
  - `user_id` is always `None` — none of the three call sites have a
    resolved user at this point (a failed login never returns one;
    forgot-password/reset-password never expose one to this layer) —
    never invented.
  - `ip_address` is the same trusted-proxy-resolved `AbuseContext.ip`
    the abuse decision itself acted on, not the separate, unconditional
    `client_ip()` used elsewhere for session/authorization audit rows.
- **`tests/test_abuse_audit.py`** (new, 6 HTTP-level tests, real Redis +
  real PostgreSQL, no mocks): repeated login failures → R1
  `STRICT_THROTTLE` + exactly one `RATE_LIMITED` row + strict-bucket
  consumption proof (2 allowed, 3rd rejected) + no duplicate rows;
  account-scoped R2 through the endpoint + account isolation; 5 distinct
  IPs against one account → R3 `TEMPORARY_BLOCK` + exactly one
  `ABUSE_TEMPORARY_BLOCK_APPLIED` row with `block_ttl_seconds` + the
  account rejected outright afterward, before `auth_service` ever runs;
  R4 forgot-password strict-throttle with enumeration-resistant
  responses intact throughout; R5 reset-password validation failures →
  `TEMPORARY_BLOCK` + audit row + subsequent outright rejection;
  successful login resetting R2/R3 but not R1, with zero abuse-audit
  rows from an ordinary below-threshold sequence.
  - **Two test-design bugs found and fixed during this slice's own
    validation** (not production defects): (1) the initial approach
    tried to pre-fill the *base* `rl:*` token bucket with an abundant
    token count to reach abuse thresholds (10–15) faster than the base
    bucket's own small capacity (5–10) would otherwise allow — this
    doesn't work, because the Lua bucket script always clamps effective
    tokens at the dimension's configured `capacity` regardless of what's
    stored, so no amount of pre-written state lets more than `capacity`
    real requests through in one window. Fixed by pre-seeding the
    *abuse-layer's own* counters directly via the same production
    `record_*` functions the endpoint itself calls (real code, not a
    mock), reserving real HTTP calls for the actually-interesting final
    transition and its surrounding assertions. (2) One assertion assumed
    the shared, persistent `audit_logs` table would show zero
    `LOGIN_SUCCEEDED` rows — wrong, since real historical rows already
    existed from earlier manual verification sessions against the live
    Docker stack (confirmed by direct query: 5 rows, all
    `ip_address='172.18.0.1'`, dated 2026-09-14). Fixed by scoping the
    assertion to the test's own unique IP instead of a bare global count.
  - `ruff`/`mypy` clean. **6/6 passed, 3 consecutive runs**, alongside
    the complete **254-test backend suite passing 254/254, 3 consecutive
    runs** — all against real Redis and real PostgreSQL inside
    `compose-backend-1` (the host shell's own published-port path
    remained broken this session too, confirmed again before falling
    back to the established container-based validation approach).
- **Documentation updated this slice**: ADR 0006 (Implementation status
  table updated for Slice 3b's merge and the new audit-emission row),
  `docs/SECURITY.md` (the "Rate limiting" section's stale "abuse-
  detection layer does not exist yet" statement corrected now that
  Slice 3b has actually merged; the "Audit logging" section extended for
  the two new event types and their metadata/`user_id` conventions),
  `PROJECT_STATE.md`, this file.

## Completed work (Playwright E2E — authentication/password-recovery)

**This work has since been committed, pushed, opened as PR #16, and
merged into `main` as squash commit `e1c4858`, with CI green.** The
record below is kept as accurate history of the implementation/
validation itself, not as current status — see "Current task" above.

No Playwright infrastructure existed before this — `@playwright/test`
was not installed (only present transitively, unused, in
`frontend/package-lock.json`'s dependency graph); introduced fresh.

- **`frontend/playwright.config.ts`** (new): `baseURL` from
  `PLAYWRIGHT_BASE_URL` (default `http://localhost:3000`); Chromium only,
  for now; `trace`/`screenshot`/`video` captured `retain-on-failure`/
  `only-on-failure` for debugging without bloating every run.
  **`workers: 1`, `fullyParallel: false`, deliberately** — the backend's
  base rate limiter and the deterministic abuse layer (ADR 0006) both key
  partly by source IP, and every Playwright request in a run shares one
  peer address; parallel specs would risk a real, correctly-functioning
  `429` unrelated to what any individual test checks.
- **`frontend/e2e/fixtures/`**: `users.ts` (unique-email/password
  helpers, mirroring the backend pytest suite's own `_unique_email()`
  pattern); `mailpit.ts` (polls Mailpit's real REST API —
  `http://localhost:8025` — for the password-reset email by recipient
  and subject, extracts the reset link by regex; a genuine poll loop for
  real, variable SMTP-capture delivery latency, not a fixed sleep);
  `auth-helpers.ts` (`registerViaUi`/`loginViaUi`/`logoutViaUi`/
  `readBrowserStorage`, all driving the real UI, never a direct API
  shortcut for the flows actually under test).
- **`frontend/e2e/app-availability.spec.ts`** (3 tests): the home page
  loads with no unexpected console errors, an anonymous visitor sees
  the log in/register entry points, the backend readiness endpoint the
  application itself depends on is reachable and reports `ready`.
- **`frontend/e2e/auth.spec.ts`** (9 tests, 2 `describe.serial` blocks
  each driving one shared `page` created in `beforeAll` — `.serial()`
  alone does not share a page/context between tests, so each block
  creates and closes its own explicitly): short-password client-side
  validation (no request sent); a full register → verify no token in
  `localStorage`/`sessionStorage` → reload persists the session → logout
  ends it → an unauthenticated visitor is redirected away from a
  protected route journey; a separate login → storage-security check →
  **CSRF negative case** (a state-changing `POST` with the session's real
  cookies but no `X-CSRF-Token` header — the exact shape the
  double-submit pattern exists to reject — gets a real `403` from the
  real middleware) → **CSRF positive case** (the same mutation through
  the real UI, which does attach the header, succeeds) journey.
- **`frontend/e2e/password-recovery.spec.ts`** (7 tests, one
  `describe.serial` block): forgot-password for an existing account and
  for a nonexistent one return the identical generic message
  (enumeration resistance); the real email is read back through Mailpit,
  the reset link is followed, the new password is accepted, and no
  token/link is left in browser storage; the old password stops
  authenticating (with the backend's own generic
  "Incorrect email or password." message — itself further
  enumeration-resistance evidence); the new password authenticates; and
  — the one test needing genuinely persistent pre-reset session state —
  the pre-reset session's **refresh capability** (not its short-lived
  access token, which is documented, intentional, not-retroactively-
  invalidated behavior — ADR 0003's hot-path trade-off, already proven
  by the backend's own
  `test_password_reset_does_not_retroactively_invalidate_an_already_issued_access_token`)
  is confirmed revoked (`401`) by a direct, CSRF-header-attached
  `POST /api/v1/auth/refresh` using that session's own cookies.
- **Genuine findings from this validation, all fixed as test-code
  corrections — no application/production code was changed for any of
  them:**
  1. A locator using `getByText(workspaceName)` hit a real strict-mode
     ambiguity — the created workspace's name legitimately renders in
     three places at once (the workspace switcher, the list, and its own
     detail heading), which is correct application behavior, not a bug.
     Fixed by scoping the assertion to the main content region.
  2. A direct `POST /api/v1/auth/refresh` call meant to prove session
     revocation returned `403`, not the expected `401` — because, like
     `/api/v1/workspaces`, `/refresh` is itself a state-changing,
     CSRF-protected endpoint, and the raw request (deliberately, in the
     *other*, adjacent CSRF-negative test) didn't attach the header.
     Fixed by reading the session's own `csrf_token` cookie and attaching
     it, matching what `lib/api-client.ts` already does for every real
     request.
  3. `page.on("console", ...)` with `type() === "error"` also captures
     Chromium's own "Failed to load resource: 401" log line for the
     anonymous-visitor auth-bootstrap check
     (`GET /api/v1/users/me` on mount, `lib/auth-context.tsx`) —
     expected, already-caught application behavior, not a fatal error.
     Fixed by filtering that specific, well-understood log pattern while
     still catching any other console error and any genuine uncaught
     exception (`pageerror`, a separate listener, unchanged).
- **`ruff`/`npx eslint e2e/ playwright.config.ts`/`npx tsc --noEmit`**
  all clean. **19/19 passed, 3 consecutive clean runs.** The first
  attempt at 3 back-to-back runs (no gap) hit a real, correctly-working
  `429` from the backend's own `register` rate limiter (capacity 5/60s
  per source IP) — not flakiness, a deterministic consequence of firing
  ~9 registrations inside one 60-second window across 3 runs. Re-run
  cleanly 3 times with the real bucket's own TTL-based refill (polled via
  `redis-cli TTL`, not a blind sleep) between runs. **This means: do not
  fire the full E2E suite repeatedly back-to-back with no gap** — a
  single CI job run is unaffected (one run, once), but local repeat runs
  for flakiness-hunting need the same spacing.
- Existing frontend suite (**48 vitest tests**) and `npm run lint`
  confirmed unaffected/still clean.
- **`.github/workflows/ci.yml`** gained a new `e2e` job (after
  `backend`/`frontend` pass): real Postgres/Redis/Mailpit service
  containers, the real backend (`uvicorn`) and frontend (`next dev`)
  started as background processes with a deterministic readiness-poll
  wait (not a fixed sleep), then `npm run test:e2e`; uploads the HTML
  report (and, on failure, the server logs — no secrets) as build
  artifacts. **Not yet run on GitHub Actions as of this entry** — this
  session's own validation was local, against the already-running
  `docker compose` stack; the CI job's exact behavior will be confirmed
  once the PR is actually opened and CI runs for real, not claimed here
  in advance.
- **This is not a production validation.**

## Completed work (Issue #3 — Slice 3.1: document data model + migration)

**Implemented, tested, committed, and pushed; PR open, not yet
merged.** Schema only — per this slice's explicit scope, no upload API,
storage abstraction, text extraction, chunking, background processing,
or embedding code was added.

- **`backend/app/models/document.py`** (new): `Document` model —
  `documents` table. `workspace_id` (`ON DELETE CASCADE`, indexed);
  `uploaded_by` nullable, `ON DELETE SET NULL` (matches `AuditLog.user_id`'s
  precedent — a document should outlive the account that uploaded it,
  not disappear when the account is removed); `filename`/`mime_type`/
  `size_bytes`/`checksum_sha256`/`storage_key` (server-generated, unique
  — never the user-supplied filename, per `docs/SECURITY.md` "Upload &
  document safety"); `status` as a new `DocumentStatus` native Postgres
  enum (`document_status`) matching the documented lifecycle exactly
  (`docs/REQUIREMENTS.md`/`docs/RAG_DESIGN.md`): `UPLOADED → PROCESSING →
  PARSED → CLEANED → CHUNKED → EMBEDDED → INDEXED → READY / FAILED`. A
  native enum was chosen over a plain string (unlike `audit_logs.event_type`,
  which is deliberately open-ended) because this lifecycle is a fixed,
  closed set defined once by the project specification — following
  `WorkspaceMember.role`'s (`workspace_role`) convention instead.
  `failure_reason`/`page_count`/`processing_started_at`/
  `processing_completed_at` all nullable. `UNIQUE(storage_key)` and
  `UNIQUE(workspace_id, checksum_sha256)` (duplicate-upload detection,
  scoped per workspace, not global — the same checksum in two different
  workspaces is allowed).
- **`backend/app/models/document_chunk.py`** (new): `DocumentChunk`
  model — `document_chunks` table. `document_id` (`ON DELETE CASCADE`,
  indexed); `workspace_id` deliberately denormalized (also indexed) —
  every future workspace-scoped retrieval/security query needs to filter
  chunks by workspace without an extra join; `chunk_index`/`page`/
  `section`/`content`. `UNIQUE(document_id, chunk_index)`, scoped per
  document, not global. **No embedding column** — see the next bullet.
- **Deliberately no pgvector column yet**: choosing `VECTOR(n)` now would
  lock the schema to an embedding model/dimension before the
  `EmbeddingProvider` abstraction is designed in a later slice; adding it
  is planned as a small additive migration once that choice is actually
  made, not a breaking change to this one.
- **`backend/alembic/versions/0004_add_documents_and_document_chunks.py`**
  (new): reversible migration for both tables, following `0002`/`0003`'s
  style (the `document_status` enum type is created by `create_table`'s
  column type hook, matching how `0002` creates `workspace_role` — no
  separate `.create()` call). `downgrade()` drops both tables' indexes,
  both tables, then the enum type.
- **`backend/app/models/__init__.py`** (modified): registers `Document`/
  `DocumentChunk`/`DocumentStatus` on `Base.metadata` so Alembic
  autogenerate and the test suite's session-scoped migration fixture see
  them, matching every prior model's registration pattern.
- **`backend/tests/test_document_schema.py`** (new, 19 tests, real
  Postgres via `tests/conftest.py`'s `db_session` fixture, no mocks):
  table existence; a document referencing an existing workspace/uploader;
  `uploaded_by` nullability; invalid workspace FK rejected
  (`IntegrityError`); the workspace+checksum unique constraint, and that
  it's correctly *not* global (same checksum across two different
  workspaces is allowed); the storage-key unique constraint; a chunk
  referencing its document/workspace; invalid document FK on a chunk
  rejected; the document+chunk_index unique constraint, and that it's
  correctly *not* global (same `chunk_index` across two different
  documents is allowed); cascade delete from `documents` to
  `document_chunks`; nullable-metadata-field defaults; `DocumentStatus`
  defaulting to `UPLOADED` and persisting a mutation; database-assigned
  timestamps on both tables.
  - **One genuine test-design bug found and fixed during this slice's
    own validation** (not a schema/migration defect): the first version
    of the cascade-delete test called `db_session.get(DocumentChunk,
    chunk_id)` right after deleting the parent `document` and flushing —
    `ON DELETE CASCADE` ran correctly in Postgres, but the SQLAlchemy
    session's identity map still held the pre-delete `chunk` object
    (the ORM was never told about the DB-level cascade), so `.get()`
    returned the stale cached instance instead of re-querying and
    getting `None`. Fixed by calling `db_session.expire_all()` before
    the assertion.
  - `ruff`/`mypy` clean (86 source files, only 2 mypy findings surfaced
    along the way, both fixed: `sa.inspect(db_session.bind)` typed as
    `Any | None` — switched to `sa.inspect(engine)`, the same real bind
    `conftest.py` itself uses).
  - **Real-Postgres validated**: **19/19 new tests passing**; the
    complete backend suite **273/273 passing** (254 pre-existing + 19
    new), **3 consecutive runs**, no flakiness, no regression in any
    existing auth/workspace/rate-limit/abuse-protection test.
  - **Migration `0004` explicitly verified reversible**, not just
    assumed from the code: `alembic downgrade 0003` removes both tables
    and the `document_status` enum (confirmed via `sqlalchemy.inspect`
    against the real database); `alembic upgrade head` re-creates both
    tables with the correct column set; the full suite re-run clean
    afterward.
  - This session hit a genuine environment interruption mid-task:
    Docker Desktop's WSL integration dropped (the `docker` CLI briefly
    reported "command could not be found in this WSL 2 distro" after
    working moments earlier) and had to be restored on the Windows side
    before any of the above could run — not a code or schema defect;
    documented here per this project's established practice of recording
    genuine Docker/WSL environment faults rather than silently working
    around or omitting them.
- **Docs updated this slice**: `docs/DATA_MODEL.md` (`documents`/
  `document_chunks` moved PROPOSED → IMPLEMENTED, schema only; the chunk
  metadata list annotated field-by-field; the embedding-column decision
  documented explicitly), `PROJECT_STATE.md`, `CHANGELOG.md`, this file.
  Also reconciled in the same pass, per explicit instruction: `PROJECT_STATE.md`/
  `HANDOFF.md`/`CHANGELOG.md` still described the already-merged
  Playwright E2E work (PR #16, `e1c4858`) as uncommitted — corrected
  throughout all three files (see "Completed work (Playwright E2E...)"
  above for its own updated status note, and the `CHANGELOG.md` entry
  moved from "Unreleased — working tree" to "Unreleased — committed"
  with the real commit hash).

## Explicitly NOT done (do not assume otherwise)

- **Slice 3c is merged** (`75dd466`, PR #15) — `AuditEvent.RATE_LIMITED`
  and `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` are both emitted,
  exactly once per escalation, from `login`/`forgot-password`/
  `reset-password`. This remains deterministic, rule-based logic
  throughout — never call it "AI" or claim ML/statistical evaluation
  unless an actual evaluated model backs that claim, per the ADR's
  explicit non-goal.
- **Playwright E2E is merged** (`e1c4858`, PR #16) — see "Completed work
  (Playwright E2E — authentication/password-recovery)" above. Covers
  only the authentication/password-recovery surface; no document/chat/
  search UI exists yet for E2E coverage to extend to.
- **Issue #3 Slice 3.1 (document schema) is implemented, tested,
  committed, and pushed — PR #17, not yet merged.** No upload
  API, storage, extraction, chunking, background processing, or
  embedding code exists. No document-access/ingestion audit events exist
  yet either — `AuditEvent` still only covers auth/workspace/rate-limit/
  abuse-escalation events; those land with a later Issue #3 slice (the
  upload/delete API).
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
- **Issue #3, Slices 3.2 onward (storage/upload/extraction/chunking/
  background processing/embeddings)** — not started.
- **Later RAG retrieval/generation features (Issue #4 onward)** — not
  started.
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

## Next major task: GitHub Issue #3 (Knowledge Ingestion), Slice 3.2

**ADR 0006's deterministic abuse-protection layer is functionally
complete end-to-end and fully merged (Slices 1–3c).** Nothing further is
planned under it unless a future decision proposes one (e.g. a
`Retry-After` header, `Forwarded` header support — see "Known
limitations" in the Slice 3c report above). Browser E2E coverage for the
authentication/password-recovery flows is implemented, validated, and
merged (PR #16, `e1c4858`).

**GitHub Issue #3 (Knowledge Ingestion) has started: Slice 3.1 (document
data model + migration) is implemented, tested, committed, and pushed —
PR #17, not yet merged.** Per that slice's own explicit scope,
it stops at the schema; no storage, upload API, extraction, chunking,
background processing, or embedding code exists.

**Before anything else starts**: get the Slice 3.1 PR reviewed and
merged, per normal workflow — don't start Slice 3.2 on top of an
unmerged prior slice.

With an explicit go-ahead, the next work in this repository's own stated
order (`PROJECT_STATE.md` "Immediate priorities") is:

1. **GitHub Issue #3, Slice 3.2** — not started; not yet scoped in this
   file. Do not assume its content without checking the Issue #3
   implementation plan/architecture notes first.

## Blockers

None currently. Docker Compose, the local Postgres container, Mailpit, a
local Redis, and `gh` CLI access are all confirmed working in this
environment. **A transient one occurred and resolved during this
session**: Docker Desktop's WSL integration dropped mid-task (the
`docker` CLI briefly reported "command could not be found in this WSL 2
distro" after working moments earlier) — required restoring the
integration on the Windows side before real-database validation could
run; not a code or environment-configuration defect on the repository
side.

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
- **Slice 3a (this checkpoint, uncommitted): `uv run ruff check .`**
  (pass, 78 files) and **`uv run mypy .`** (pass, "Success: no issues
  found in 78 source files") both clean, covering all three new files.
  **`uv run pytest --collect-only -q`** succeeded: **215 tests collected**
  (183 existing + 32 new) — this confirms imports/wiring are structurally
  correct, it is **not** a passing-test count. Actually running
  `uv run pytest tests/test_abuse_state.py -q` produced **32 errors**,
  every one a `sqlalchemy.exc` connection failure from the shared
  session-scoped `_migrated_database` autouse fixture (it requires a real
  Postgres for an Alembic migration, gating every test file including the
  Redis-only ones). Confirmed this is purely environmental, not a code
  defect: `docker compose ... up -d db redis` failed with "docker: command
  not found"; `/mnt/wsl/` contains only `resolv.conf` (no
  `docker-desktop` integration socket); direct TCP connection attempts to
  both `127.0.0.1:6379` and `127.0.0.1:5432` returned "Connection
  refused." Per explicit prior instruction, no Docker-level workaround
  (installing Docker Engine in WSL, editing Docker config) was attempted.
  **This particular attempt never got the 32 new tests executed against a
  real Redis** — superseded by the real-Redis validation recorded
  immediately below, from a later checkpoint in this same slice.

- **Slice 3a real-Redis validation (later checkpoint, still uncommitted):**
  once Docker Desktop/WSL integration came back, the *host shell's own*
  path to the running containers' published ports (`127.0.0.1:5432`,
  `127.0.0.1:6379`) was tested and found broken — TCP handshake succeeds,
  but the protocol-level read is reset immediately (`psycopg.OperationalError:
  server closed the connection unexpectedly`; `redis.ConnectionError:
  Connection reset by peer`) — confirmed as an environment/networking
  fault (not Postgres/Redis/code) via `/api/v1/health/ready` and
  `redis-cli ping` both succeeding from **inside** the Docker network, and
  via a previously-passing, unrelated Redis test file
  (`test_redis_rate_limiter.py`) failing identically. Worked around by
  running the tests **inside the already-running `compose-backend-1`
  container** instead, over its internal `db`/`redis` hostnames (the same
  values `docker-compose.yml` already sets as that container's own
  `DATABASE_URL`/`REDIS_URL` — no override needed). Since that container's
  image predates the uncommitted Slice 3a files (no bind mount), the three
  new files were `docker cp`'d into the container's writable layer for the
  duration of the validation, then removed afterward — no image rebuild,
  no compose/file change, no host repo change.
  - `uv run pytest tests/test_abuse_state.py -v` **32 passed**, 3
    consecutive times (5.6–5.8s each run, no flakiness).
  - Live Redis inspection (calling `record_login_failure`/
    `record_ip_failure` directly, before any cleanup fixture ran)
    confirmed real `abuse:*` keys of every expected type/TTL
    (`abuse:failcount:*` strings TTL 60s, `abuse:distinct_ips:acct:*`
    string/HLL TTL 60s with correct `PFCOUNT`, `abuse:strict:*` hashes TTL
    1200s, `abuse:block:*` string flags TTL 600s) — every key observed had
    a finite, positive TTL, and no raw email substring appeared in any key
    name or value (scanned directly, not assumed).
  - `ruff check .` / `mypy .` also re-run inside the container: both
    clean, matching the host results.
  - **This container's image was itself stale relative to `main` HEAD**
    (missing exactly the 8 tests Slice 2's review-fix pass added to
    `test_rate_limit_wiring.py` — confirmed by diffing collected test IDs
    against the host's 215) — so the full-suite run inside that container
    collected 207, not 215. That run initially showed 5 failures, all in
    `test_password_reset.py`, root-caused to the container's
    `EMAIL_PROVIDER=smtp` app-runtime setting (for manual Mailpit testing)
    versus the test suite's implicit expectation of `EMAIL_PROVIDER=console`
    (`conftest.py` doesn't default this one, unlike `DATABASE_URL`/
    `REDIS_URL`/`SECRET_KEY`) — confirmed via a one-off invocation-level
    override (`EMAIL_PROVIDER=console`, no file changed): 207/207 passed.
    **Neither 207 number should be read as "the current 215-test suite
    passed"** — that still requires either a fixed host-to-container
    network path or a freshly rebuilt container image, neither done this
    checkpoint.
  - **Net result: the 32 Slice 3a tests are real-Redis validated.** Slice
    3a has since committed/merged (`026dcf3`, PR #13).
- **Slice 3b (this checkpoint, uncommitted): `uv run ruff check .`**
  (pass, 81 files) and **`uv run mypy .`** (pass, 81 source files) both
  clean, host and container. **`tests/test_abuse_decision.py` (33 tests)
  plus the unaffected `tests/test_abuse_state.py` (32 tests) — 65/65
  passed, 3 consecutive runs**, inside `compose-backend-1` over
  Docker-internal hostnames (the host shell's own published-port path
  was tested again this session and remained broken, same symptom as
  before — TCP handshake succeeds, protocol read reset). Two test-design
  bugs (not implementation bugs) were found and fixed during this
  validation — see "Completed work (Redis abuse layer — Slice 3b)" for
  exactly what and why.
  - **Circular-import fix verified**: `from app.main import create_app;
    create_app()` succeeds; `mypy .` passes across all 81 files
    (including the explicit-reexport fix `DimensionSpec as DimensionSpec`
    needed for `no_implicit_reexport` compliance after the
    `token_bucket_types.py` extraction).
- **Test-isolation fix (commit `46a2860`, same branch)**: full
  pre-existing suite, run inside the container from a freshly flushed
  Redis, `EMAIL_PROVIDER=console` overridden to match CI's own
  environment (confirmed via `.github/workflows/ci.yml` that CI never
  sets `EMAIL_PROVIDER`) — before the fix, 238 passed/2 failed locally
  (240 collected); CI itself independently hit 245 passed/3 failed on
  PR #14 (the same root cause, landing on one extra test due to a
  different execution order). After the fix: **the complete 248-test
  suite (215 pre-abuse-layer + 32 Slice 3a + 33 Slice 3b — `conftest.py`
  changes don't add tests, they just fix isolation) passed 248/248, 3
  consecutive runs**, real Postgres + real Redis. `ruff check .`/`mypy .`
  both clean after the fix too (81 source files — the fixture change is
  test-only). **Slice 3b subsequently merged into `main` as `42529e3`
  (PR #14) with CI green (3/3 checks).**
- **Slice 3c (this checkpoint, uncommitted): `uv run ruff check .`**
  (pass, 82 files) and **`uv run mypy .`** (pass, 82 source files) both
  clean, host and container. **`tests/test_abuse_audit.py` (6 new
  HTTP-level tests) — 6/6 passed, 3 consecutive runs**, plus every
  related focused suite (`test_abuse_state.py`, `test_abuse_decision.py`,
  `test_auth.py`, `test_rate_limit_wiring.py`, `test_redis_rate_limiter.py`,
  `test_password_reset.py` — 138/138 combined) and the **complete
  254-test backend suite passing 254/254, 3 consecutive runs**, all
  against real Redis + real PostgreSQL inside `compose-backend-1` (the
  host shell's own published-port path was tested again this session and
  remained broken, same symptom as every prior session). Two test-design
  bugs (not implementation bugs) were found and fixed during this
  validation — see "Completed work (Redis abuse layer — Slice 3c)" for
  exactly what and why. **Slice 3c subsequently merged into `main` as
  `75dd466` (PR #15) with CI green (3/3 checks).**
- **Playwright E2E (this checkpoint, uncommitted): `npx eslint e2e/
  playwright.config.ts`** and **`npx tsc --noEmit -p .`** both clean.
  **19 tests across 3 spec files (`app-availability.spec.ts`,
  `auth.spec.ts`, `password-recovery.spec.ts`) — 19/19 passed, 3
  consecutive clean runs**, against the real frontend/backend/
  PostgreSQL/Redis/Mailpit stack (already-running `docker compose`
  services this session; host-shell HTTP connectivity to the published
  `3000`/`8000`/`8025` ports was tested and confirmed working this
  session — unlike the raw Postgres/Redis wire-protocol issue seen in
  earlier sessions, plain HTTP was reachable here). An initial attempt
  at 3 back-to-back runs with no gap hit a real, correctly-working `429`
  from the backend's own `register` rate limiter (not flakiness — see
  "Completed work (Playwright E2E...)" for the exact mechanism and fix).
  Existing **48 vitest tests** and `npm run lint` confirmed unaffected.
  **Since merged into `main` as squash commit `e1c4858` via PR #16.**
- **Issue #3, Slice 3.1 (document schema): `uv run ruff check .`** (pass)
  and **`uv run mypy .`** (pass, 86 source files — 2 findings surfaced
  and fixed along the way: `sa.inspect(db_session.bind)` typed
  `Any | None`, switched to `sa.inspect(engine)`). **19 new tests
  (`tests/test_document_schema.py`) — 19/19 passed** (one test-design bug
  found and fixed during validation, not a schema defect: a
  cascade-delete assertion read a stale ORM identity-map object after a
  DB-level `ON DELETE CASCADE`, before `db_session.expire_all()` was
  added — see "Completed work (Issue #3 — Slice 3.1...)" above for the
  full explanation). **Complete backend suite: 273/273 passing** (254
  pre-existing + 19 new), **3 consecutive runs**, real Postgres + real
  Redis, no regression in any existing auth/workspace/rate-limit/abuse
  test. **Migration `0004` explicitly verified reversible**: `alembic
  downgrade 0003` (both tables + the `document_status` enum removed,
  confirmed via `sqlalchemy.inspect`) then `alembic upgrade head` (both
  tables recreated with the correct columns), followed by a clean full
  suite re-run. This session hit a genuine, resolved environment
  interruption partway through (Docker Desktop's WSL integration
  dropped, then was restored on the Windows side) — documented in
  "Blockers" above; not a code defect. Schema/model/migration/tests
  committed as `36fe8b0`; documentation reconciliation as a second,
  separate commit — pushed on branch `issue-3-slice-3-1-document-schema`
  (cut from `e1c4858`), opened as **PR #17**.

## Exact next recommended action

Redis Slices 1/2/3a/3b/3c and Playwright E2E are all merged into `main`
(`46ef03b` PR #11, `5391a78` PR #12, `026dcf3` PR #13, `42529e3` PR #14,
`75dd466` PR #15, `e1c4858` PR #16) — nothing pending for any of them.
**GitHub Issue #3, Slice 3.1 (document data model + migration) is
implemented, tested, committed (`36fe8b0` + a docs commit), pushed, and
opened as PR #17** on branch `issue-3-slice-3-1-document-schema` (cut
from `e1c4858`) — see "Completed work (Issue #3 — Slice 3.1...)" and
"Tests run" above. The next work, in order:

1. **Get PR #17 reviewed, confirm CI is green, and merge it** — this
   slice's own real-Postgres validation (schema tests, full suite,
   migration reversibility) is already done locally; what's left is
   ordinary review plus confirming GitHub Actions CI passes on the PR
   itself. Do not merge it without review.
2. **Once merged, with an explicit go-ahead:** scope and implement
   GitHub Issue #3, Slice 3.2 — not yet defined in this file; check the
   Issue #3 implementation plan/architecture notes first rather than
   assuming its content.
