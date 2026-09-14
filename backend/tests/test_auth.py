from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"


def _register(client: TestClient, email: str, password: str = _PASSWORD) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def test_register_sets_httponly_auth_cookies_and_returns_only_the_user(
    client: TestClient,
) -> None:
    email = _unique_email()

    body = _register(client, email)

    assert body == {"user": body["user"]}  # no access_token/refresh_token in the body
    assert body["user"]["email"] == email
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert client.cookies.get("access_token") is not None
    assert client.cookies.get("refresh_token") is not None


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )

    assert response.status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": _unique_email(), "password": "short"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": _PASSWORD},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422


def test_login_succeeds_with_correct_credentials(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == email


def test_login_fails_with_wrong_password(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong password"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 401


def test_login_with_nonexistent_email_gives_same_generic_error_as_wrong_password(
    client: TestClient,
) -> None:
    """Resists user enumeration via the login endpoint: the response for a
    nonexistent account must be indistinguishable from a wrong password."""
    email = _unique_email()
    _register(client, email)
    headers = csrf_headers(client)

    wrong_password_response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong password"}, headers=headers
    )
    nonexistent_email_response = client.post(
        "/api/v1/auth/login",
        json={"email": _unique_email(), "password": _PASSWORD},
        headers=headers,
    )

    assert wrong_password_response.status_code == nonexistent_email_response.status_code == 401
    assert (
        wrong_password_response.json()["error"]["message"]
        == nonexistent_email_response.json()["error"]["message"]
    )


def test_refresh_rotates_cookie_and_invalidates_old_one(client: TestClient) -> None:
    _register(client, _unique_email())
    headers = csrf_headers(client)
    old_refresh_cookie = client.cookies.get("refresh_token")
    assert old_refresh_cookie is not None

    refreshed = client.post("/api/v1/auth/refresh", headers=headers)
    assert refreshed.status_code == 200
    new_refresh_cookie = client.cookies.get("refresh_token")
    assert new_refresh_cookie != old_refresh_cookie

    # Simulate presenting the stale, pre-rotation cookie again.
    client.cookies.set("refresh_token", old_refresh_cookie)
    reused_old_cookie = client.post("/api/v1/auth/refresh", headers=headers)
    assert reused_old_cookie.status_code == 401


def test_refresh_without_a_cookie_fails(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))

    assert response.status_code == 401


def test_refresh_with_malformed_cookie_fails(client: TestClient) -> None:
    headers = csrf_headers(client)
    client.cookies.set("refresh_token", "not-a-real-token")

    response = client.post("/api/v1/auth/refresh", headers=headers)

    assert response.status_code == 401


def test_reuse_of_rotated_refresh_cookie_revokes_the_session(client: TestClient) -> None:
    _register(client, _unique_email())
    headers = csrf_headers(client)
    original_refresh_cookie = client.cookies.get("refresh_token")

    rotated = client.post("/api/v1/auth/refresh", headers=headers)
    assert rotated.status_code == 200
    new_refresh_cookie = client.cookies.get("refresh_token")

    client.cookies.set("refresh_token", original_refresh_cookie)
    reuse_attempt = client.post("/api/v1/auth/refresh", headers=headers)
    assert reuse_attempt.status_code == 401

    # Even the legitimately-rotated cookie must now fail — the whole
    # session was revoked, not just the stale cookie rejected.
    client.cookies.set("refresh_token", new_refresh_cookie)
    now_also_fails = client.post("/api/v1/auth/refresh", headers=headers)
    assert now_also_fails.status_code == 401


def test_logout_revokes_session_and_clears_cookies(client: TestClient) -> None:
    _register(client, _unique_email())
    headers = csrf_headers(client)

    logout_response = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 204

    refresh_after_logout = client.post("/api/v1/auth/refresh", headers=headers)
    assert refresh_after_logout.status_code == 401


def test_logout_without_a_cookie_still_succeeds(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    assert response.status_code == 204


def test_get_current_user_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401


def test_get_current_user_returns_profile_with_valid_cookie(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["email"] == email


def test_garbage_access_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set("access_token", "not-a-real-token")

    response = client.get("/api/v1/users/me")

    assert response.status_code == 401


def test_list_sessions_flags_the_current_session(client: TestClient) -> None:
    _register(client, _unique_email())

    response = client.get("/api/v1/auth/sessions")

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True


def test_revoke_session_by_id(client: TestClient) -> None:
    _register(client, _unique_email())
    headers = csrf_headers(client)
    session_id = client.get("/api/v1/auth/sessions").json()[0]["id"]

    response = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)

    assert response.status_code == 204
    refresh_after_revoke = client.post("/api/v1/auth/refresh", headers=headers)
    assert refresh_after_revoke.status_code == 401


def test_cannot_revoke_another_users_session(
    client_factory: Callable[[], TestClient],
) -> None:
    user_a = client_factory()
    user_b = client_factory()
    _register(user_a, _unique_email())
    _register(user_b, _unique_email())
    user_b_session_id = user_b.get("/api/v1/auth/sessions").json()[0]["id"]

    response = user_a.delete(
        f"/api/v1/auth/sessions/{user_b_session_id}", headers=csrf_headers(user_a)
    )

    # Same 404 as a nonexistent session — never confirms another user's
    # session IDs exist.
    assert response.status_code == 404


def test_login_is_rate_limited(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)
    headers = csrf_headers(client)

    responses = [
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong"}, headers=headers
        )
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_register_is_rate_limited(client: TestClient) -> None:
    headers = csrf_headers(client)

    responses = [
        client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
            headers=headers,
        )
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_refresh_is_rate_limited(client: TestClient) -> None:
    _register(client, _unique_email())
    headers = csrf_headers(client)

    responses = [client.post("/api/v1/auth/refresh", headers=headers) for _ in range(21)]

    assert responses[-1].status_code == 429
