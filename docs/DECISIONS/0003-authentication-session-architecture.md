# 0003. Authentication: short-lived access tokens with server-tracked sessions

**Status:** Accepted
**Date:** 2026-09-11

## Context

The initial documentation pass described authentication in
`docs/API_CONTRACT.md` as simply "bearer tokens," while
`docs/REQUIREMENTS.md` and `docs/SECURITY.md` separately committed firmly
to session/device listing and per-session revocation. Pure stateless bearer
tokens (e.g., long-lived JWTs validated only by signature) cannot satisfy
per-session revocation without some form of server-side state — the
second-pass documentation audit flagged this as an unresolved contradiction
that needed resolving before Authentication work begins. This ADR resolves
it, consistent with the modular-monolith, no-premature-infrastructure
principles already recorded in [ADR 0001](0001-modular-monolith-over-microservices.md)
and [ADR 0002](0002-postgresql-pgvector-initial-vector-store.md) — no
external session store is introduced solely to solve this.

## Decision

Authentication uses:

- **Short-lived access tokens** — bearer credentials, presented on each
  request, short expiry (minutes, not days), validated without a database
  round-trip.
- **Server-tracked refresh/session records** — each login or device
  creates a session record, stored in PostgreSQL alongside all other
  application data (no separate store), that a refresh token maps to. The
  record carries at least: user, device/session identity, created/last-used
  timestamps, and revocation state.
- **Per-device/session identity** — a user can be logged in from multiple
  devices/sessions simultaneously, each tracked independently.
- **Session listing and revocation** — a user can list their active
  sessions and revoke one (or all) individually; revoking a session
  immediately invalidates its refresh capability.
- **Refresh-token rotation** — each use of a refresh token issues a new
  refresh token and invalidates the old one, so a leaked, unused refresh
  token has a limited window of validity and reuse is detectable.
- **Logout invalidates the session** — logout marks the corresponding
  session record revoked, invalidating its refresh capability immediately.
- **Server-side authorization on every request** — session/token validity
  and workspace-role checks happen server-side on every protected request;
  there is no client-trusted authorization state.
- **The overall architecture is not stateless.** Access tokens are
  bearer-style for transport convenience, but the system depends on
  server-tracked session state for revocation — "bearer token" alone is not
  an accurate description of the model, and `docs/API_CONTRACT.md` is
  corrected to reflect that.
- **No external session store (e.g., Redis) is introduced solely for
  this.** Session/refresh records live in PostgreSQL like every other
  entity, consistent with ADR 0002.

## Alternatives considered

- **Pure stateless JWT bearer tokens with no server-side session record** —
  rejected. Cannot support per-device session listing or immediate refresh
  revocation without a denylist, which is itself server-side state — so it
  doesn't avoid the complexity, it just does it worse (no listing, coarser
  revocation).
- **Server-side session cookies only (no bearer access token)** — rejected
  for now. A separate short-lived access-token layer keeps the API usable
  by non-browser clients without being tied to cookie semantics; this can
  be revisited if it proves unnecessary.
- **Redis-backed session store** — rejected for the initial implementation,
  consistent with ADR 0002's no-second-datastore rule. PostgreSQL can hold
  and index session rows without materially different performance at this
  project's scale; revisit via a new ADR only if a measured requirement
  justifies it.

## Consequences

- `sessions` becomes a **core** (not "potential") entity — see
  `docs/DATA_MODEL.md`.
- `docs/API_CONTRACT.md`'s `/api/v1/auth` description is corrected to
  reflect this model rather than "bearer tokens" alone.
- Logout, refresh, and session-listing/revocation endpoints all depend on
  the same `sessions` table and should be designed together.
- Access-token validation stays fast (no DB hit) since it's short-lived and
  signature-based; only refresh and explicit session management touch the
  `sessions` table, keeping the normal authenticated-request hot path cheap.

## Security implications

- A leaked access token has a bounded blast radius (its short expiry),
  independent of session revocation.
- Refresh-token rotation with reuse detection lets the system detect a
  stolen refresh token: if a rotated-out refresh token is presented again,
  the associated session should be treated as compromised and revoked.
- Session revocation must be checked on refresh (not just on login), or
  revocation would be ineffective until natural access-token expiry.
- This model still requires the protections already documented in
  `docs/SECURITY.md`: password hashing, rate limiting/brute-force
  protection on login and refresh, and audit logging of session
  creation/revocation events.

## What remains to be finalized during implementation

- Exact access-token and refresh-token lifetimes.
- Whether refresh tokens are delivered via an HttpOnly cookie, response
  body, or both, per client type.
- The specific reuse-detection response (revoke just the one session vs.
  all sessions for that user).
- Password hashing algorithm choice (already flagged as deferred in
  `docs/SECURITY.md`).

This ADR describes the intended design only — **no part of it is
implemented**; see `PROJECT_STATE.md`.
