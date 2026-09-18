# Security

**Status:** PARTIALLY IMPLEMENTED — authentication (HttpOnly cookie + CSRF,
password recovery), authorization, workspace isolation, audit logging, and
rate limiting on auth endpoints are now implemented and tested (GitHub
Issue #2 — Authentication & Workspaces; see "Authentication &
authorization", "Rate limiting approach", and "Audit logging" below for
exactly what's real). Upload validation and prompt-injection defense
remain not implemented — there's no upload or generation surface yet for
them to protect. The Issue #1 foundation's generic protections (centralized
error handling, loud-failure config loading) are also in place — see
"Errors and information disclosure" and "Secret management" below. See
[`PROJECT_STATE.md`](../PROJECT_STATE.md) for current, per-control status.

## Trust boundaries and core principles

1. **User data is isolated by workspace.** No user or process should be
   able to read or write another workspace's data.
2. **Authorization must be enforced server-side.** Client-side checks
   (hidden UI, disabled buttons) are never a substitute for a server-side
   permission check.
3. **Retrieved documents are untrusted input.** Anything pulled from the
   corpus during retrieval is data, not instructions.
4. **Prompt injection from retrieved content must not override system
   instructions.** The generation layer must be designed so that text
   embedded in a retrieved chunk cannot cause the LLM to ignore its system
   prompt, exfiltrate data, or take unintended actions.
5. **Secrets must never be committed.** `.env.example` contains placeholders
   only; real secrets live outside version control.
6. **Uploaded files are untrusted.** Every upload must be validated before
   it's processed or stored.
7. **File paths and filenames must be safely handled** — no path traversal,
   no trusting user-supplied filenames for storage paths.
8. **Rate limits must protect expensive operations** (auth attempts,
   uploads, embedding calls, LLM calls).
9. **Errors exposed to users must not reveal stack traces, internal paths,
   or secrets.**
10. **Audit logs should capture security-relevant actions** (auth events,
    workspace membership changes, document deletion, permission changes).
11. **Security assumptions must be tested, not merely documented** — see
    "Security testing" below and `AGENTS.md` §3.

## Authentication & authorization

**Implemented (Issue #2)**, all in `backend/app/core/security.py` and
`backend/app/services/auth_service.py` unless noted:

- Passwords hashed with Argon2id (see
  [ADR 0004](DECISIONS/0004-password-hashing-argon2id.md)).
- Short-lived access tokens backed by server-tracked refresh/session
  records — the architecture is **not** purely stateless. See
  [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  for the full model.
- **Tokens are delivered exclusively via `HttpOnly` cookies, never in a
  response body or an `Authorization` header** — the browser attaches them
  automatically; JavaScript never reads or holds them. A separate,
  non-`HttpOnly` `csrf_token` cookie plus an `X-CSRF-Token` header (double-
  submit pattern) protects every state-changing request, including
  `login`/`register` themselves. `SameSite`/`Secure`/`Domain` are
  deployment-aware (`COOKIE_SAMESITE`/`COOKIE_SECURE`/`COOKIE_DOMAIN`), and
  are never weakened for local-dev convenience. See
  [ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md) for the
  full model, including the "different origin ≠ cross-site" distinction
  that governs `COOKIE_SAMESITE` and the explicit requirements for a
  genuinely cross-site deployment.
- Sessions/devices are listable and individually revocable by the user;
  refresh tokens rotate on use; **logout invalidates the corresponding
  session's refresh capability immediately.** Reuse of a rotated-out
  refresh token revokes that session outright. Per ADR 0003, an
  already-issued access token is not retroactively invalidated by
  logout/session-revocation/password-reset — its blast radius is bounded
  by its short expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`), independent of
  session state; only its refresh capability dies immediately.
- **Password recovery** (`backend/app/services/password_reset_service.py`):
  reset tokens are cryptographically random (`secrets.token_urlsafe(32)`,
  256 bits), SHA-256-hashed at rest (raw value never stored or logged),
  single-use, and expiring (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`).
  `forgot-password` always returns the same generic response regardless of
  whether the email exists, with timing equalized via a dummy Argon2
  verification on the not-found path, to resist enumeration. A successful
  reset revokes every existing session for that user
  (`session_repository.revoke_all_for_user`) and reuses the same Argon2id
  hashing as normal password changes. Email delivery goes through the
  `EmailProvider` abstraction (`backend/app/services/email_provider.py`) —
  `console` (stdout, dev/test fallback) or `smtp` (any SMTP-compatible
  provider; local dev points it at Mailpit). `ENVIRONMENT=production` with
  `EMAIL_PROVIDER=console` fails at startup (`app/core/config.py`), since
  stdout is typically captured by log aggregation in real deployments,
  which would leak raw reset tokens into logs.
- Role-based authorization within a workspace: `OWNER`, `ADMIN`, `MEMBER`,
  `VIEWER` — enforced server-side on every workspace-scoped endpoint via
  `backend/app/core/dependencies.py`'s `require_workspace_role`, not just
  at the UI layer. See `docs/API_CONTRACT.md`'s authorization matrix.
- Rate limiting and brute-force protection on login/registration/refresh/
  forgot-password/reset-password (see "Rate limiting approach" below).
- Login failures, and forgot-password requests, return the same generic
  message whether the account exists or not, resisting enumeration via
  either endpoint.

## Rate limiting approach

Rate limiting is a firm requirement (see principle 8 above). It was
deliberately built in-process first, with no external session/cache store.
Going further is justified by architectural certainty, not measured
production evidence — this project has no production deployment, so there
is no telemetry or incident to point to (see [ADR 0006](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
§1's honest framing). That distinction, and the resulting design, is
documented below rather than anticipated speculatively:

- **Implemented (Issue #2):** an in-process fixed-window limiter
  (`backend/app/core/rate_limit.py`) guards `register`, `login`,
  `refresh`, `forgot-password`, and `reset-password`, keyed by client IP —
  correct for the current single-process deployment
  (`infra/docker/backend.Dockerfile` runs no `--workers`); no
  PostgreSQL-backed counters were needed yet. Per-IP limiting does not stop
  a distributed low-rate attempt to guess a reset token, but the token
  space (256 bits) makes that infeasible regardless of request rate.
- **Designed, not yet implemented:** horizontal scale-out (more than one
  backend instance behind a load balancer) breaks the in-process limiter's
  core assumption — a verified, deterministic architectural fact, not a
  hypothetical one, but *not* itself the "measured requirement" evidence
  bar [ADR 0001](DECISIONS/0001-modular-monolith-over-microservices.md)
  sets for adopting new infrastructure in *production* (no such measurement
  exists yet — see ADR 0006 §1). This ADR treats that architectural
  certainty as sufficient to justify a *design*, a lower bar than
  production adoption. The full design is documented in
  [ADR 0006](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md):
  Redis-backed token-bucket rate limiting plus a deterministic (non-ML),
  rule-based abuse-detection layer, an operation-aware Redis failure
  policy, and a key design that never stores raw credentials.
- **Redis-backed distributed rate limiting implemented, committed,
  pushed, and merged into `main` — both the engine and its endpoint
  wiring:** Slice 1 (squash commit `46ef03b` via PR #11) added the
  multi-key atomic Lua token-bucket engine (`RedisTokenBucketLimiter`,
  ADR §8/§10), a Redis connection abstraction, centralized key
  construction with a keyed-HMAC (not plain-hash) email identifier (ADR
  §14), and a trusted-proxy-aware IP resolver (`resolve_client_ip()`, ADR
  §9a — secure-by-default: `X-Forwarded-For` ignored unless the peer is
  within a configured trusted CIDR). Slice 2 (squash commit `5391a78` via
  PR #12) wired all of it into every `enforce_*_rate_limit` dependency —
  `register`, `login`, `refresh`, `forgot-password`, `reset-password` now
  all attempt the Redis engine first, using ADR §9's exact per-operation
  dimensions — IP always; the submitted email, as a keyed-HMAC
  identifier, for `login`/`forgot-password`; the session ID, parsed from
  the refresh-token cookie without a database round-trip, for
  `refresh` — falling back to the in-process limiter per ADR §13's
  operation-aware policy when Redis is unreachable. **This is now active
  in the committed codebase on `main`.** One implementation-time
  refinement of §13, recorded with rationale in ADR 0006's "Implementation
  status" and `SOLVING.md`: an unconfigured Redis always falls back to
  the in-process limiter, for every operation including `register`;
  §13's literal Tier B fail-open is reserved for a genuine mid-request
  outage of an *already-configured* Redis. A structured log line fires on
  a genuine Redis-failure fallback (ADR §13's own requirement —
  `app.rate_limit` logger, `operation`/`policy` fields only, never a
  request-derived value). Tested: 183 backend tests (119 pre-Redis + 51
  Slice 1 + 13 Slice 2), verified locally against real Postgres + real
  Redis and via GitHub Actions CI on PR #12 (backend/frontend/Docker-build
  checks all passed). The deterministic abuse-detection layer (ADR §11)
  does not exist yet — no `STRICT_THROTTLE`/`TEMPORARY_BLOCK` escalation
  is possible. Redis's role remains strictly limited to ephemeral
  rate-limit state; PostgreSQL remains the only durable datastore (ADR
  0002) — Redis never becomes a second source of truth for users,
  sessions, workspaces, or audit logs.

## Upload & document safety

- Validate MIME type, file extension, and size before processing.
- Reject or safely handle malformed/corrupt documents without crashing the
  ingestion pipeline.
- Store uploaded files using generated identifiers, not user-supplied
  filenames, to avoid path traversal and collision issues.
- Apply resource and time limits to parsing/processing to bound the impact
  of a pathological file.

## Prompt injection defense

Because retrieved chunks are untrusted, the generation layer's design must
assume a malicious document could contain text like "ignore previous
instructions" or attempts to exfiltrate other users' data. Mitigations to
apply when the generation module is built (and to test explicitly — see
below): structurally separating system instructions from retrieved content
in the prompt, not granting the LLM tool/data access beyond what's needed to
answer from the provided evidence, and treating any instruction-like text
inside retrieved content as inert.

## Secret management

- Real secrets are never committed; `.env.example` lists variable names
  with empty/placeholder values only.
- Configuration loading should fail loudly (not silently default) if a
  required secret is missing in a non-development environment.

## Errors and information disclosure

- User-facing errors are generic and actionable ("upload failed — file too
  large") without stack traces, file paths, query text, or internal IDs
  that aren't meant to be public.
- Detailed error information goes to logs/observability (see
  [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) §"Observability"), not to the
  response body.

## Audit logging

**Implemented (Issue #2)** — `backend/app/core/audit.py` (`AuditEvent`
constants, plain strings for extensibility) and
`backend/app/repositories/audit_log_repository.py`. Captured today:
registration, login success/failure, logout, session revocation, refresh-
token reuse detection, password-reset request/success, workspace
create/delete/membership changes, and authorization denials. Audit writes
commit immediately and independently of the surrounding request's
transaction, so a denial's audit record survives even when the request
goes on to raise an error. `user_id`/`workspace_id` use `ON DELETE SET
NULL` so the audit trail outlives the account/workspace it references.
Document upload/delete audit events will be added when that surface exists
(Issue #3).

## Security testing

Per `AGENTS.md` §3, security assumptions are verified, not just documented:

- **Cross-workspace access tests** — attempt to read/write another
  workspace's documents, conversations, and collections; must fail.
  **Implemented (Issue #2)** for workspaces/membership themselves —
  `backend/tests/test_workspaces.py` proves a non-member gets `404` (never
  `403`, never real data) on every workspace-scoped endpoint. Documents/
  conversations/collections don't exist yet, so this extends to them when
  they're built.
- **Malicious upload tests** — oversized files, mismatched
  extension/content, malformed PDFs/DOCX, zip-bomb-style payloads; must be
  rejected or safely contained. Not implemented — no upload surface exists
  yet (Issue #3).
- **Prompt injection tests** — documents containing instruction-like text
  ("ignore the above," attempts to leak system prompt or other users'
  data); the system must not comply with injected instructions. Not
  implemented — no generation surface exists yet (Issue #4).
- **Auth bypass tests** — attempt to access protected endpoints without a
  valid session, with an expired session, or with a session from a
  different workspace. **Implemented (Issue #2)** —
  `backend/tests/test_auth.py` covers missing/garbage/expired/wrong-signature
  access tokens and revoked refresh tokens; `test_workspaces.py` covers a
  valid session with no membership in the target workspace.
- **Path traversal tests** — filenames/paths like `../../etc/passwd` must
  be neutralized. Not implemented — no file storage surface exists yet
  (Issue #3).
- **Rate limiting tests** — confirm limits actually trigger under load on
  login and expensive endpoints. **Implemented (Issue #2)** —
  `backend/tests/test_auth.py` drives `register`/`login`/`refresh`, and
  `backend/tests/test_password_reset.py` drives `forgot-password`/
  `reset-password`, past their limits and asserts `429`.
- **CSRF tests** — missing/mismatched token rejected, valid token accepted,
  safe methods exempt, login/register themselves protected (login CSRF),
  a token from one client's cookie jar rejected against another's request.
  **Implemented (Issue #2)** — `backend/tests/test_csrf.py`,
  `backend/tests/test_cookie_security.py` (also asserts the actual
  `Set-Cookie` attributes: `HttpOnly`/`Path`/`SameSite`, and that the CSRF
  cookie is deliberately not `HttpOnly`), and
  `backend/tests/test_password_reset.py` (CSRF specifically on
  `forgot-password`/`reset-password`).
- **Cookie-only authentication tests** — an `Authorization: Bearer` header
  alone (no cookie) must not authenticate, and must not satisfy CSRF
  either. **Implemented (Issue #2)** — `backend/tests/test_cookie_security.py`.
- **Password-reset security tests** — enumeration resistance (same
  response/timing for known vs. unknown email), single-use/expired/invalid
  token rejection, session invalidation after reset, a token issued for one
  user never affecting another user. **Implemented (Issue #2)** —
  `backend/tests/test_password_reset.py`.

The remaining tests (malicious upload, prompt injection, path traversal)
are written alongside their corresponding feature per the Definition of
Done in `AGENTS.md` §7, not deferred to a later "security phase."

## Related documents

- [`docs/REQUIREMENTS.md`](REQUIREMENTS.md) — functional security
  requirements (auth, workspaces).
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — where security-relevant code
  lives (`core/`, `api/` dependencies).
- [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) — generation-layer design where
  prompt injection defense is applied.
- [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  — the authentication/session model referenced above.
- [`docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md`](DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  — the cookie/CSRF delivery model, and the "different origin ≠ cross-site"
  distinction governing deployment configuration.
- [`docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md`](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
  — the Redis rate-limiting/abuse-protection design referenced above
  (design only; not yet implemented).
