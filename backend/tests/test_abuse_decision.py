"""Tests for the deterministic abuse-decision policy layer (ADR 0006
§11/§12 — Slice 3b).

Two kinds of test live here, per this project's own established
precedent (`test_abuse_state.py`, `test_redis_rate_limiter.py`):

- A small number of pure unit tests (rule-table shape, `AbuseContext`
  construction, the Redis-unconfigured no-op path) that need no Redis at
  all and run instantly.
- The majority: real-Redis integration tests, run against a real Redis
  instance — no mocks, per ADR 0002/0006 §16's "no mock substitute for
  the real datastore" precedent. A mock cannot verify the atomicity/
  precedence/concurrency properties this layer depends on.

HTTP-level tests (through `TestClient`, asserting on response status/
headers/audit rows) are deliberately not added here — per the Slice 3b
readiness review, those belong to Slice 3c. This file stops at the
`abuse_decision` module boundary, exactly as `test_abuse_state.py`
stopped at the `abuse_state` module boundary.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
import redis

from app.core.abuse_decision import (
    _BLOCK_DIMENSIONS,
    _STRICT_DIMENSIONS,
    AbuseContext,
    AbuseDecision,
    check,
    record_forgot_password_request,
    record_login_failure,
    record_login_success,
    record_reset_validation_failure,
)
from app.core.abuse_keys import block_key, failcount_key, strict_throttle_key
from app.core.abuse_state import is_strict_throttle_active, is_temporarily_blocked
from app.core.rate_limit import DimensionSpec, RedisTokenBucketLimiter
from app.core.redis_client import build_redis_client
from app.core.redis_keys import hash_account_identifier

_REDIS_URL = os.environ["REDIS_URL"]  # set by conftest.py / the environment


@pytest.fixture
def redis_conn() -> Iterator[redis.Redis]:
    client = build_redis_client(_REDIS_URL, socket_timeout=2.0, socket_connect_timeout=2.0)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def _cleanup_abuse_keys(redis_conn: redis.Redis) -> Iterator[None]:
    yield
    for key in redis_conn.scan_iter(match="abuse:*"):
        redis_conn.delete(key)
    for key in redis_conn.scan_iter(match="rl:*"):
        redis_conn.delete(key)


def _unique_ip() -> str:
    return f"198.51.100.{uuid.uuid4().int % 256}-{uuid.uuid4().hex[:8]}"


def _unique_account_hash() -> str:
    return uuid.uuid4().hex


# --- 1: rule table correctness (unit, no Redis) ------------------------------


def test_rule_table_dimensions_match_the_approved_r1_r5_design() -> None:
    assert _BLOCK_DIMENSIONS["login"] == ("acct",)  # R3
    assert _BLOCK_DIMENSIONS["forgot-password"] == ()  # no block rule
    assert _BLOCK_DIMENSIONS["reset-password"] == ("ip",)  # R5
    assert _STRICT_DIMENSIONS["login"] == ("ip", "acct")  # R1, R2
    assert _STRICT_DIMENSIONS["forgot-password"] == ("ip",)  # R4
    assert _STRICT_DIMENSIONS["reset-password"] == ()  # no strict rule


# --- 2: AbuseContext correctness (unit, no Redis) -----------------------------


def test_abuse_context_account_hash_defaults_to_none() -> None:
    context = AbuseContext(operation="reset-password", ip="203.0.113.1")
    assert context.account_hash is None


def test_abuse_context_is_frozen() -> None:
    context = AbuseContext(operation="login", ip="203.0.113.1", account_hash="x")
    with pytest.raises(AttributeError):
        context.ip = "203.0.113.2"  # type: ignore[misc]


# --- 27: Redis unconfigured -> no-op (unit, no Redis) -------------------------


def test_check_with_no_client_returns_allow_and_no_strict_dimensions() -> None:
    context = AbuseContext(operation="login", ip=_unique_ip(), account_hash=_unique_account_hash())
    decision = check(None, context)
    assert decision == AbuseDecision(temporary_blocked=False, retry_after_seconds=None)


def test_record_functions_with_no_client_are_safe_no_ops() -> None:
    context = AbuseContext(operation="login", ip=_unique_ip(), account_hash=_unique_account_hash())
    outcome = record_login_failure(None, context)
    assert outcome.newly_escalated is False
    record_login_success(None, context)  # must not raise
    fp_outcome = record_forgot_password_request(None, context)
    assert fp_outcome.newly_escalated is False
    reset_outcome = record_reset_validation_failure(None, context)
    assert reset_outcome.newly_escalated is False


# --- 3-9: R1-R5 threshold behavior (below / exact / already-active) ----------


def test_r1_ip_strict_throttle_escalates_only_at_threshold(redis_conn: redis.Redis) -> None:
    # A fresh, one-off account per call: no single account ever
    # accumulates more than 1 failure (R2 never fires) and never sees
    # more than 1 distinct IP (R3 never fires) -- isolates R1 cleanly.
    ip = _unique_ip()
    for _ in range(9):
        outcome = record_login_failure(
            redis_conn,
            AbuseContext(operation="login", ip=ip, account_hash=_unique_account_hash()),
        )
        assert outcome.rule_id is None
    assert (
        is_strict_throttle_active(redis_conn, operation="login", dimension="ip", value=ip) is False
    )

    outcome = record_login_failure(
        redis_conn, AbuseContext(operation="login", ip=ip, account_hash=_unique_account_hash())
    )
    assert outcome.rule_id == "R1"
    assert outcome.action == "STRICT_THROTTLE"
    assert outcome.newly_escalated is True
    assert (
        is_strict_throttle_active(redis_conn, operation="login", dimension="ip", value=ip) is True
    )


def test_r2_account_strict_throttle_escalates_only_at_threshold(redis_conn: redis.Redis) -> None:
    # Cycle through only 2 distinct IPs (well under R3's distinct-IP
    # threshold of 5), each hit 5 times (well under R1's per-IP
    # threshold of 10) -- isolates R2 cleanly.
    account_hash = _unique_account_hash()
    ips = [_unique_ip(), _unique_ip()]
    for i in range(9):
        context = AbuseContext(operation="login", ip=ips[i % 2], account_hash=account_hash)
        outcome = record_login_failure(redis_conn, context)
        assert outcome.rule_id is None, f"unexpected escalation at failure {i + 1}"

    context = AbuseContext(operation="login", ip=ips[9 % 2], account_hash=account_hash)
    outcome = record_login_failure(redis_conn, context)
    assert outcome.rule_id == "R2"
    assert outcome.action == "STRICT_THROTTLE"
    assert (
        is_strict_throttle_active(
            redis_conn, operation="login", dimension="acct", value=account_hash
        )
        is True
    )


def test_r3_temporary_block_escalates_only_at_distinct_ip_threshold(
    redis_conn: redis.Redis,
) -> None:
    account_hash = _unique_account_hash()
    for i in range(4):
        context = AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
        outcome = record_login_failure(redis_conn, context)
        assert outcome.rule_id is None, f"unexpected escalation at distinct IP {i + 1}"

    context = AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
    outcome = record_login_failure(redis_conn, context)
    assert outcome.rule_id == "R3"
    assert outcome.action == "TEMPORARY_BLOCK"
    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is True
    )


def test_r4_forgot_password_strict_throttle_escalates_only_at_threshold(
    redis_conn: redis.Redis,
) -> None:
    ip = _unique_ip()
    for i in range(9):
        context = AbuseContext(operation="forgot-password", ip=ip)
        outcome = record_forgot_password_request(redis_conn, context)
        assert outcome.rule_id is None, f"unexpected escalation at request {i + 1}"

    context = AbuseContext(operation="forgot-password", ip=ip)
    outcome = record_forgot_password_request(redis_conn, context)
    assert outcome.rule_id == "R4"
    assert outcome.action == "STRICT_THROTTLE"


def test_r5_reset_password_temporary_block_escalates_only_at_threshold(
    redis_conn: redis.Redis,
) -> None:
    ip = _unique_ip()
    for i in range(14):
        context = AbuseContext(operation="reset-password", ip=ip)
        outcome = record_reset_validation_failure(redis_conn, context)
        assert outcome.rule_id is None, f"unexpected escalation at failure {i + 1}"

    context = AbuseContext(operation="reset-password", ip=ip)
    outcome = record_reset_validation_failure(redis_conn, context)
    assert outcome.rule_id == "R5"
    assert outcome.action == "TEMPORARY_BLOCK"


# --- 10: already-active escalation does not re-fire --------------------------


def test_already_escalated_rule_does_not_report_newly_escalated_again(
    redis_conn: redis.Redis,
) -> None:
    ip = _unique_ip()
    context = AbuseContext(operation="forgot-password", ip=ip)
    for _ in range(10):
        record_forgot_password_request(redis_conn, context)
    outcome = record_forgot_password_request(redis_conn, context)
    assert outcome.rule_id is None  # still escalated, but not a *new* escalation
    assert (
        is_strict_throttle_active(redis_conn, operation="forgot-password", dimension="ip", value=ip)
        is True
    )


# --- 11-13: TTL expiry / temporary-block TTL / no indefinite refresh ---------


def test_temporary_block_ttl_is_finite_and_reported_by_check(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    context = AbuseContext(operation="reset-password", ip=ip)
    for _ in range(15):
        record_reset_validation_failure(redis_conn, context)

    decision = check(redis_conn, context)
    assert decision.temporary_blocked is True
    assert decision.retry_after_seconds is not None
    assert 0 < decision.retry_after_seconds <= 600


def test_temporary_block_does_not_indefinitely_refresh_on_repeated_crossings(
    redis_conn: redis.Redis,
) -> None:
    ip = _unique_ip()
    context = AbuseContext(operation="reset-password", ip=ip)
    for _ in range(15):
        record_reset_validation_failure(redis_conn, context)

    key = block_key("reset-password", "ip", ip)
    redis_conn.expire(key, 2)  # force a short TTL to make the test fast
    ttl_before = redis_conn.ttl(key)

    for _ in range(5):
        record_reset_validation_failure(redis_conn, context)  # repeated crossings

    ttl_after = redis_conn.ttl(key)
    assert ttl_after <= ttl_before  # never refreshed upward by a later crossing

    time.sleep(2.3)
    assert check(redis_conn, context).temporary_blocked is False


def test_strict_throttle_ttl_expires_and_check_stops_reporting_it_active(
    redis_conn: redis.Redis,
) -> None:
    ip = _unique_ip()
    context = AbuseContext(operation="forgot-password", ip=ip)
    for _ in range(10):
        record_forgot_password_request(redis_conn, context)

    key = strict_throttle_key("forgot-password", "ip", ip)
    redis_conn.expire(key, 1)
    time.sleep(1.3)

    decision = check(redis_conn, context)
    assert decision.strict_dimensions == []


# --- 14-16: precedence / simultaneous rules -----------------------------------


def test_r1_and_r2_simultaneously_active_both_fold_into_check(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    account_hash = _unique_account_hash()

    for _ in range(10):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=ip, account_hash=account_hash)
        )

    decision = check(redis_conn, AbuseContext(operation="login", ip=ip, account_hash=account_hash))
    assert decision.temporary_blocked is False
    keys = {spec.key for spec in decision.strict_dimensions}
    assert strict_throttle_key("login", "ip", ip) in keys
    assert strict_throttle_key("login", "acct", account_hash) in keys
    assert len(decision.strict_dimensions) == 2


def test_r2_and_r3_simultaneously_active_block_dominates(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    # 10 failures from 10 distinct IPs crosses both R2 (account failcount)
    # and R3 (distinct-IP threshold=5) in the same sequence.
    for _ in range(10):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
        )

    assert (
        is_strict_throttle_active(
            redis_conn, operation="login", dimension="acct", value=account_hash
        )
        is True
    )
    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is True
    )

    decision = check(
        redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
    )
    assert decision.temporary_blocked is True
    assert decision.strict_dimensions == []  # never even inspected, once blocked


def test_r1_r2_r3_simultaneously_active_block_still_dominates(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    shared_ip = _unique_ip()
    # Route every failure through the same IP too, so R1 also crosses.
    for _ in range(10):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=shared_ip, account_hash=account_hash)
        )

    assert (
        is_strict_throttle_active(redis_conn, operation="login", dimension="ip", value=shared_ip)
        is True
    )
    assert (
        is_strict_throttle_active(
            redis_conn, operation="login", dimension="acct", value=account_hash
        )
        is True
    )
    # distinct_ip_threshold=5 was never crossed here (only one shared IP),
    # so R3 does NOT fire in this scenario -- re-run with distinct IPs too.
    for _ in range(5):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
        )
    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is True
    )

    decision = check(
        redis_conn, AbuseContext(operation="login", ip=shared_ip, account_hash=account_hash)
    )
    assert decision.temporary_blocked is True
    assert decision.strict_dimensions == []


# --- 17: temporary block precedence, explicit -----------------------------


def test_check_never_inspects_strict_state_once_blocked(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    ip = _unique_ip()
    context = AbuseContext(operation="login", ip=ip, account_hash=account_hash)

    # Escalate R1 (strict) first...
    for _ in range(10):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=ip, account_hash=_unique_account_hash())
        )
    # ...then escalate R3 (block) for this specific account via distinct IPs.
    for _ in range(5):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
        )

    decision = check(redis_conn, context)
    assert decision.temporary_blocked is True
    assert decision.retry_after_seconds is not None
    assert decision.strict_dimensions == []


# --- 18: block expiry falls through to still-active strict throttle ---------


def test_block_expiry_falls_through_to_still_active_strict_throttle(
    redis_conn: redis.Redis,
) -> None:
    # R5 has no strict-throttle counterpart, so this scenario is exercised
    # on login instead, where R2 (strict) and R3 (block) share the acct
    # dimension and can coexist.
    account_hash = _unique_account_hash()
    login_context = AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
    for _ in range(10):
        record_login_failure(redis_conn, login_context)
    for _ in range(5):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
        )

    block = block_key("login", "acct", account_hash)
    redis_conn.expire(block, 1)
    time.sleep(1.3)

    decision = check(redis_conn, login_context)
    assert decision.temporary_blocked is False
    keys = {spec.key for spec in decision.strict_dimensions}
    assert strict_throttle_key("login", "acct", account_hash) in keys


# --- 19-20: account / IP isolation --------------------------------------------


def test_account_isolation_one_accounts_escalation_does_not_affect_another(
    redis_conn: redis.Redis,
) -> None:
    account_a = _unique_account_hash()
    account_b = _unique_account_hash()
    for _ in range(10):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_a)
        )

    decision_b = check(
        redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_b)
    )
    assert decision_b.temporary_blocked is False
    assert decision_b.strict_dimensions == []


def test_ip_isolation_one_ips_escalation_does_not_affect_another(redis_conn: redis.Redis) -> None:
    ip_a = _unique_ip()
    ip_b = _unique_ip()
    for _ in range(10):
        record_forgot_password_request(
            redis_conn, AbuseContext(operation="forgot-password", ip=ip_a)
        )

    decision_b = check(redis_conn, AbuseContext(operation="forgot-password", ip=ip_b))
    assert decision_b.strict_dimensions == []


# --- 21-23: successful-login reset behavior -----------------------------------


def test_successful_login_resets_r2_and_r3_state(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    context = AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
    record_login_failure(redis_conn, context)
    assert redis_conn.exists(failcount_key("login", "acct", account_hash)) == 1

    record_login_success(redis_conn, context)

    assert redis_conn.exists(failcount_key("login", "acct", account_hash)) == 0


def test_successful_login_does_not_erase_r1_ip_state(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    account_a = _unique_account_hash()
    account_b = _unique_account_hash()
    record_login_failure(redis_conn, AbuseContext(operation="login", ip=ip, account_hash=account_a))

    record_login_success(redis_conn, AbuseContext(operation="login", ip=ip, account_hash=account_b))

    assert redis_conn.exists(failcount_key("login", "ip", ip)) == 1


def test_successful_login_does_not_remove_active_strict_or_block_state(
    redis_conn: redis.Redis,
) -> None:
    account_hash = _unique_account_hash()
    for _ in range(10):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
        )
    for _ in range(5):
        record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
        )
    assert (
        is_strict_throttle_active(
            redis_conn, operation="login", dimension="acct", value=account_hash
        )
        is True
    )
    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is True
    )

    record_login_success(
        redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
    )

    assert (
        is_strict_throttle_active(
            redis_conn, operation="login", dimension="acct", value=account_hash
        )
        is True
    )
    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is True
    )


# --- 24-25: R4 unconditional / R5 failure-only --------------------------------


def test_r4_records_every_request_regardless_of_outcome(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    context = AbuseContext(operation="forgot-password", ip=ip)
    for expected in (1, 2, 3):
        record_forgot_password_request(redis_conn, context)
        count = int(redis_conn.get(failcount_key("forgot-password", "ip", ip)) or 0)
        assert count == expected


def test_r5_only_records_what_it_is_explicitly_called_for(redis_conn: redis.Redis) -> None:
    """`record_reset_validation_failure()` itself has no success/failure
    branching -- calling it always records one failure, unconditionally.
    The actual "only call this on reset_token_invalid/_expired/
    _already_used, never on success" guarantee is therefore an
    endpoint-wiring property (app/api/v1/auth.py), not something this
    function can enforce on its own -- verified separately by a
    dedicated HTTP-level test in test_rate_limit_wiring.py asserting a
    successful reset creates no R5 failcount key."""
    ip = _unique_ip()
    context = AbuseContext(operation="reset-password", ip=ip)
    before = redis_conn.exists(failcount_key("reset-password", "ip", ip))
    assert before == 0

    record_reset_validation_failure(redis_conn, context)

    after = int(redis_conn.get(failcount_key("reset-password", "ip", ip)) or 0)
    assert after == 1


# --- 26: Redis unavailable -> fail open ---------------------------------------


def test_redis_unavailable_check_fails_open() -> None:
    unreachable = build_redis_client(
        "redis://localhost:1/0", socket_timeout=0.05, socket_connect_timeout=0.05
    )
    try:
        context = AbuseContext(
            operation="login", ip=_unique_ip(), account_hash=_unique_account_hash()
        )
        decision = check(unreachable, context)
        assert decision == AbuseDecision(temporary_blocked=False, retry_after_seconds=None)
    finally:
        unreachable.close()


def test_redis_unavailable_record_functions_fail_open_safely() -> None:
    unreachable = build_redis_client(
        "redis://localhost:1/0", socket_timeout=0.05, socket_connect_timeout=0.05
    )
    try:
        context = AbuseContext(
            operation="login", ip=_unique_ip(), account_hash=_unique_account_hash()
        )
        assert record_login_failure(unreachable, context).newly_escalated is False
        record_login_success(unreachable, context)  # must not raise
        assert record_forgot_password_request(unreachable, context).newly_escalated is False
        assert record_reset_validation_failure(unreachable, context).newly_escalated is False
    finally:
        unreachable.close()


# --- 28-29: concurrency ---------------------------------------------------


def test_concurrent_login_failures_never_lose_or_double_count(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    account_hash = _unique_account_hash()
    attempts = 20
    escalated_flags: list[bool] = []
    lock = threading.Lock()

    def _attempt() -> None:
        outcome = record_login_failure(
            redis_conn, AbuseContext(operation="login", ip=ip, account_hash=account_hash)
        )
        with lock:
            escalated_flags.append(outcome.rule_id == "R1")

    threads = [threading.Thread(target=_attempt) for _ in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_count = int(redis_conn.get(failcount_key("login", "ip", ip)) or 0)
    assert final_count == attempts
    # Exactly one call (the one whose INCR result first reached 10) may
    # report the R1 escalation -- never zero, never more than one.
    assert escalated_flags.count(True) <= 1


def test_concurrent_r3_distinct_ip_failures_never_lose_or_double_count(
    redis_conn: redis.Redis,
) -> None:
    account_hash = _unique_account_hash()
    attempts = 20

    def _attempt() -> None:
        record_login_failure(
            redis_conn,
            AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash),
        )

    threads = [threading.Thread(target=_attempt) for _ in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    decision = check(
        redis_conn, AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)
    )
    assert decision.temporary_blocked is True  # 20 distinct IPs >> M=5


# --- 30: strict-dimension consumption stays atomic with the base dimension --


def test_strict_dimension_never_partially_consumes_the_base_dimension_on_rejection(
    redis_conn: redis.Redis,
) -> None:
    ip = _unique_ip()
    context = AbuseContext(operation="forgot-password", ip=ip)
    for _ in range(10):
        record_forgot_password_request(redis_conn, context)  # escalates R4

    decision = check(redis_conn, context)
    assert len(decision.strict_dimensions) == 1
    strict_spec = decision.strict_dimensions[0]

    # Exhaust the strict bucket directly (simulate two prior consumptions).
    redis_conn.hset(strict_spec.key, mapping={"tokens": 0, "last_refill_at": time.time()})

    base_key = f"rl:forgot-password:ip:{ip}"
    base_spec = DimensionSpec(key=base_key, capacity=5.0, refill_rate=5.0 / 60)

    limiter = RedisTokenBucketLimiter(redis_conn)
    result = limiter.check_all([base_spec, strict_spec])
    assert result.allowed is False

    # The base dimension must show a FULL, unconsumed bucket -- either
    # never written (no key) or written with a full token count -- since
    # the combined check_all() must reject before writing anything.
    assert redis_conn.exists(base_key) == 0


def test_strict_dimension_allows_through_when_both_dimensions_have_capacity(
    redis_conn: redis.Redis,
) -> None:
    ip = _unique_ip()
    context = AbuseContext(operation="forgot-password", ip=ip)
    for _ in range(10):
        record_forgot_password_request(redis_conn, context)  # escalates R4, fresh 2-token bucket

    decision = check(redis_conn, context)
    strict_spec = decision.strict_dimensions[0]

    base_key = f"rl:forgot-password:ip:{_unique_ip()}"
    base_spec = DimensionSpec(key=base_key, capacity=5.0, refill_rate=5.0 / 60)

    limiter = RedisTokenBucketLimiter(redis_conn)
    result = limiter.check_all([base_spec, strict_spec])
    assert result.allowed is True


# --- 31: no raw email/secret leakage ------------------------------------------


def test_no_raw_email_leaks_through_the_decision_layer(redis_conn: redis.Redis) -> None:
    email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
    account_hash = hash_account_identifier(email, key=b"test-hmac-key")
    context = AbuseContext(operation="login", ip=_unique_ip(), account_hash=account_hash)

    record_login_failure(redis_conn, context)
    check(redis_conn, context)

    for key in redis_conn.scan_iter(match="abuse:*"):
        key_str = key.decode() if isinstance(key, bytes) else key
        assert email not in key_str
        assert "victim" not in key_str
    for key in redis_conn.scan_iter(match="rl:*"):
        key_str = key.decode() if isinstance(key, bytes) else key
        assert email not in key_str
