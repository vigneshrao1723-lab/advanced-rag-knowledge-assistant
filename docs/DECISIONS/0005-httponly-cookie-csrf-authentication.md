# 0005. Browser authentication: HttpOnly cookies with double-submit CSRF

**Status:** Accepted
**Date:** 2026-09-14

## Context

[ADR 0003](0003-authentication-session-architecture.md) established
short-lived access tokens plus server-tracked refresh sessions, but left
open "whether refresh tokens are delivered via an HttpOnly cookie, response
body, or both." The initial implementation delivered both access and
refresh tokens in the JSON response body, for the frontend to hold and
attach as an `Authorization: Bearer` header. That design was rejected after
implementation because it required the frontend to hold raw tokens in
memory/JavaScript-reachable state, which is unnecessary for a first-party
browser client and only widens the XSS blast radius (any script-injection
vulnerability, anywhere on the page, can read `localStorage`/JS variables
and exfiltrate the tokens).

This ADR documents the design actually implemented: tokens delivered
exclusively via HttpOnly cookies, with CSRF protection added to close the
attack surface that cookie-based auth reopens (CSRF), and is deliberately
explicit about a distinction the earlier cookie-configuration comments
left implicit and that is easy to get wrong: **"different origin" and
"cross-site" are not the same thing**, and conflating them leads to either
an unnecessarily weakened `SameSite` setting or a deployment that silently
fails to send cookies at all.

## Decision

- **Access token** (`access_token` cookie): `HttpOnly`, `Path=/`, lifetime =
  `ACCESS_TOKEN_EXPIRE_MINUTES`. Sent on every request.
- **Refresh token** (`refresh_token` cookie): `HttpOnly`, `Path=/api/v1/auth`
  (narrowly scoped — never sent on ordinary API calls, only to the
  auth namespace that actually consumes it), lifetime =
  `REFRESH_TOKEN_EXPIRE_DAYS`.
- **CSRF token** (`csrf_token` cookie): deliberately **not** `HttpOnly` —
  the double-submit pattern requires JavaScript to read it and echo it as
  the `X-CSRF-Token` header on every state-changing request. A cross-site
  attacker can make the browser attach the auth cookies to a forged
  request, but same-origin policy stops them from reading this cookie's
  value to also forge a matching header.
- All three cookies share the same `SameSite`/`Secure`/`Domain` resolution
  (`app/core/config.py`'s `cookie_samesite` / `cookie_secure_resolved` /
  `cookie_domain`, applied in `app/core/cookies.py` and
  `app/core/csrf.py`) — one deployment-aware source of truth, not
  per-cookie special cases.
- CSRF is enforced on every non-safe method (`POST`/`PUT`/`PATCH`/`DELETE`),
  **including `login`/`register` themselves** (defends against login CSRF —
  forcing a victim into an attacker's account), and exempts
  `GET`/`HEAD`/`OPTIONS`.
- The response body **never** contains a token — `AuthResponse` is
  `{user: UserRead}` only. Non-browser API clients are out of scope for
  this ADR; if one is needed later, it should get its own token-delivery
  path (e.g. a response-body flow for machine clients), not a weakening of
  the browser path.

## "Different origin" vs. "cross-site" — do not conflate them

This distinction governs which `COOKIE_SAMESITE` value a deployment
actually needs, and getting it wrong either over-weakens CSRF protection
or silently breaks the cookie flow. Two separate concepts are in play:

- **Origin** = scheme + host + port. `http://localhost:3000` and
  `http://localhost:8000` are different origins. `https://app.example.com`
  and `https://api.example.com` are different origins.
- **Site** = the registrable domain (eTLD+1, per the public suffix list —
  what a browser's `SameSite` cookie logic actually keys off). `app.example.com`
  and `api.example.com` are **different origins but the same site**
  (`example.com`). `localhost` has no registrable-domain suffix on the
  public suffix list, so every `localhost:<port>` is considered the same
  site regardless of port.

Consequences that follow directly from this:

1. **This project's local dev setup (`localhost:3000` frontend,
   `localhost:8000` backend) is different-origin but same-site.** That is
   *why* the default `COOKIE_SAMESITE=lax` works locally without any
   cross-site accommodation — `SameSite=Lax` is a same-site cookie policy,
   and `localhost:3000` ↔ `localhost:8000` satisfies it. This is not a
   coincidence or a relaxed rule for dev convenience; it is the correct,
   secure configuration for a same-site deployment, local or not.
2. **A subdomain-split production deployment** (e.g. frontend at
   `app.example.com`, backend at `api.example.com`) is *also* same-site,
   for the same reason as (1) — both share the registrable domain
   `example.com`. This deployment should use `COOKIE_SAMESITE=lax` (not
   `none`) and set `COOKIE_DOMAIN=.example.com` so the cookie is valid
   across both subdomains. Setting `SameSite=None` here would be an
   unforced weakening: it drops CSRF-relevant browser protections that
   `Lax` provides for no reason, since the deployment was never cross-site
   to begin with.
3. **CORS is origin-based, not site-based, and applies regardless of (1)
   and (2).** Every scenario above still requires `CORS_ALLOWED_ORIGINS`
   to list the frontend's exact origin(s) (scheme + host + port) and
   `allow_credentials=True` (already the default in `app/main.py`), because
   the browser enforces CORS on the `fetch` layer purely by origin — same
   site does not exempt a request from CORS. This is why local dev, despite
   being same-site, still needs `CORS_ALLOWED_ORIGINS=http://localhost:3000`
   configured, and why `frontend/lib/api-client.ts` still sets
   `credentials: "include"` on every request.
4. **A genuinely cross-site deployment** — frontend and backend on
   different registrable domains entirely (e.g. `app.example.com` and
   `backend-service.up.a-paas-provider.io`) — is the *only* case that
   actually needs `COOKIE_SAMESITE=none`. This is not a preference; browsers
   will not send a `SameSite=Lax` (or `Strict`) cookie on a genuinely
   cross-site request at all, so the cookie-based auth flow simply would
   not work without it.

## Required configuration for a cross-site deployment

Do not attempt this by trial and error against browser behavior in
production. If frontend and backend are genuinely on different
registrable domains, all of the following are required together — the
`Settings` model_validator in `app/core/config.py` already enforces the
first pairing at startup, but the rest are architectural requirements this
document is the source of truth for:

- `COOKIE_SAMESITE=none` (`_validate_cookie_security` then requires
  `COOKIE_SECURE` to resolve `true`, which it does automatically unless
  explicitly overridden to `false`, in which case startup fails loudly).
- `COOKIE_SECURE=true` in effect (the default derivation already forces
  this whenever `COOKIE_SAMESITE=none`) — cookies must be served over
  HTTPS; browsers silently drop `SameSite=None` cookies without `Secure`.
- `COOKIE_DOMAIN` left unset (host-only) unless the backend itself spans
  subdomains that must all share the cookie — it does **not** unify a
  frontend and backend that are on genuinely different registrable
  domains; that is not what `Domain` is for.
- `CORS_ALLOWED_ORIGINS` listing the exact frontend origin(s) — this is
  unrelated to the `SameSite` setting and is required in every deployment
  shape, cross-site or not (see point 3 above).
- Browser/ecosystem constraints to plan for, not to code around: some
  browsers (notably Safari, and Chrome's ongoing third-party-cookie
  changes) restrict or block cookies set in a genuinely cross-site context
  by default privacy features (Intelligent Tracking Prevention and
  similar), independent of `SameSite=None; Secure` being correctly set.
  A cross-site deployment of this application should be treated as
  something to explicitly test against real target browsers, not assumed
  to work everywhere `SameSite=None` is technically permitted. If this
  becomes a real requirement, prefer restructuring the deployment to be
  same-site (a subdomain split, per point 2 above, or a reverse proxy that
  puts frontend and backend under one registrable domain) over shipping a
  cross-site cookie flow that degrades unpredictably across browsers.

## Alternatives considered

- **Keep bearer tokens in the response body** — rejected; this is the
  design being superseded (see Context).
- **`SameSite=None` everywhere, "to be safe for any deployment"** —
  rejected. This is the exact conflation this ADR warns against: it
  weakens CSRF-relevant protection for the common same-site case (local
  dev and same-registrable-domain production deployments) for no benefit,
  and does so silently, since nothing would visibly break — it would just
  be a strictly weaker default no one asked for.
- **Validate the `Origin`/`Referer` header server-side as the sole CSRF
  defense, instead of double-submit cookie** — not adopted as the primary
  mechanism. Double-submit cookie is simpler to reason about and test, and
  does not depend on every intermediate proxy/CDN faithfully preserving
  the `Origin` header. Origin validation remains a reasonable defense-in-depth
  addition later; it is not required given CORS + double-submit already
  in place.

## Consequences

- `docs/SECURITY.md`'s "Authentication & authorization" section is
  corrected to describe this cookie/CSRF model instead of "bearer access
  tokens."
- Any future non-browser API client needs its own explicitly-designed
  token-delivery path; it must not reuse the cookie flow or push the
  frontend back toward storing tokens in JavaScript-reachable state.
- Deploying frontend and backend on different registrable domains is a
  deliberate, documented choice with the explicit configuration above and
  the stated browser caveats — not a configuration flag flipped without
  reading this document.
