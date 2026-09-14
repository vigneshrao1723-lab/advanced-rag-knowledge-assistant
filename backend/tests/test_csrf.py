from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def test_safe_methods_do_not_require_a_csrf_token(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_first_response_sets_a_csrf_cookie(client: TestClient) -> None:
    response = client.get("/api/v1/auth/csrf")

    assert response.status_code == 204
    assert client.cookies.get("csrf_token") is not None


def test_legitimate_request_with_matching_cookie_and_header_succeeds(client: TestClient) -> None:
    headers = csrf_headers(client)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": _PASSWORD},
        headers=headers,
    )

    assert response.status_code == 201


def test_state_changing_request_without_any_csrf_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": _PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_error"


def test_state_changing_request_with_header_but_no_cookie_is_rejected(client: TestClient) -> None:
    """A cross-site attacker can make the browser send a forged request,
    but cannot read the victim's csrf cookie to also set a matching
    header — so a header alone (no matching cookie) must fail."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": _PASSWORD},
        headers={"X-CSRF-Token": "attacker-supplied-value"},
    )

    assert response.status_code == 403


def test_state_changing_request_with_mismatched_token_is_rejected(client: TestClient) -> None:
    client.get("/api/v1/auth/csrf")
    assert client.cookies.get("csrf_token") is not None

    response = client.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": _PASSWORD},
        headers={"X-CSRF-Token": "does-not-match-the-cookie"},
    )

    assert response.status_code == 403


def test_login_itself_requires_a_valid_csrf_token(client: TestClient) -> None:
    """Login is a state change (creates a session) — skipping CSRF here
    would allow "login CSRF" (forcing a victim into an attacker's
    account)."""
    email = _unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
    )

    assert response.status_code == 403


def test_workspace_creation_requires_a_valid_csrf_token(client: TestClient) -> None:
    email = _unique_email()
    headers = csrf_headers(client)
    client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD}, headers=headers
    )

    response = client.post("/api/v1/workspaces", json={"name": "No CSRF"})

    assert response.status_code == 403


def test_csrf_token_is_not_accepted_from_a_different_clients_cookie(
    client_factory: Callable[[], TestClient],
) -> None:
    """An attacker's own valid CSRF token (from their own session) must not
    let them forge a request that rides on a *different* victim's cookies
    — the double-submit check only ever compares a single request's own
    cookie against its own header, so this is really confirming there's no
    global/shared token that would make that possible."""
    victim = client_factory()
    attacker = client_factory()
    victim_headers = csrf_headers(victim)
    attacker_headers = csrf_headers(attacker)

    assert victim_headers != attacker_headers

    response = victim.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": _PASSWORD},
        headers=attacker_headers,  # wrong token for this cookie jar
    )

    assert response.status_code == 403
