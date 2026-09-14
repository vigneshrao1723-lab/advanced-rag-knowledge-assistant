# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**GitHub Issue #2 — Authentication & Workspaces is complete and merged.**
Issue #1 (Application Foundation) is merged to `main` (PR #9). Issue #2
was implemented on branch `issue-2-authentication-workspaces` (checkpoint
commit `864d783`), opened as **PR #10**, verified green on GitHub Actions
(3/3 checks), and **merged into `main` as commit `ec4225d`** — a
squash/rebase merge (single parent), with its tree content verified
byte-identical to `864d783`. `main` is at `ec4225d`, `origin/main` matches
it, and the working tree is clean. The old feature branch still exists
(locally and on `origin`, not deleted) but has no content not already in
`main`.

**Nothing is currently in flight.** The next task — Redis distributed rate
limiting + a deterministic abuse-detection layer — is now **architecturally
designed** ([ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)),
but **implementation has not started**: no Redis dependency, service, or
application code exists yet, and no tests exist. See "Next major task"
below for a summary and a pointer to the ADR for full detail. Do not start
implementing it, Playwright, or Issue #3 without an explicit go-ahead.

Issue #2 covered: registration/login/logout/refresh with PostgreSQL-backed
sessions, HttpOnly cookie + CSRF browser authentication (superseding the
original bearer-token-in-body design), workspace CRUD/membership/RBAC,
password recovery (backend and frontend), audit logging, and the security
documentation/ADRs for all of it.

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

## Explicitly NOT done (do not assume otherwise)

- **Redis distributed rate limiting implementation** — not started. The
  architecture is designed (ADR 0006, above); no Redis dependency,
  service, or code exists anywhere in this repository.
- **Deterministic abuse/risk layer implementation** — not started. The
  rule model is designed (ADR 0006 §11); no code exists. (When you build
  this: it must remain deterministic, rule-based logic — never call it
  "AI" or claim ML/statistical evaluation unless an actual evaluated
  model backs that claim, per the ADR's explicit non-goal.)
- **Concurrency/race-condition testing for Redis** — not applicable yet;
  there is no Redis to test. ADR 0006 §17 designs what these tests should
  cover once implementation exists.
- **Playwright browser E2E** — not started. No config, no test files, no
  dependency. The live-Docker verification done for this checkpoint
  (curl/Python against running containers, including reading Mailpit's
  REST API directly) is real integration verification but is **not** a
  substitute for actual browser automation — say so explicitly if asked,
  don't imply Playwright coverage exists.
- **Issue #3 (document ingestion)** — not started.
- **Later RAG retrieval/generation features** — not started.

## Next major task: implement Redis rate limiting + deterministic abuse protection

**The design is done — [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
is the canonical source; read it in full before writing any code.** This
section is a summary and pointer, not a substitute for it. Implementation
is the next thing to build, has not started, and is a separate unit of
work from both Issue #2 (merged) and the design task that produced the
ADR.

Key points from the ADR (see it for the full reasoning and the "Open
decisions" section listing what's intentionally left for implementation
time):

- **Evolve `backend/app/core/rate_limit.py`, don't blindly replace it.**
  The existing `FixedWindowRateLimiter` becomes the documented failure-mode
  fallback for security-sensitive endpoints (ADR §13), not dead code.
  Understand why each existing limit exists and what test currently
  asserts it (`tests/test_auth.py`, `tests/test_password_reset.py`,
  `tests/test_rate_limit.py`) before changing anything underneath.
- **PostgreSQL remains the authoritative durable datastore** (ADR 0002).
  Redis holds only ephemeral rate-limit/abuse state (ADR 0006 §7) — never
  a second source of truth for anything that must survive a restart or be
  queried historically (that's still Postgres + `audit_logs`).
- **Algorithm:** token bucket via a single atomic Lua script **per
  operation, over all of that operation's dimension keys together** — not
  one script per key (that was this ADR's own first draft, and was
  wrong — see the atomicity correction above) and not a naive
  `GET → calculate → SET` (ADR §8, §10).
- **Redis failure is operation-aware, not a single global policy**:
  security-sensitive endpoints fall back to the in-process limiter;
  `register` fails open; block-checks specifically fail open even within
  the otherwise-conservative security-sensitive tier (ADR §13 explains
  why for each case).
- **No unbounded attacker queues** — every Redis key is TTL-bound; nothing
  is queued, only allowed/throttled/blocked (ADR §8, §10, §12).
- **Abuse detection is a deterministic rule table, not a score, not ML**
  (ADR §11) — implement it that way even if a numeric score looks
  tempting; the ADR explains why it was rejected.
- Files/areas to inspect first: `backend/app/core/rate_limit.py` (current
  mechanism), `backend/tests/test_rate_limit.py` and every
  `enforce_*_rate_limit` call site (`app/api/v1/auth.py`), `app/core/audit.py`
  (the already-defined-but-unused `AuditEvent.RATE_LIMITED` the ADR
  reuses), `docs/SECURITY.md` "Rate limiting approach" (needs updating
  once implementation lands — not yet, since nothing is implemented),
  `infra/compose/docker-compose.yml` (where a `redis` service would be
  added, following the same healthcheck-gated pattern already used for
  `mailpit`).

## Blockers

None. Docker Compose, the local Postgres container, Mailpit, and `gh` CLI
access are all confirmed working in this environment.

## Tests run (Issue #2, verified locally and confirmed again by CI on PR #10)

- GitHub Actions on PR #10: **3/3 checks passed** (backend
  lint/typecheck/tests; frontend lint/typecheck/tests/build; Docker build
  check) — confirmed before merge.
- Backend: `uv run ruff check .` (pass), `uv run mypy .` (pass, 67 files),
  `uv run pytest -v` (**119/119 pass**, against real Postgres).
- Frontend: `npm run lint` (pass), `npm run typecheck` (pass), `npm run
  test` (**48/48 pass**), `npm run build` (pass — `/forgot-password` and
  `/reset-password` both build as static pages).
- Docker: rebuilt backend + frontend images; full stack (db, mailpit,
  backend, frontend) started healthy.
- Live end-to-end password-recovery flow against the running containers:
  registered a test user → cleared Mailpit → called `forgot-password` →
  Mailpit received exactly 1 email to the correct address with a correct
  `http://localhost:3000/reset-password?token=...` link → extracted the
  real token from Mailpit's REST API → confirmed 0 occurrences of that
  raw token anywhere in backend container logs → reset without CSRF → 403
  → reset with correct CSRF → 204 → old password → 401 → new password →
  200 → the refresh token captured *before* the reset → 401 on replay
  (session invalidated). Also re-verified general cookie/CSRF/CORS
  behavior (login/register cookie attributes, CORS preflight
  allow/deny-by-origin, CORS headers present on CSRF/auth rejections)
  still intact after the frontend changes.
- Stack shut down cleanly after each verification pass.

## Exact next recommended action

Issue #2 is merged — there is nothing left to push, review, or merge for
it.

1. Implement Redis rate limiting + deterministic abuse protection per
   [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
   (design complete; implementation not started — see "Next major task"
   above). Resolve the ADR's "Open decisions" (§22) as part of that work,
   with rationale recorded alongside the code.
2. Introduce Playwright E2E coverage for auth/password-recovery — not
   started.
3. Only after the above: begin GitHub Issue #3 (Knowledge Ingestion) —
   not started.
