"""CSRF protection (double-submit cookie) for cookie-authenticated
requests (ADR 0005).

Because authentication now lives in HttpOnly cookies that the browser
attaches automatically, a malicious site can trigger state-changing
requests against this API using a victim's cookies without ever seeing
them. The double-submit pattern defeats this: a second, non-HttpOnly
`csrf_token` cookie carries a value that must also be echoed back as the
`X-CSRF-Token` header. A cross-site attacker can trigger the cookie-bearing
request but — same-origin policy — cannot read the cookie's value to put
it in the header, so the two won't match.

Every safe method (`GET`/`HEAD`/`OPTIONS`) is exempt; every state-changing
method requires a match, **including `login`/`register`** — skipping them
would allow "login CSRF" (forcing a victim into an attacker's account).
The frontend fetches a CSRF cookie via `GET /api/v1/auth/csrf` before
rendering the login/register forms.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.observability.request_id import get_request_id

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cookie_token = request.cookies.get(CSRF_COOKIE)

        if request.method not in _SAFE_METHODS:
            header_token = request.headers.get(CSRF_HEADER)
            if (
                not cookie_token
                or not header_token
                or not secrets.compare_digest(cookie_token, header_token)
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "csrf_error",
                            "message": "Missing or invalid CSRF token.",
                            "request_id": get_request_id(),
                        }
                    },
                )

        response = await call_next(request)

        if not cookie_token:
            settings = get_settings()
            cookie_kwargs: dict[str, object] = {
                "httponly": False,  # must be JS-readable to echo back as a header
                "secure": settings.cookie_secure_resolved,
                "samesite": settings.cookie_samesite,
                "path": "/",
            }
            if settings.cookie_domain:
                cookie_kwargs["domain"] = settings.cookie_domain
            response.set_cookie(CSRF_COOKIE, generate_csrf_token(), **cookie_kwargs)  # type: ignore[arg-type]

        return response
