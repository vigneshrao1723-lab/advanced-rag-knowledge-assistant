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
limiting + a deterministic abuse-detection layer — has **not been
started**: no Redis dependency, service, code, or ADR exists yet. See
"Next major task" below for the constraints already recorded for whoever
picks it up. Do not start it, Playwright, or Issue #3 without an explicit
go-ahead.

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

## Explicitly NOT done (do not assume otherwise)

- **Redis distributed rate limiting** — not started. No Redis dependency,
  service, or code exists anywhere in this repository.
- **Deterministic abuse/risk layer** — not started. (If you build this
  later: it must be deterministic, rule-based logic — never call it "AI"
  or claim ML/statistical evaluation unless an actual evaluated model
  backs that claim.)
- **Concurrency/race-condition testing for Redis** — not applicable yet;
  there is no Redis to test.
- **Playwright browser E2E** — not started. No config, no test files, no
  dependency. The live-Docker verification done for this checkpoint
  (curl/Python against running containers, including reading Mailpit's
  REST API directly) is real integration verification but is **not** a
  substitute for actual browser automation — say so explicitly if asked,
  don't imply Playwright coverage exists.
- **Issue #3 (document ingestion)** — not started.
- **Later RAG retrieval/generation features** — not started.

## Next major task: Redis rate limiting + deterministic abuse protection

This is the next thing to build. Issue #2 is already reviewed, committed,
pushed, PR'd (#10), and merged into `main` — this task starts clean, not
combined with it, and has not been started itself.

Constraints for whoever picks this up:

- **Evolve `backend/app/core/rate_limit.py`, don't blindly replace it.**
  The existing `FixedWindowRateLimiter` and its per-endpoint
  `enforce_*_rate_limit` dependencies are working, tested (in
  `tests/test_auth.py`, `tests/test_password_reset.py`,
  `tests/test_rate_limit.py`), and correct for a single-process
  deployment. Understand why each limit exists and what test currently
  asserts it before changing the mechanism underneath.
- **PostgreSQL remains the authoritative durable datastore** (ADR 0002).
  Redis, when introduced, is for ephemeral distributed rate-limiting/
  abuse state only — not a second source of truth for anything that must
  survive a restart or be queried historically (that's still Postgres +
  `audit_logs`).
- **Redis failure behavior must be operation-aware and security-
  conscious** — decide deliberately, per operation, whether a Redis
  outage should fail open (allow the request, degrade to no limiting) or
  fail closed (reject), rather than picking one global default. Document
  the choice and why in the ADR this work should produce.
- **No unbounded attacker queues** — any queuing/backoff mechanism must
  have a hard bound; don't let a malicious client's requests accumulate
  server-side memory or Redis keys without expiry.
- **This needs its own ADR** before or alongside implementation
  (`docs/DECISIONS/0006-...`), per `CLAUDE.md` §4 — introducing Redis is
  a new infrastructure dependency, which is exactly the kind of decision
  that document instructs stopping for.
- Files/areas to inspect first: `backend/app/core/rate_limit.py` (current
  mechanism), `backend/tests/test_rate_limit.py` and every
  `enforce_*_rate_limit` call site (`app/api/v1/auth.py`), `docs/SECURITY.md`
  "Rate limiting approach" (documents the existing no-premature-
  infrastructure reasoning this decision needs to explicitly revisit),
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

1. Start the Redis rate-limiting + abuse-detection work per "Next major
   task" above — write ADR `docs/DECISIONS/0006-...` first (does not
   exist yet).
2. Introduce Playwright E2E coverage for auth/password-recovery — not
   started.
3. Only after the above: begin GitHub Issue #3 (Knowledge Ingestion) —
   not started.
