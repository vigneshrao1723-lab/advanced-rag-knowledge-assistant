from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

_PASSWORD = "correct horse battery staple"


def _register(client: TestClient, email: str, password: str = _PASSWORD) -> dict[str, Any]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def test_register_creates_user_and_returns_tokens(client: TestClient) -> None:
    email = _unique_email()

    body = _register(client, email)

    assert body["user"]["email"] == email
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.post("/api/v1/auth/register", json={"email": email, "password": _PASSWORD})

    assert response.status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": _unique_email(), "password": "short"}
    )

    assert response.status_code == 422


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": _PASSWORD}
    )

    assert response.status_code == 422


def test_login_succeeds_with_correct_credentials(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.post("/api/v1/auth/login", json={"email": email, "password": _PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == email


def test_login_fails_with_wrong_password(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong password"}
    )

    assert response.status_code == 401


def test_login_with_nonexistent_email_gives_same_generic_error_as_wrong_password(
    client: TestClient,
) -> None:
    """Resists user enumeration via the login endpoint: the response for a
    nonexistent account must be indistinguishable from a wrong password."""
    email = _unique_email()
    _register(client, email)

    wrong_password_response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong password"}
    )
    nonexistent_email_response = client.post(
        "/api/v1/auth/login", json={"email": _unique_email(), "password": _PASSWORD}
    )

    assert wrong_password_response.status_code == nonexistent_email_response.status_code == 401
    assert (
        wrong_password_response.json()["error"]["message"]
        == nonexistent_email_response.json()["error"]["message"]
    )


def test_refresh_rotates_token_and_invalidates_old_one(client: TestClient) -> None:
    tokens = _register(client, _unique_email())

    refreshed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    reused_old_token = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused_old_token.status_code == 401


def test_refresh_with_malformed_token_fails(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})

    assert response.status_code == 401


def test_reuse_of_rotated_refresh_token_revokes_the_session(client: TestClient) -> None:
    tokens = _register(client, _unique_email())
    original_refresh_token = tokens["refresh_token"]

    # Rotate once (legitimate use).
    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original_refresh_token}
    )
    assert rotated.status_code == 200
    new_refresh_token = rotated.json()["refresh_token"]

    # Reuse of the rotated-out token: session must be revoked entirely.
    reuse_attempt = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original_refresh_token}
    )
    assert reuse_attempt.status_code == 401

    # Even the legitimately-rotated token must now fail — the whole
    # session was revoked, not just the stale token rejected.
    now_also_fails = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_refresh_token}
    )
    assert now_also_fails.status_code == 401


def test_logout_revokes_session_so_refresh_no_longer_works(client: TestClient) -> None:
    tokens = _register(client, _unique_email())

    logout_response = client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout_response.status_code == 204

    refresh_after_logout = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_after_logout.status_code == 401


def test_logout_with_malformed_token_does_not_error(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "garbage"})

    assert response.status_code == 204


def test_get_current_user_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401


def test_get_current_user_returns_profile_with_valid_token(client: TestClient) -> None:
    email = _unique_email()
    tokens = _register(client, email)

    response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == email


def test_garbage_access_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


def test_list_sessions_flags_the_current_session(client: TestClient) -> None:
    tokens = _register(client, _unique_email())
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = client.get("/api/v1/auth/sessions", headers=headers)

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True


def test_revoke_session_by_id(client: TestClient) -> None:
    tokens = _register(client, _unique_email())
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    session_id = client.get("/api/v1/auth/sessions", headers=headers).json()[0]["id"]

    response = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)

    assert response.status_code == 204
    refresh_after_revoke = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_after_revoke.status_code == 401


def test_cannot_revoke_another_users_session(client: TestClient) -> None:
    user_a_tokens = _register(client, _unique_email())
    user_b_tokens = _register(client, _unique_email())
    user_b_session_id = client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {user_b_tokens['access_token']}"},
    ).json()[0]["id"]

    response = client.delete(
        f"/api/v1/auth/sessions/{user_b_session_id}",
        headers={"Authorization": f"Bearer {user_a_tokens['access_token']}"},
    )

    # Same 404 as a nonexistent session — never confirms another user's
    # session IDs exist.
    assert response.status_code == 404


def test_login_is_rate_limited(client: TestClient) -> None:
    email = _unique_email()
    _register(client, email)

    responses = [
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_register_is_rate_limited(client: TestClient) -> None:
    responses = [
        client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
        )
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_refresh_is_rate_limited(client: TestClient) -> None:
    tokens = _register(client, _unique_email())

    responses = [
        client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        for _ in range(21)
    ]

    assert responses[-1].status_code == 429
