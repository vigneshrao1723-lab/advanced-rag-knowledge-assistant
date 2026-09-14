from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.core.security import hash_password_reset_token
from app.repositories import password_reset_token_repository, user_repository
from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"
_NEW_PASSWORD = "a brand new stronger password"
_RESET_LINK_RE = re.compile(r"reset-password\?token=(\S+)")


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def _register(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text


def _extract_reset_token(printed_output: str) -> str:
    match = _RESET_LINK_RE.search(printed_output)
    assert match is not None, f"no reset link found in captured output: {printed_output!r}"
    return match.group(1)


def test_forgot_password_returns_generic_message_for_existing_email(
    client: TestClient,
) -> None:
    email = _unique_email()
    _register(client, email)

    response = client.post(
        "/api/v1/auth/forgot-password", json={"email": email}, headers=csrf_headers(client)
    )

    assert response.status_code == 200
    assert "if an account with that email exists" in response.json()["message"].lower()


def test_forgot_password_returns_the_same_generic_message_for_an_unknown_email(
    client: TestClient,
) -> None:
    known_email = _unique_email()
    _register(client, known_email)
    headers = csrf_headers(client)

    known_response = client.post(
        "/api/v1/auth/forgot-password", json={"email": known_email}, headers=headers
    )
    unknown_response = client.post(
        "/api/v1/auth/forgot-password", json={"email": _unique_email()}, headers=headers
    )

    assert known_response.status_code == unknown_response.status_code == 200
    assert known_response.json() == unknown_response.json()


def test_forgot_password_for_unknown_email_sends_no_email(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    client.post(
        "/api/v1/auth/forgot-password",
        json={"email": _unique_email()},
        headers=csrf_headers(client),
    )

    assert "EMAIL" not in capsys.readouterr().out


def test_full_password_reset_flow(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    email = _unique_email()
    _register(client, email)
    headers = csrf_headers(client)

    client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=headers)
    raw_token = _extract_reset_token(capsys.readouterr().out)

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": _NEW_PASSWORD},
        headers=headers,
    )
    assert reset_response.status_code == 204

    old_password_login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}, headers=headers
    )
    assert old_password_login.status_code == 401

    new_password_login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": _NEW_PASSWORD}, headers=headers
    )
    assert new_password_login.status_code == 200


def test_password_reset_invalidates_existing_sessions(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    email = _unique_email()
    _register(client, email)
    headers = csrf_headers(client)
    refresh_cookie_before_reset = client.cookies.get("refresh_token")

    client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=headers)
    raw_token = _extract_reset_token(capsys.readouterr().out)
    client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": _NEW_PASSWORD},
        headers=headers,
    )

    client.cookies.set("refresh_token", refresh_cookie_before_reset)
    refresh_with_old_session = client.post("/api/v1/auth/refresh", headers=headers)

    assert refresh_with_old_session.status_code == 401


def test_reset_token_is_single_use(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    email = _unique_email()
    _register(client, email)
    headers = csrf_headers(client)

    client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=headers)
    raw_token = _extract_reset_token(capsys.readouterr().out)

    first_attempt = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": _NEW_PASSWORD},
        headers=headers,
    )
    assert first_attempt.status_code == 204

    second_attempt = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "yet-another-password"},
        headers=headers,
    )
    assert second_attempt.status_code == 400
    assert second_attempt.json()["error"]["code"] == "reset_token_already_used"


def test_reset_with_invalid_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": _NEW_PASSWORD},
        headers=csrf_headers(client),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "reset_token_invalid"


def test_reset_with_expired_token_is_rejected(
    client: TestClient, db_session: DbSession
) -> None:
    email = _unique_email()
    _register(client, email)
    user = user_repository.get_by_email(db_session, email)
    assert user is not None

    raw_token = "expired-token-value-for-testing"
    password_reset_token_repository.create(
        db_session,
        user_id=user.id,
        token_hash=hash_password_reset_token(raw_token),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.commit()

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": _NEW_PASSWORD},
        headers=csrf_headers(client),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "reset_token_expired"


def test_forgot_password_is_rate_limited(client: TestClient) -> None:
    headers = csrf_headers(client)

    responses = [
        client.post(
            "/api/v1/auth/forgot-password", json={"email": _unique_email()}, headers=headers
        )
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_reset_password_is_rate_limited(client: TestClient) -> None:
    headers = csrf_headers(client)

    responses = [
        client.post(
            "/api/v1/auth/reset-password",
            json={"token": "garbage", "new_password": _NEW_PASSWORD},
            headers=headers,
        )
        for _ in range(11)
    ]

    assert responses[-1].status_code == 429


def test_forgot_password_without_csrf_token_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/forgot-password", json={"email": _unique_email()})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_error"


def test_forgot_password_with_mismatched_csrf_token_is_rejected(client: TestClient) -> None:
    client.get("/api/v1/auth/csrf")

    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": _unique_email()},
        headers={"X-CSRF-Token": "does-not-match-the-cookie"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_error"


def test_reset_password_without_csrf_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "irrelevant", "new_password": _NEW_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_error"


def test_reset_password_with_mismatched_csrf_token_is_rejected(client: TestClient) -> None:
    client.get("/api/v1/auth/csrf")

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "irrelevant", "new_password": _NEW_PASSWORD},
        headers={"X-CSRF-Token": "does-not-match-the-cookie"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_error"


def test_reset_token_does_not_affect_other_users(
    client_factory: Callable[[], TestClient], capsys: pytest.CaptureFixture[str]
) -> None:
    """A reset token is bound server-side to the user it was issued for
    (looked up by hash, never by a client-supplied user id) — there is no
    way to present a valid token for user A and change user B's password.
    This proves that structural guarantee end-to-end rather than just by
    inspection of the service code."""
    victim = client_factory()
    other_user = client_factory()
    victim_email = _unique_email()
    other_email = _unique_email()
    _register(victim, victim_email)
    _register(other_user, other_email)

    victim.post(
        "/api/v1/auth/forgot-password", json={"email": victim_email}, headers=csrf_headers(victim)
    )
    raw_token = _extract_reset_token(capsys.readouterr().out)

    reset_response = other_user.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": _NEW_PASSWORD},
        headers=csrf_headers(other_user),
    )
    assert reset_response.status_code == 204

    victim_old_password_login = victim.post(
        "/api/v1/auth/login",
        json={"email": victim_email, "password": _PASSWORD},
        headers=csrf_headers(victim),
    )
    assert victim_old_password_login.status_code == 401

    other_user_old_password_still_works = other_user.post(
        "/api/v1/auth/login",
        json={"email": other_email, "password": _PASSWORD},
        headers=csrf_headers(other_user),
    )
    assert other_user_old_password_still_works.status_code == 200


def test_password_reset_does_not_retroactively_invalidate_an_already_issued_access_token(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Documents the same ADR 0003 tradeoff already covered for logout/
    session-revocation (test_workspaces.py) — access tokens are validated
    without a DB round-trip, so a password reset (like logout) cannot
    retroactively invalidate an already-issued, unexpired access token,
    only its refresh capability. The blast radius is bounded by the
    token's short expiry, not indefinite; a real fix (immediate
    revocation) would require a stateful check on every request, which
    ADR 0003 explicitly trades away for hot-path performance."""
    email = _unique_email()
    _register(client, email)
    headers = csrf_headers(client)
    access_token_before_reset = client.cookies.get("access_token")

    client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=headers)
    raw_token = _extract_reset_token(capsys.readouterr().out)
    client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": _NEW_PASSWORD},
        headers=headers,
    )

    client.cookies.set("access_token", access_token_before_reset)
    still_works = client.get("/api/v1/auth/sessions")
    assert still_works.status_code == 200
