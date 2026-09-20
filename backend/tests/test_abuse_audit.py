"""HTTP-level tests for Slice 3c: abuse-escalation audit emission (ADR
0006 §11/§12/§15) through the real `login`/`forgot-password`/
`reset-password` endpoints.

Real Redis and real PostgreSQL throughout — no mocks, per this project's
established precedent (ADR 0002/0006 §16). Uses the same
`TestClient(app, client=(ip, port))` technique `test_rate_limit_wiring.py`
already established for genuinely distinct peer IPs (the default
`client`/`client_factory` fixtures always report the same fixed
`"testclient"` peer).

**Why most escalation setup below is pre-seeded directly through
`abuse_decision`'s own `record_*` functions, rather than fired purely
through real HTTP calls:** every R1/R2/R4/R5 threshold (10/10/10/15) is
larger than the corresponding base token bucket's own capacity (5 for
`login`/`forgot-password`, 10 for `reset-password`) — the Lua bucket
script always clamps a dimension's effective tokens at its configured
`capacity` regardless of what's stored, so no amount of pre-written
Redis state can let more than `capacity` real requests through within
one window; reaching an abuse threshold through HTTP calls alone would
require waiting out the base bucket's real refill rate (ADR 0006's own
documented ~60s derivation for `login`). Each test therefore pre-seeds
all but the last one or two crossings directly via the exact same
production primitive the endpoint itself calls, then exercises the
*actual* interesting transition — and the endpoint-to-audit wiring
around it — through one or more genuine HTTP requests, comfortably
within the base bucket's own capacity.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.abuse_decision import (
    AbuseContext,
    record_forgot_password_request,
    record_login_failure,
    record_reset_validation_failure,
)
from app.core.abuse_keys import block_key, failcount_key, strict_throttle_key
from app.core.audit import AuditEvent
from app.core.config import get_settings
from app.core.redis_client import get_redis_client
from app.core.redis_keys import hash_account_identifier
from app.models.audit_log import AuditLog
from tests.conftest import csrf_headers
from tests.test_auth import _PASSWORD, _register, _unique_email


def _rate_limit_hash_key() -> bytes:
    return get_settings().rate_limit_hash_key_resolved.encode("utf-8")


def _unique_ip() -> str:
    return f"203.0.{uuid.uuid4().int % 200 + 1}.{uuid.uuid4().int % 200 + 1}"


def _audit_rows(db_session: DbSession, event_type: str) -> list[AuditLog]:
    return list(
        db_session.execute(select(AuditLog).where(AuditLog.event_type == event_type)).scalars()
    )


# --- A: login repeated failures -> R1 STRICT_THROTTLE + RATE_LIMITED audit --


def test_repeated_login_failures_trigger_strict_throttle_with_rate_limited_audit(
    app: FastAPI, db_session: DbSession
) -> None:
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    ip = _unique_ip()
    # 9 of R1's 10 failures, each against a distinct throwaway account so
    # R2 never co-escalates (see module docstring for why this can't be
    # done through 10 real HTTP calls).
    for _ in range(9):
        record_login_failure(
            redis_client, AbuseContext(operation="login", ip=ip, account_hash=uuid.uuid4().hex)
        )
    assert redis_client.exists(strict_throttle_key("login", "ip", ip)) == 0

    test_client = TestClient(app, client=(ip, 12345))
    try:
        headers = csrf_headers(test_client)

        # The 10th failure, through the real endpoint — the actual
        # transition the endpoint-to-audit wiring is tested on.
        response = test_client.post(
            "/api/v1/auth/login",
            json={"email": _unique_email(), "password": "wrong-password"},
            headers=headers,
        )
        assert response.status_code == 401

        assert redis_client.exists(strict_throttle_key("login", "ip", ip)) == 1

        rows = _audit_rows(db_session, AuditEvent.RATE_LIMITED)
        assert len(rows) == 1
        row = rows[0]
        assert row.ip_address == ip
        assert row.user_id is None  # never invented — genuinely unavailable here
        assert row.event_metadata == {"rule": "R1", "operation": "login", "dimension": "ip"}
        assert "wrong-password" not in str(row.event_metadata)

        # The strict bucket (capacity 2) actually gets consulted by
        # check() and folded into check_all() — two more requests pass
        # (spending its 2 tokens), the third is rejected outright.
        allowed_1 = test_client.post(
            "/api/v1/auth/login",
            json={"email": _unique_email(), "password": "wrong-password"},
            headers=headers,
        )
        allowed_2 = test_client.post(
            "/api/v1/auth/login",
            json={"email": _unique_email(), "password": "wrong-password"},
            headers=headers,
        )
        blocked = test_client.post(
            "/api/v1/auth/login",
            json={"email": _unique_email(), "password": "wrong-password"},
            headers=headers,
        )
        assert allowed_1.status_code == 401
        assert allowed_2.status_code == 401
        assert blocked.status_code == 429

        # No duplicate RATE_LIMITED rows from the repeat crossings above.
        assert len(_audit_rows(db_session, AuditEvent.RATE_LIMITED)) == 1
    finally:
        test_client.close()


# --- B: account-based (R2) login abuse through the endpoint -----------------


def test_repeated_login_failures_against_one_account_trigger_r2_with_isolation(
    app: FastAPI, db_session: DbSession
) -> None:
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    victim_email = _unique_email()
    victim_hash = hash_account_identifier(victim_email, key=_rate_limit_hash_key())

    # 9 of R2's 10 failures, cycling through only 2 IPs (well under R3's
    # distinct-IP threshold of 5) so only R2 escalates below.
    setup_ips = [_unique_ip(), _unique_ip()]
    for i in range(9):
        record_login_failure(
            redis_client,
            AbuseContext(operation="login", ip=setup_ips[i % 2], account_hash=victim_hash),
        )
    assert redis_client.exists(strict_throttle_key("login", "acct", victim_hash)) == 0

    ip = _unique_ip()
    victim_client = TestClient(app, client=(ip, 12345))
    try:
        _register(victim_client, victim_email)
        headers = csrf_headers(victim_client)

        response = victim_client.post(
            "/api/v1/auth/login",
            json={"email": victim_email, "password": "wrong-password"},
            headers=headers,
        )
        assert response.status_code == 401

        assert redis_client.exists(strict_throttle_key("login", "acct", victim_hash)) == 1

        acct_rows = [
            row
            for row in _audit_rows(db_session, AuditEvent.RATE_LIMITED)
            if row.event_metadata is not None and row.event_metadata.get("dimension") == "acct"
        ]
        assert len(acct_rows) == 1
        acct_metadata = acct_rows[0].event_metadata
        assert acct_metadata is not None
        assert acct_metadata["rule"] == "R2"
        assert acct_metadata["account_hash"] == victim_hash
        assert victim_email not in str(acct_metadata)
    finally:
        victim_client.close()

    # Account isolation: an unrelated account, attacked from a different
    # IP, must show no escalation at all.
    other_ip = _unique_ip()
    other_client = TestClient(app, client=(other_ip, 12345))
    try:
        other_email = _unique_email()
        _register(other_client, other_email)
        other_hash = hash_account_identifier(other_email, key=_rate_limit_hash_key())
        assert redis_client.exists(strict_throttle_key("login", "acct", other_hash)) == 0
    finally:
        other_client.close()


# --- C: R3 distinct-IP temporary block --------------------------------------


def test_distinct_ips_against_one_account_trigger_temporary_block(
    app: FastAPI, db_session: DbSession
) -> None:
    setup_client = TestClient(app, client=(_unique_ip(), 12345))
    try:
        victim_email = _unique_email()
        _register(setup_client, victim_email)
    finally:
        setup_client.close()

    victim_hash = hash_account_identifier(victim_email, key=_rate_limit_hash_key())
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    # 5 genuinely distinct IPs, each making exactly one real failed
    # login attempt — well within each IP's own base-bucket capacity, so
    # no pre-seeding is needed for this rule.
    attacker_ips = [_unique_ip() for _ in range(5)]
    for ip in attacker_ips:
        attacker = TestClient(app, client=(ip, 12345))
        try:
            headers = csrf_headers(attacker)
            response = attacker.post(
                "/api/v1/auth/login",
                json={"email": victim_email, "password": "wrong-password"},
                headers=headers,
            )
            assert response.status_code == 401
        finally:
            attacker.close()

    assert redis_client.exists(block_key("login", "acct", victim_hash)) == 1

    block_rows = _audit_rows(db_session, AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED)
    assert len(block_rows) == 1
    row = block_rows[0]
    assert row.user_id is None
    assert row.event_metadata == {
        "rule": "R3",
        "operation": "login",
        "dimension": "acct",
        "account_hash": victim_hash,
        "block_ttl_seconds": 600,
    }
    assert victim_email not in str(row.event_metadata)

    # While blocked, even the correct password must be rejected outright,
    # before auth_service ever runs — no new LOGIN_SUCCEEDED audit row,
    # no duplicate ABUSE_TEMPORARY_BLOCK_APPLIED row.
    sixth_ip = _unique_ip()
    blocked_client = TestClient(app, client=(sixth_ip, 12345))
    try:
        headers = csrf_headers(blocked_client)
        response = blocked_client.post(
            "/api/v1/auth/login",
            json={"email": victim_email, "password": _PASSWORD},
            headers=headers,
        )
        assert response.status_code == 429
    finally:
        blocked_client.close()

    assert len(_audit_rows(db_session, AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED)) == 1
    # No LOGIN_SUCCEEDED row for *this* attempt specifically -- scoped by
    # this test's own unique IP rather than a bare global count, since
    # `audit_logs` is a real, persistent, shared table that may already
    # contain unrelated historical rows from outside this test.
    login_succeeded_from_this_ip = [
        row
        for row in _audit_rows(db_session, AuditEvent.LOGIN_SUCCEEDED)
        if row.ip_address == sixth_ip
    ]
    assert login_succeeded_from_this_ip == []


# --- D: forgot-password R4 strict throttle -----------------------------------


def test_repeated_forgot_password_requests_trigger_strict_throttle_with_audit(
    app: FastAPI, db_session: DbSession
) -> None:
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    ip = _unique_ip()
    test_client = TestClient(app, client=(ip, 12345))
    try:
        headers = csrf_headers(test_client)
        nonexistent_email = _unique_email()

        # First 2 requests genuinely through HTTP — enumeration
        # resistance unaffected while still below threshold.
        for _ in range(2):
            response = test_client.post(
                "/api/v1/auth/forgot-password",
                json={"email": nonexistent_email},
                headers=headers,
            )
            assert response.status_code == 200
            assert "sent" in response.json()["message"].lower()

        # 7 more pre-seeded directly (2 real + 7 seeded = 9, one below
        # R4's threshold of 10).
        for _ in range(7):
            record_forgot_password_request(
                redis_client, AbuseContext(operation="forgot-password", ip=ip)
            )
        assert redis_client.exists(strict_throttle_key("forgot-password", "ip", ip)) == 0

        # The 10th request, through the real endpoint.
        response = test_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": nonexistent_email},
            headers=headers,
        )
        assert response.status_code == 200
        assert "sent" in response.json()["message"].lower()

        assert redis_client.exists(strict_throttle_key("forgot-password", "ip", ip)) == 1

        rows = _audit_rows(db_session, AuditEvent.RATE_LIMITED)
        matching = [
            r for r in rows if r.event_metadata is not None and r.event_metadata.get("rule") == "R4"
        ]
        assert len(matching) == 1
        assert matching[0].ip_address == ip
        assert matching[0].event_metadata == {
            "rule": "R4",
            "operation": "forgot-password",
            "dimension": "ip",
        }
    finally:
        test_client.close()


# --- E: reset-password R5 temporary block ------------------------------------


def test_repeated_reset_password_validation_failures_trigger_temporary_block(
    app: FastAPI, db_session: DbSession
) -> None:
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    ip = _unique_ip()
    test_client = TestClient(app, client=(ip, 12345))
    try:
        headers = csrf_headers(test_client)

        for _ in range(2):
            response = test_client.post(
                "/api/v1/auth/reset-password",
                json={"token": f"not-a-real-token-{uuid.uuid4().hex}", "new_password": _PASSWORD},
                headers=headers,
            )
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "reset_token_invalid"

        # 12 more pre-seeded directly (2 real + 12 seeded = 14, one below
        # R5's threshold of 15).
        for _ in range(12):
            record_reset_validation_failure(
                redis_client, AbuseContext(operation="reset-password", ip=ip)
            )
        assert redis_client.exists(block_key("reset-password", "ip", ip)) == 0

        # The 15th failure, through the real endpoint.
        response = test_client.post(
            "/api/v1/auth/reset-password",
            json={"token": f"not-a-real-token-{uuid.uuid4().hex}", "new_password": _PASSWORD},
            headers=headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "reset_token_invalid"

        assert redis_client.exists(block_key("reset-password", "ip", ip)) == 1

        rows = _audit_rows(db_session, AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED)
        matching = [
            r for r in rows if r.event_metadata is not None and r.event_metadata.get("rule") == "R5"
        ]
        assert len(matching) == 1
        row = matching[0]
        assert row.ip_address == ip
        assert row.user_id is None
        assert row.event_metadata == {
            "rule": "R5",
            "operation": "reset-password",
            "dimension": "ip",
            "block_ttl_seconds": 600,
        }

        # Now blocked outright, regardless of token validity.
        blocked = test_client.post(
            "/api/v1/auth/reset-password",
            json={"token": "irrelevant", "new_password": _PASSWORD},
            headers=headers,
        )
        assert blocked.status_code == 429
        assert len(_audit_rows(db_session, AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED)) == 1
    finally:
        test_client.close()


# --- F: success behavior -----------------------------------------------------


def test_successful_login_resets_r2_r3_but_not_r1_and_emits_no_abuse_audit(
    app: FastAPI, db_session: DbSession
) -> None:
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    ip = _unique_ip()
    test_client = TestClient(app, client=(ip, 12345))
    try:
        email = _unique_email()
        _register(test_client, email)
        headers = csrf_headers(test_client)

        # A few failures, well below every threshold.
        for _ in range(3):
            response = test_client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
                headers=headers,
            )
            assert response.status_code == 401

        account_hash = hash_account_identifier(email, key=_rate_limit_hash_key())
        assert redis_client.exists(failcount_key("login", "acct", account_hash)) == 1
        assert redis_client.exists(failcount_key("login", "ip", ip)) == 1

        success = test_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": _PASSWORD},
            headers=headers,
        )
        assert success.status_code == 200

        # R2 (account failcount) and R3 (distinct-IP HLL) reset on success.
        assert redis_client.exists(failcount_key("login", "acct", account_hash)) == 0
        # R1 (IP failcount) is NOT erased by a success.
        assert redis_client.exists(failcount_key("login", "ip", ip)) == 1

        # Nothing here ever crossed a threshold — no abuse-escalation
        # audit rows of either kind, from ordinary ALLOW/ordinary
        # below-threshold failures/an ordinary success.
        assert _audit_rows(db_session, AuditEvent.RATE_LIMITED) == []
        assert _audit_rows(db_session, AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED) == []
    finally:
        test_client.close()
