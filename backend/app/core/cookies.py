"""HttpOnly cookie management for browser authentication (ADR 0005).

Access/refresh tokens are never exposed to JavaScript — they live only in
HttpOnly cookies, set and cleared here, in one place, so every route uses
identical, deployment-aware attributes (`app/core/config.py`'s
`cookie_samesite` / `cookie_secure_resolved` / `cookie_domain`). Never
default these to something weaker "for local dev" — local dev already gets
a secure configuration (`SameSite=Lax`, no `Secure` over plain HTTP, which
is what browsers expect for same-site HTTP); a genuinely cross-site
deployment must opt in to `SameSite=None` explicitly (see `config.py`),
which then forces `Secure`.
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import get_settings

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"

# The refresh cookie is scoped narrowly to the endpoints that actually need
# it, so it isn't sent on every ordinary API request.
_REFRESH_COOKIE_PATH = "/api/v1/auth"
_DEFAULT_COOKIE_PATH = "/"


def _cookie_kwargs(*, path: str) -> dict[str, object]:
    settings = get_settings()
    kwargs: dict[str, object] = {
        "httponly": True,
        "secure": settings.cookie_secure_resolved,
        "samesite": settings.cookie_samesite,
        "path": path,
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    access_max_age_seconds: int,
    refresh_max_age_seconds: int,
) -> None:
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=access_max_age_seconds,
        **_cookie_kwargs(path=_DEFAULT_COOKIE_PATH),  # type: ignore[arg-type]
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        refresh_token,
        max_age=refresh_max_age_seconds,
        **_cookie_kwargs(path=_REFRESH_COOKIE_PATH),  # type: ignore[arg-type]
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    domain = settings.cookie_domain
    response.delete_cookie(
        ACCESS_TOKEN_COOKIE,
        path=_DEFAULT_COOKIE_PATH,
        domain=domain,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        REFRESH_TOKEN_COOKIE,
        path=_REFRESH_COOKIE_PATH,
        domain=domain,
        samesite=settings.cookie_samesite,
    )
