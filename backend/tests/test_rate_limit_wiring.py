"""HTTP-level tests for implementation slice 2: `enforce_*_rate_limit`
actually calling the Redis-backed engine (ADR 0006 §6, §13), not just the
engine in isolation (`test_redis_rate_limiter.py`) or the fallback limiter
in isolation (`test_rate_limit.py`).

Every existing `test_auth.py`/`test_password_reset.py` rate-limit
assertion continues to pass unmodified against whichever path (Redis or
fallback) is actually live in this environment — this file adds the
tests that specifically distinguish the two paths and verify the ADR
§13 failure policy end-to-end.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.cookies import REFRESH_TOKEN_COOKIE
from app.core.redis_client import build_redis_client, get_redis_client
from app.core.redis_keys import hash_account_identifier, rate_limit_key
from app.core.security import parse_refresh_token
from tests.conftest import csrf_headers
from tests.test_auth import _PASSWORD, _register, _unique_email


@pytest.fixture
def unreachable_redis_client() -> Iterator[redis.Redis]:
    """A `redis.Redis` pointed at a connection that will refuse/time out
    quickly — used to override `get_redis_client` and force the "Redis
    configured but unreachable" path (ADR 0006 §13), independent of
    whether this environment has a real Redis available."""
    client = build_redis_client(
        "redis://localhost:1/0", socket_timeout=0.05, socket_connect_timeout=0.05
    )
    yield client
    client.close()


def test_successful_login_creates_the_redis_ip_and_account_dimension_keys(
    client: TestClient,
) -> None:
    """Proves the wiring actually reaches Redis (not just the fallback
    limiter) and uses the HMAC account identifier design (ADR §14), not
    a raw email."""
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    email = _unique_email()
    _register(client, email)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200

    settings = get_settings()
    expected_account_hash = hash_account_identifier(
        email, key=settings.rate_limit_hash_key_resolved.encode("utf-8")
    )
    ip_key = rate_limit_key("login", "ip", "testclient")
    acct_key = rate_limit_key("login", "acct", expected_account_hash)

    assert redis_client.exists(ip_key) == 1
    assert redis_client.exists(acct_key) == 1
    # The raw email must never appear in the Redis key.
    assert email not in acct_key


def test_redis_unavailable_falls_back_to_fixed_window_for_login(
    app: FastAPI,
    client_factory: Callable[[], TestClient],
    unreachable_redis_client: redis.Redis,
) -> None:
    """Tier A (ADR §13): a genuinely unreachable Redis falls back to the
    existing `FixedWindowRateLimiter` — login stays rate-limited at the
    same threshold, not unlimited."""
    app.dependency_overrides[get_redis_client] = lambda: unreachable_redis_client
    test_client = client_factory()

    email = _unique_email()
    _register(test_client, email)
    headers = csrf_headers(test_client)

    responses = [
        test_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong"}, headers=headers
        )
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_redis_unavailable_fails_open_for_register(
    app: FastAPI,
    client_factory: Callable[[], TestClient],
    unreachable_redis_client: redis.Redis,
) -> None:
    """Tier B (ADR §13): `register` fails open on a genuine Redis outage
    — more attempts than the base limit (5) must all still succeed,
    unlike every Tier A endpoint."""
    app.dependency_overrides[get_redis_client] = lambda: unreachable_redis_client
    test_client = client_factory()
    headers = csrf_headers(test_client)

    responses = [
        test_client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
            headers=headers,
        )
        for _ in range(8)
    ]

    assert all(response.status_code == 201 for response in responses), [
        r.status_code for r in responses
    ]


def test_redis_configured_but_none_still_uses_fallback_for_register(
    app: FastAPI,
    client_factory: Callable[[], TestClient],
) -> None:
    """The "never configured" case (ADR §13's implementation note in
    `rate_limit.py`'s module docstring) must still rate-limit `register`
    — Tier B's fail-open behavior is reserved for a genuine mid-request
    outage, not the default unconfigured state."""
    app.dependency_overrides[get_redis_client] = lambda: None
    test_client = client_factory()
    headers = csrf_headers(test_client)

    responses = [
        test_client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
            headers=headers,
        )
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_spoofed_forwarded_for_header_does_not_bypass_the_ip_dimension(
    client: TestClient,
) -> None:
    """ADR §9a: with `TRUSTED_PROXY_CIDRS` unset (the default), a
    client-supplied `X-Forwarded-For` must be ignored entirely — varying
    it on every request must not let an attacker escape the IP-keyed
    bucket by claiming a different IP each time."""
    email = _unique_email()
    _register(client, email)
    headers = csrf_headers(client)

    responses = [
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong"},
            headers={**headers, "X-Forwarded-For": f"10.0.0.{i}"},
        )
        for i in range(6)
    ]

    # If the header were honored, each request would land in its own
    # bucket and none would be rejected. It must still be exactly the
    # same as the un-spoofed case (test_login_is_rate_limited): the 6th
    # request is rejected because every request shared one bucket.
    assert responses[-1].status_code == 429


# --- refresh: Redis wiring -----------------------------------------------


def test_successful_refresh_creates_the_redis_ip_and_session_dimension_keys(
    client: TestClient,
) -> None:
    """Proves refresh's Redis wiring creates both dimensions, and that
    the session key contains only the (already non-secret) session
    identifier — never the refresh token's high-entropy secret half,
    which must never reach Redis at all."""
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    email = _unique_email()
    _register(client, email)

    raw_refresh_token = client.cookies.get(REFRESH_TOKEN_COOKIE)
    assert raw_refresh_token is not None
    parsed = parse_refresh_token(raw_refresh_token)
    assert parsed is not None
    session_id, secret = parsed

    response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert response.status_code == 200

    ip_key = rate_limit_key("refresh", "ip", "testclient")
    session_key = rate_limit_key("refresh", "session", str(session_id))

    assert redis_client.exists(ip_key) == 1
    assert redis_client.exists(session_key) == 1
    # The refresh token's high-entropy secret half must never appear in
    # any Redis key — only the session ID, which the API already exposes
    # non-secretly via GET /api/v1/auth/sessions.
    assert secret not in session_key


# --- forgot-password: Redis wiring ----------------------------------------


def test_successful_forgot_password_creates_the_redis_ip_and_account_dimension_keys(
    client: TestClient,
) -> None:
    """Mirrors the login test above for forgot-password's own dimension
    construction (IP + HMAC account), which is otherwise untested at the
    HTTP/Redis-wiring level."""
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    email = _unique_email()
    _register(client, email)

    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": email},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200

    settings = get_settings()
    expected_account_hash = hash_account_identifier(
        email, key=settings.rate_limit_hash_key_resolved.encode("utf-8")
    )
    ip_key = rate_limit_key("forgot-password", "ip", "testclient")
    acct_key = rate_limit_key("forgot-password", "acct", expected_account_hash)

    assert redis_client.exists(ip_key) == 1
    assert redis_client.exists(acct_key) == 1
    assert email not in acct_key


# --- reset-password: Redis wiring -----------------------------------------


def test_reset_password_creates_only_the_redis_ip_dimension(
    client: TestClient,
) -> None:
    """ADR §9: reset-password is IP-only — the token's own 256-bit
    entropy is the real defense, so no account or session dimension
    should ever exist for this operation, regardless of whether the
    submitted token is valid (rate limiting runs before token
    validation)."""
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "garbage", "new_password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 400  # invalid token — rate limiting still ran first

    ip_key = rate_limit_key("reset-password", "ip", "testclient")
    assert redis_client.exists(ip_key) == 1
    assert list(redis_client.scan_iter(match="rl:reset-password:acct:*")) == []
    assert list(redis_client.scan_iter(match="rl:reset-password:session:*")) == []


# --- Tier A fallback: refresh / forgot-password / reset-password ----------


def test_redis_unavailable_falls_back_to_fixed_window_for_refresh(
    app: FastAPI,
    client_factory: Callable[[], TestClient],
    unreachable_redis_client: redis.Redis,
) -> None:
    """Tier A (ADR §13): refresh falls back to `FixedWindowRateLimiter`,
    keyed by IP — the fallback's own key, used regardless of whether a
    session dimension would otherwise have applied."""
    app.dependency_overrides[get_redis_client] = lambda: unreachable_redis_client
    test_client = client_factory()
    headers = csrf_headers(test_client)

    responses = [test_client.post("/api/v1/auth/refresh", headers=headers) for _ in range(21)]

    assert responses[-1].status_code == 429


def test_redis_unavailable_falls_back_to_fixed_window_for_forgot_password(
    app: FastAPI,
    client_factory: Callable[[], TestClient],
    unreachable_redis_client: redis.Redis,
) -> None:
    """Tier A (ADR §13): forgot-password falls back to
    `FixedWindowRateLimiter` at the same threshold, not unlimited."""
    app.dependency_overrides[get_redis_client] = lambda: unreachable_redis_client
    test_client = client_factory()
    headers = csrf_headers(test_client)

    responses = [
        test_client.post(
            "/api/v1/auth/forgot-password", json={"email": _unique_email()}, headers=headers
        )
        for _ in range(6)
    ]

    assert responses[-1].status_code == 429


def test_redis_unavailable_falls_back_to_fixed_window_for_reset_password(
    app: FastAPI,
    client_factory: Callable[[], TestClient],
    unreachable_redis_client: redis.Redis,
) -> None:
    """Tier A (ADR §13): reset-password falls back to
    `FixedWindowRateLimiter` at the same threshold, not unlimited."""
    app.dependency_overrides[get_redis_client] = lambda: unreachable_redis_client
    test_client = client_factory()
    headers = csrf_headers(test_client)

    responses = [
        test_client.post(
            "/api/v1/auth/reset-password",
            json={"token": "garbage", "new_password": _PASSWORD},
            headers=headers,
        )
        for _ in range(11)
    ]

    assert responses[-1].status_code == 429


# --- multi-dimension endpoint atomicity / cross-user isolation ------------


def test_login_endpoint_rejection_never_partially_consumes_the_ip_dimension(
    app: FastAPI,
) -> None:
    """Endpoint-level regression test for the atomicity flaw ADR 0006's
    adversarial review found and corrected (§10): proves
    `enforce_login_rate_limit` supplies both dimensions to ONE
    `check_all()` invocation, not two separate checks. If it did the
    latter, a losing request's IP bucket would be consumed before the
    account check rejected it — exactly the partial-consumption bug this
    design exists to prevent. `test_redis_rate_limiter.py` (Slice 1,
    already merged) proves the underlying Lua engine's atomicity in
    isolation; this test proves the endpoint actually wires both
    dimensions into that engine correctly, not just that the engine
    itself is correct.

    Uses `TestClient(app, client=(ip, port))` to get two genuinely
    different peer IPs — the default `client`/`client_factory` fixtures
    always report the same fixed "testclient" peer, which can't
    distinguish an IP-dimension bug from an account-dimension one.
    """
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    ip_a = "203.0.113.10"
    ip_b = "203.0.113.20"
    client_a = TestClient(app, client=(ip_a, 12345))
    client_b = TestClient(app, client=(ip_b, 12345))
    try:
        email = _unique_email()
        _register(client_a, email)

        headers_a = csrf_headers(client_a)
        # Exhaust the account bucket (capacity 5) with wrong-password
        # attempts from ip_a — this also exhausts ip_a's own bucket,
        # which is irrelevant: ip_a is not under test below.
        for _ in range(5):
            response = client_a.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong"},
                headers=headers_a,
            )
            assert response.status_code == 401

        ip_b_key = rate_limit_key("login", "ip", ip_b)
        assert redis_client.exists(ip_b_key) == 0

        headers_b = csrf_headers(client_b)
        rejected = client_b.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong"},
            headers=headers_b,
        )

        assert rejected.status_code == 429
        # The account dimension rejected this request — ip_b's own
        # bucket, which had full capacity, must never have been touched.
        assert redis_client.exists(ip_b_key) == 0
    finally:
        client_a.close()
        client_b.close()


def test_one_accounts_failed_logins_do_not_throttle_a_different_account(
    app: FastAPI,
) -> None:
    """Cross-user isolation: account A's exhausted bucket must never
    affect account B's own, independent account-dimension bucket (ADR
    §14's per-account HMAC keying guarantees distinct keys; this proves
    it holds through the real endpoint, not just at the hash-construction
    unit level in `test_redis_keys.py`). Uses distinct IPs for each
    account specifically so the *shared* IP dimension cannot confound the
    result — this test is about account-dimension isolation, not IP
    isolation, which is a different, already-covered property.
    """
    ip_a = "203.0.113.30"
    ip_b = "203.0.113.40"
    client_a = TestClient(app, client=(ip_a, 12345))
    client_b = TestClient(app, client=(ip_b, 12345))
    try:
        email_a = _unique_email()
        email_b = _unique_email()
        _register(client_a, email_a)
        _register(client_b, email_b)

        headers_a = csrf_headers(client_a)
        for _ in range(5):
            response = client_a.post(
                "/api/v1/auth/login",
                json={"email": email_a, "password": "wrong"},
                headers=headers_a,
            )
            assert response.status_code == 401
        exhausted = client_a.post(
            "/api/v1/auth/login",
            json={"email": email_a, "password": "wrong"},
            headers=headers_a,
        )
        assert exhausted.status_code == 429

        # Account B, on a different IP, must be entirely unaffected by
        # account A's exhausted bucket.
        headers_b = csrf_headers(client_b)
        response_b = client_b.post(
            "/api/v1/auth/login",
            json={"email": email_b, "password": _PASSWORD},
            headers=headers_b,
        )
        assert response_b.status_code == 200
    finally:
        client_a.close()
        client_b.close()
