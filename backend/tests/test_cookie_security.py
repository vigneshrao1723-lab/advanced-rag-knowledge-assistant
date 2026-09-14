"""Explicit assertions on the cookie/CSRF/CORS mechanics of ADR 0005.

`test_auth.py` and `test_csrf.py` already exercise the *behavior* (login
works, CSRF is enforced, etc.) through the cookie jar. This file asserts
the actual wire-level `Set-Cookie` attributes and CORS headers directly —
the things a curl/manual check can miss if a future change accidentally
loosens them.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"
_ALLOWED_ORIGIN = "http://localhost:3000"


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    email = _unique_email()
    headers = csrf_headers(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD},
        headers=headers,
    )
    assert response.status_code == 201
    return email, headers


def _set_cookie_for(response: httpx.Response, cookie_name: str) -> str:
    for raw in response.headers.get_list("set-cookie"):
        if raw.startswith(f"{cookie_name}="):
            return raw
    raise AssertionError(f"no Set-Cookie header found for {cookie_name!r}")


class TestLoginRegisterCookieAttributes:
    def test_register_sets_httponly_access_and_refresh_cookies(self, client: TestClient) -> None:
        email = _unique_email()
        headers = csrf_headers(client)

        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": _PASSWORD},
            headers=headers,
        )

        assert response.status_code == 201
        access_cookie = _set_cookie_for(response, "access_token")
        refresh_cookie = _set_cookie_for(response, "refresh_token")

        assert "HttpOnly" in access_cookie
        assert "HttpOnly" in refresh_cookie
        assert "SameSite=lax" in access_cookie.lower() or "samesite=lax" in access_cookie.lower()
        assert "Path=/;" in access_cookie or access_cookie.rstrip().endswith("Path=/")
        assert "Path=/api/v1/auth" in refresh_cookie

    def test_login_sets_httponly_access_and_refresh_cookies(self, client: TestClient) -> None:
        email, headers = _register(client)

        response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": _PASSWORD},
            headers=headers,
        )

        assert response.status_code == 200
        access_cookie = _set_cookie_for(response, "access_token")
        refresh_cookie = _set_cookie_for(response, "refresh_token")
        assert "HttpOnly" in access_cookie
        assert "HttpOnly" in refresh_cookie
        assert "Path=/api/v1/auth" in refresh_cookie

    def test_csrf_cookie_is_not_httponly(self, client: TestClient) -> None:
        """The CSRF cookie must be readable by JavaScript — that's the whole
        point of the double-submit pattern (frontend reads it and echoes it
        as a header)."""
        response = client.get("/api/v1/auth/csrf")

        csrf_cookie = _set_cookie_for(response, "csrf_token")
        assert "HttpOnly" not in csrf_cookie

    def test_login_response_body_contains_no_tokens(self, client: TestClient) -> None:
        email, headers = _register(client)

        response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": _PASSWORD},
            headers=headers,
        )

        body = response.json()
        assert set(body.keys()) == {"user"}


class TestRefreshRotatesCookies:
    def test_refresh_issues_new_access_and_refresh_cookies(self, client: TestClient) -> None:
        email, headers = _register(client)
        old_refresh = client.cookies.get("refresh_token")

        response = client.post("/api/v1/auth/refresh", headers=headers)

        assert response.status_code == 200
        # The refresh token's secret is freshly random on every rotation
        # (app/core/security.py's `generate_refresh_token`), so it must
        # always differ. The access token JWT is *not* asserted to differ
        # byte-for-byte here: refresh does not rotate the session id, and
        # `exp` has one-second granularity, so a refresh issued within the
        # same wall-clock second as the original token can legitimately
        # produce an identical JWT — that's expected, not a bug.
        new_refresh_cookie = _set_cookie_for(response, "refresh_token")
        assert old_refresh not in new_refresh_cookie
        access_cookie = _set_cookie_for(response, "access_token")
        assert "HttpOnly" in access_cookie

    def test_refresh_without_a_refresh_cookie_is_rejected(self, client: TestClient) -> None:
        headers = csrf_headers(client)

        response = client.post("/api/v1/auth/refresh", headers=headers)

        assert response.status_code == 401


class TestLogoutClearsCookies:
    def test_logout_clears_both_auth_cookies(self, client: TestClient) -> None:
        _register(client)
        headers = csrf_headers(client)

        response = client.post("/api/v1/auth/logout", headers=headers)

        assert response.status_code == 204
        access_cookie = _set_cookie_for(response, "access_token")
        refresh_cookie = _set_cookie_for(response, "refresh_token")
        # Starlette's delete_cookie sets an empty value with Max-Age=0
        # (and `expires` set to "now"), which every browser treats as
        # "delete this cookie immediately" — not literally a 1970 date.
        assert 'access_token=""' in access_cookie
        assert "Max-Age=0" in access_cookie
        assert 'refresh_token=""' in refresh_cookie
        assert "Max-Age=0" in refresh_cookie

    def test_requests_after_logout_are_no_longer_authenticated(self, client: TestClient) -> None:
        _register(client)
        headers = csrf_headers(client)
        client.post("/api/v1/auth/logout", headers=headers)

        response = client.get("/api/v1/auth/sessions")

        assert response.status_code == 401


class TestCookieOnlyAuthentication:
    def test_authenticated_request_succeeds_using_only_the_cookie(
        self, client: TestClient
    ) -> None:
        _register(client)

        response = client.get("/api/v1/auth/sessions")

        assert response.status_code == 200

    def test_authorization_bearer_header_alone_does_not_authenticate(
        self, client_factory: Callable[[], TestClient]
    ) -> None:
        """Proves the old bearer-token path is fully gone, not just unused:
        a request presenting a syntactically-plausible bearer token but no
        cookie must be rejected exactly like an anonymous request."""
        registrar = client_factory()
        registrar_headers = csrf_headers(registrar)
        registrar.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
            headers=registrar_headers,
        )
        stolen_looking_token = registrar.cookies.get("access_token")
        assert stolen_looking_token is not None

        bare_client = client_factory()
        response = bare_client.get(
            "/api/v1/auth/sessions",
            headers={"Authorization": f"Bearer {stolen_looking_token}"},
        )

        assert response.status_code == 401

    def test_bearer_header_does_not_satisfy_csrf_either(
        self, client_factory: Callable[[], TestClient]
    ) -> None:
        registrar = client_factory()
        registrar_headers = csrf_headers(registrar)
        registrar.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
            headers=registrar_headers,
        )
        access_token = registrar.cookies.get("access_token")

        response = registrar.post(
            "/api/v1/workspaces",
            json={"name": "Bearer-only workspace"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_error"


class TestCorsBehavior:
    def test_preflight_from_allowed_origin_returns_access_control_headers(
        self, client: TestClient
    ) -> None:
        response = client.options(
            "/api/v1/workspaces",
            headers={
                "Origin": _ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type, x-csrf-token",
            },
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_from_disallowed_origin_gets_no_allow_origin_header(
        self, client: TestClient
    ) -> None:
        """A real browser would refuse to send the actual follow-up request
        (or would block reading its response) if this header is absent for
        its origin — this is the mechanism that stops a malicious
        cross-origin site from completing a state-changing request."""
        response = client.options(
            "/api/v1/workspaces",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type, x-csrf-token",
            },
        )

        assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"

    def test_cors_headers_present_even_on_a_csrf_rejection(self, client: TestClient) -> None:
        """Verifies the middleware ordering (app/main.py): CORSMiddleware
        must be outermost so its headers still land on an error response
        raised by CSRFMiddleware further in."""
        response = client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
            headers={"Origin": _ALLOWED_ORIGIN},
        )

        assert response.status_code == 403
        assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN

    def test_cors_headers_present_on_an_auth_rejection(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/auth/sessions",
            headers={"Origin": _ALLOWED_ORIGIN},
        )

        assert response.status_code == 401
        assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN
