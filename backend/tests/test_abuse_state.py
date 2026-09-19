"""Integration tests for the deterministic abuse-protection layer's
Redis primitives (ADR 0006 §11/§12 — Slice 3a).

Run against a real Redis instance, per this project's established
"no mock substitute for the real datastore" precedent (ADR 0002,
extended to Redis by ADR 0006 §16, already applied to the rate-limit
engine in `test_redis_rate_limiter.py`) — a mock cannot verify the
atomicity/concurrency properties this layer depends on.

Deliberately uses small, fast thresholds/windows (e.g. threshold=3,
window=2s) throughout rather than the approved production values
(N=10, W=600s, etc.) -- those numbers are Slice 3b's rule-table
concern, not this primitive layer's; using them here would only make
the suite slow without testing anything Slice 3a itself is responsible
for. Every dimension value (fake IP, fake account hash) is unique per
test via `uuid.uuid4()`, so no explicit cross-test cleanup is required
beyond each key's own TTL -- the same pattern `test_redis_rate_limiter.py`
already establishes.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
import redis

from app.core.abuse_keys import block_key, distinct_ips_key, failcount_key, strict_throttle_key
from app.core.abuse_state import (
    STRICT_THROTTLE_CAPACITY,
    TEMPORARY_BLOCK_TTL_SECONDS,
    is_strict_throttle_active,
    is_temporarily_blocked,
    record_ip_failure,
    record_login_failure,
    reset_account_state,
)
from app.core.redis_client import RedisUnavailableError, build_redis_client

_REDIS_URL = os.environ["REDIS_URL"]  # set by conftest.py / the environment


@pytest.fixture
def redis_conn() -> Iterator[redis.Redis]:
    client = build_redis_client(_REDIS_URL, socket_timeout=2.0, socket_connect_timeout=2.0)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def _cleanup_abuse_keys(redis_conn: redis.Redis) -> Iterator[None]:
    """No other code in this repository writes to the `abuse:*` namespace
    yet (Slice 3a has no endpoint wiring) -- safe to sweep it clean after
    every test in this module, mirroring `test_redis_rate_limiter.py`'s
    own `_cleanup_test_keys` fixture."""
    yield
    for key in redis_conn.scan_iter(match="abuse:*"):
        redis_conn.delete(key)


def _unique_ip() -> str:
    return f"198.51.100.{uuid.uuid4().int % 256}-{uuid.uuid4().hex[:8]}"


def _unique_account_hash() -> str:
    return uuid.uuid4().hex


# --- 1-4: failcount basics (creation, increment, TTL, expiry) --------------


def test_ip_failure_counter_is_created_on_first_call(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    result = record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=3,
        window_seconds=60,
        escalation="strict",
    )
    assert result.failure_count == 1
    assert result.newly_escalated is False
    assert redis_conn.exists(failcount_key("forgot-password", "ip", ip)) == 1


def test_ip_failure_counter_increments_on_each_call(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    for expected in (1, 2, 3):
        result = record_ip_failure(
            redis_conn,
            operation="forgot-password",
            ip=ip,
            threshold=100,
            window_seconds=60,
            escalation="strict",
        )
        assert result.failure_count == expected


def test_ip_failure_counter_ttl_is_finite_and_positive(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=100,
        window_seconds=60,
        escalation="strict",
    )
    ttl = redis_conn.ttl(failcount_key("forgot-password", "ip", ip))
    assert ttl > 0
    assert ttl != -1  # no immortal keys
    assert ttl != -2  # not already gone


def test_ip_failure_counter_expires_and_restarts_fresh(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=100,
        window_seconds=1,
        escalation="strict",
    )
    assert redis_conn.exists(failcount_key("forgot-password", "ip", ip)) == 1

    time.sleep(1.3)

    assert redis_conn.exists(failcount_key("forgot-password", "ip", ip)) == 0
    result = record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=100,
        window_seconds=60,
        escalation="strict",
    )
    assert result.failure_count == 1  # fresh window, not 2


# --- 5-10: HyperLogLog lifecycle --------------------------------------------


def test_hll_created_on_first_ip(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    result = record_login_failure(
        redis_conn,
        ip=_unique_ip(),
        account_hash=account_hash,
        ip_failure_threshold=100,
        account_failure_threshold=100,
        distinct_ip_threshold=5,
        window_seconds=60,
    )
    assert result.distinct_ip_count == 1
    assert redis_conn.exists(distinct_ips_key(account_hash)) == 1


def test_hll_repeated_same_ip_does_not_increase_distinct_count(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    ip = _unique_ip()
    for _ in range(3):
        result = record_login_failure(
            redis_conn,
            ip=ip,
            account_hash=account_hash,
            ip_failure_threshold=100,
            account_failure_threshold=100,
            distinct_ip_threshold=5,
            window_seconds=60,
        )
    assert result.distinct_ip_count == 1


def test_hll_counts_multiple_distinct_ips(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    for _ in range(4):
        result = record_login_failure(
            redis_conn,
            ip=_unique_ip(),
            account_hash=account_hash,
            ip_failure_threshold=100,
            account_failure_threshold=100,
            distinct_ip_threshold=100,
            window_seconds=60,
        )
    assert result.distinct_ip_count == 4


def test_hll_threshold_boundary_triggers_temporary_block(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    threshold = 3

    for _ in range(threshold - 1):
        result = record_login_failure(
            redis_conn,
            ip=_unique_ip(),
            account_hash=account_hash,
            ip_failure_threshold=100,
            account_failure_threshold=100,
            distinct_ip_threshold=threshold,
            window_seconds=60,
        )
        assert result.account_temporary_block_newly_escalated is False

    result = record_login_failure(
        redis_conn,
        ip=_unique_ip(),
        account_hash=account_hash,
        ip_failure_threshold=100,
        account_failure_threshold=100,
        distinct_ip_threshold=threshold,
        window_seconds=60,
    )
    assert result.distinct_ip_count == threshold
    assert result.account_temporary_block_newly_escalated is True
    assert redis_conn.exists(block_key("login", "acct", account_hash)) == 1


def test_hll_expires(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    record_login_failure(
        redis_conn,
        ip=_unique_ip(),
        account_hash=account_hash,
        ip_failure_threshold=100,
        account_failure_threshold=100,
        distinct_ip_threshold=100,
        window_seconds=1,
    )
    assert redis_conn.exists(distinct_ips_key(account_hash)) == 1

    time.sleep(1.3)

    assert redis_conn.exists(distinct_ips_key(account_hash)) == 0


def test_hll_reset_on_successful_login(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    record_login_failure(
        redis_conn,
        ip=_unique_ip(),
        account_hash=account_hash,
        ip_failure_threshold=100,
        account_failure_threshold=100,
        distinct_ip_threshold=100,
        window_seconds=60,
    )
    assert redis_conn.exists(distinct_ips_key(account_hash)) == 1

    reset_account_state(redis_conn, account_hash=account_hash)

    assert redis_conn.exists(distinct_ips_key(account_hash)) == 0


# --- 11-12: R2 reset on success / R1 not reset by success -------------------


def test_r2_account_failcount_resets_on_successful_login(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    record_login_failure(
        redis_conn,
        ip=_unique_ip(),
        account_hash=account_hash,
        ip_failure_threshold=100,
        account_failure_threshold=100,
        distinct_ip_threshold=100,
        window_seconds=60,
    )
    assert redis_conn.exists(failcount_key("login", "acct", account_hash)) == 1

    reset_account_state(redis_conn, account_hash=account_hash)

    assert redis_conn.exists(failcount_key("login", "acct", account_hash)) == 0


def test_r1_ip_failcount_is_not_reset_by_successful_login(redis_conn: redis.Redis) -> None:
    """The deliberate asymmetry the approved design requires: resetting
    IP-scoped state on any success would let an attacker "launder" a
    shared IP's failure history via an unrelated account's legitimate
    success (see `abuse_state.py`'s module docstring)."""
    ip = _unique_ip()
    account_a = _unique_account_hash()
    account_b = _unique_account_hash()

    record_login_failure(
        redis_conn,
        ip=ip,
        account_hash=account_a,
        ip_failure_threshold=100,
        account_failure_threshold=100,
        distinct_ip_threshold=100,
        window_seconds=60,
    )
    ip_count_before = redis_conn.get(failcount_key("login", "ip", ip))

    # A DIFFERENT account (account_b) succeeding from the same IP must
    # not touch account_a's evidence, and must not touch the shared IP
    # counter either -- reset_account_state only ever targets the
    # specific account passed to it.
    reset_account_state(redis_conn, account_hash=account_b)

    ip_count_after = redis_conn.get(failcount_key("login", "ip", ip))
    assert ip_count_after == ip_count_before
    assert redis_conn.exists(failcount_key("login", "acct", account_a)) == 1


# --- 13-16: temporary block --------------------------------------------------


def test_temporary_block_created_at_threshold(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    threshold = 3
    for _ in range(threshold - 1):
        result = record_ip_failure(
            redis_conn,
            operation="reset-password",
            ip=ip,
            threshold=threshold,
            window_seconds=60,
            escalation="block",
        )
        assert result.newly_escalated is False
        assert (
            is_temporarily_blocked(redis_conn, operation="reset-password", dimension="ip", value=ip)
            is False
        )

    result = record_ip_failure(
        redis_conn,
        operation="reset-password",
        ip=ip,
        threshold=threshold,
        window_seconds=60,
        escalation="block",
    )
    assert result.newly_escalated is True
    assert (
        is_temporarily_blocked(redis_conn, operation="reset-password", dimension="ip", value=ip)
        is True
    )


def test_temporary_block_ttl_matches_approved_value(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    record_ip_failure(
        redis_conn,
        operation="reset-password",
        ip=ip,
        threshold=1,
        window_seconds=60,
        escalation="block",
    )
    ttl = redis_conn.ttl(block_key("reset-password", "ip", ip))
    assert 0 < ttl <= TEMPORARY_BLOCK_TTL_SECONDS


def test_temporary_block_expires(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    result = record_ip_failure(
        redis_conn,
        operation="reset-password",
        ip=ip,
        threshold=1,
        window_seconds=60,
        escalation="block",
    )
    assert result.newly_escalated is True
    # Directly force a short TTL to make the test fast without waiting
    # out the real 600s TEMPORARY_BLOCK_TTL_SECONDS.
    redis_conn.expire(block_key("reset-password", "ip", ip), 1)

    time.sleep(1.3)

    assert (
        is_temporarily_blocked(redis_conn, operation="reset-password", dimension="ip", value=ip)
        is False
    )


def test_temporary_block_is_not_removed_by_successful_login(redis_conn: redis.Redis) -> None:
    account_hash = _unique_account_hash()
    threshold = 2
    for _ in range(threshold):
        record_login_failure(
            redis_conn,
            ip=_unique_ip(),
            account_hash=account_hash,
            ip_failure_threshold=1000,
            account_failure_threshold=1000,
            distinct_ip_threshold=threshold,
            window_seconds=60,
        )
    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is True
    )

    reset_account_state(redis_conn, account_hash=account_hash)

    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is True
    )


# --- 17-20: strict-throttle bucket -------------------------------------------


def test_strict_bucket_not_created_by_ordinary_failures(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    threshold = 5
    for _ in range(threshold - 1):
        record_ip_failure(
            redis_conn,
            operation="forgot-password",
            ip=ip,
            threshold=threshold,
            window_seconds=60,
            escalation="strict",
        )
    assert (
        is_strict_throttle_active(redis_conn, operation="forgot-password", dimension="ip", value=ip)
        is False
    )


def test_strict_bucket_created_only_after_escalation(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    threshold = 3
    for _ in range(threshold - 1):
        result = record_ip_failure(
            redis_conn,
            operation="forgot-password",
            ip=ip,
            threshold=threshold,
            window_seconds=60,
            escalation="strict",
        )
        assert result.newly_escalated is False

    result = record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=threshold,
        window_seconds=60,
        escalation="strict",
    )
    assert result.newly_escalated is True
    assert (
        is_strict_throttle_active(redis_conn, operation="forgot-password", dimension="ip", value=ip)
        is True
    )


def test_strict_bucket_uses_approved_capacity(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=1,
        window_seconds=60,
        escalation="strict",
    )
    key = strict_throttle_key("forgot-password", "ip", ip)
    tokens = float(redis_conn.hget(key, "tokens"))  # type: ignore[arg-type]
    assert tokens == STRICT_THROTTLE_CAPACITY
    assert redis_conn.hget(key, "last_refill_at") is not None


def test_strict_bucket_does_not_reset_already_consumed_tokens_on_re_escalation(
    redis_conn: redis.Redis,
) -> None:
    """A later crossing of the same threshold must refresh the bucket's
    TTL (keep the escalation alive) without resetting its token count
    back to full -- otherwise continued abuse could "refresh" an
    attacker's own strict-throttle allowance."""
    ip = _unique_ip()
    record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=1,
        window_seconds=60,
        escalation="strict",
    )
    key = strict_throttle_key("forgot-password", "ip", ip)
    redis_conn.hset(key, "tokens", 0)  # simulate the bucket having been consumed elsewhere

    record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=1,
        window_seconds=60,
        escalation="strict",
    )

    assert float(redis_conn.hget(key, "tokens")) == 0  # type: ignore[arg-type]


def test_strict_bucket_ttl_is_finite_and_matches_derived_value(redis_conn: redis.Redis) -> None:
    from app.core.abuse_state import _STRICT_THROTTLE_TTL_SECONDS

    ip = _unique_ip()
    record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=1,
        window_seconds=60,
        escalation="strict",
    )
    ttl = redis_conn.ttl(strict_throttle_key("forgot-password", "ip", ip))
    assert 0 < ttl <= _STRICT_THROTTLE_TTL_SECONDS


def test_strict_bucket_expires(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    record_ip_failure(
        redis_conn,
        operation="forgot-password",
        ip=ip,
        threshold=1,
        window_seconds=60,
        escalation="strict",
    )
    key = strict_throttle_key("forgot-password", "ip", ip)
    redis_conn.expire(key, 1)

    time.sleep(1.3)

    assert (
        is_strict_throttle_active(redis_conn, operation="forgot-password", dimension="ip", value=ip)
        is False
    )


# --- 21: multi-signal atomicity ----------------------------------------------


def test_multi_signal_login_failure_updates_only_the_dimensions_that_cross_threshold(
    redis_conn: redis.Redis,
) -> None:
    """R1 (IP) and R2 (account) are evaluated and escalated
    independently within the same atomic call -- one crossing must not
    affect, or be affected by, the other."""
    ip = _unique_ip()
    account_hash = _unique_account_hash()

    # High account threshold (never crossed), low IP threshold (crossed
    # on this exact call).
    result = record_login_failure(
        redis_conn,
        ip=ip,
        account_hash=account_hash,
        ip_failure_threshold=1,
        account_failure_threshold=1000,
        distinct_ip_threshold=1000,
        window_seconds=60,
    )

    assert result.ip_strict_throttle_newly_escalated is True
    assert result.account_strict_throttle_newly_escalated is False
    assert result.account_temporary_block_newly_escalated is False
    assert (
        is_strict_throttle_active(redis_conn, operation="login", dimension="ip", value=ip) is True
    )
    assert (
        is_strict_throttle_active(
            redis_conn, operation="login", dimension="acct", value=account_hash
        )
        is False
    )
    assert (
        is_temporarily_blocked(redis_conn, operation="login", dimension="acct", value=account_hash)
        is False
    )


# --- 22-23: concurrency -------------------------------------------------------


def test_concurrent_failure_increments_never_lose_or_double_count(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    attempts = 30
    results: list[int] = []
    lock = threading.Lock()

    def _attempt() -> None:
        result = record_ip_failure(
            redis_conn,
            operation="forgot-password",
            ip=ip,
            threshold=100_000,
            window_seconds=60,
            escalation="strict",
        )
        with lock:
            results.append(result.failure_count)

    threads = [threading.Thread(target=_attempt) for _ in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every count from 1..attempts must appear exactly once -- no lost
    # updates, no double counting, regardless of arrival order.
    assert sorted(results) == list(range(1, attempts + 1))


def test_concurrent_reset_and_failure_produce_only_bounded_valid_states(
    redis_conn: redis.Redis,
) -> None:
    """The approved, explicitly-analyzed race: a concurrent reset and a
    batch of concurrent failures for the same account. Redis serializes
    all commands, so the final count is deterministically "last write
    wins" -- but which write is last is not determined by this test.
    The property under test is that the result is always one of the
    valid, explainable outcomes (never negative, never exceeding the
    number of failures fired), not that a specific ordering wins.
    """
    account_hash = _unique_account_hash()
    failures = 10

    def _fail() -> None:
        record_login_failure(
            redis_conn,
            ip=_unique_ip(),
            account_hash=account_hash,
            ip_failure_threshold=100_000,
            account_failure_threshold=100_000,
            distinct_ip_threshold=100_000,
            window_seconds=60,
        )

    def _reset() -> None:
        reset_account_state(redis_conn, account_hash=account_hash)

    threads = [threading.Thread(target=_fail) for _ in range(failures)]
    threads.append(threading.Thread(target=_reset))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    raw = redis_conn.get(failcount_key("login", "acct", account_hash))
    final_count = int(raw) if raw is not None else 0

    assert final_count >= 0
    assert final_count <= failures


# --- 25-27: cross-account isolation / shared-IP / multi-IP ------------------


def test_cross_account_isolation(redis_conn: redis.Redis) -> None:
    account_a = _unique_account_hash()
    account_b = _unique_account_hash()

    for _ in range(3):
        record_login_failure(
            redis_conn,
            ip=_unique_ip(),
            account_hash=account_a,
            ip_failure_threshold=1000,
            account_failure_threshold=1000,
            distinct_ip_threshold=1000,
            window_seconds=60,
        )

    result_b = record_login_failure(
        redis_conn,
        ip=_unique_ip(),
        account_hash=account_b,
        ip_failure_threshold=1000,
        account_failure_threshold=1000,
        distinct_ip_threshold=1000,
        window_seconds=60,
    )
    assert result_b.account_failure_count == 1  # unaffected by account_a's 3 failures


def test_shared_ip_across_multiple_accounts_accumulates_the_ip_dimension_only(
    redis_conn: redis.Redis,
) -> None:
    """One attacker's IP failing against many different accounts must
    accumulate R1 (IP-scoped) across all of them, while each account's
    own R2 (account-scoped) counter stays independent -- exactly the
    "many accounts, one IP" credential-stuffing shape R1 exists for."""
    ip = _unique_ip()
    account_a = _unique_account_hash()
    account_b = _unique_account_hash()

    result_a = record_login_failure(
        redis_conn,
        ip=ip,
        account_hash=account_a,
        ip_failure_threshold=1000,
        account_failure_threshold=1000,
        distinct_ip_threshold=1000,
        window_seconds=60,
    )
    result_b = record_login_failure(
        redis_conn,
        ip=ip,
        account_hash=account_b,
        ip_failure_threshold=1000,
        account_failure_threshold=1000,
        distinct_ip_threshold=1000,
        window_seconds=60,
    )

    assert result_a.ip_failure_count == 1
    assert result_b.ip_failure_count == 2  # shared IP counter accumulated
    assert result_a.account_failure_count == 1
    assert result_b.account_failure_count == 1  # independent account counters


def test_multiple_ips_against_one_account_accumulates_r2_and_r3(redis_conn: redis.Redis) -> None:
    """The R3 "coordinated abuse" shape: one account, many distinct
    source IPs. R2 (account failcount) must accumulate across all of
    them, and R3 (distinct-IP HLL) must count each distinct IP."""
    account_hash = _unique_account_hash()
    ips = [_unique_ip() for _ in range(4)]

    result = None
    for ip in ips:
        result = record_login_failure(
            redis_conn,
            ip=ip,
            account_hash=account_hash,
            ip_failure_threshold=1000,
            account_failure_threshold=1000,
            distinct_ip_threshold=1000,
            window_seconds=60,
        )
    assert result is not None
    assert result.account_failure_count == len(ips)
    assert result.distinct_ip_count == len(ips)


# --- 28: Redis unavailable ---------------------------------------------------


def test_redis_unavailable_raises_redis_unavailable_error_not_a_raw_redis_exception() -> None:
    unreachable_client = build_redis_client(
        "redis://localhost:1/0", socket_timeout=0.05, socket_connect_timeout=0.05
    )
    try:
        with pytest.raises(RedisUnavailableError):
            record_ip_failure(
                unreachable_client,
                operation="forgot-password",
                ip=_unique_ip(),
                threshold=1,
                window_seconds=60,
                escalation="strict",
            )
        with pytest.raises(RedisUnavailableError):
            record_login_failure(
                unreachable_client,
                ip=_unique_ip(),
                account_hash=_unique_account_hash(),
                ip_failure_threshold=1,
                account_failure_threshold=1,
                distinct_ip_threshold=1,
                window_seconds=60,
            )
        with pytest.raises(RedisUnavailableError):
            reset_account_state(unreachable_client, account_hash=_unique_account_hash())
        with pytest.raises(RedisUnavailableError):
            is_strict_throttle_active(
                unreachable_client, operation="login", dimension="ip", value=_unique_ip()
            )
        with pytest.raises(RedisUnavailableError):
            is_temporarily_blocked(
                unreachable_client, operation="login", dimension="ip", value=_unique_ip()
            )
    finally:
        unreachable_client.close()


# --- 30-31: no raw secrets anywhere ------------------------------------------


def test_no_raw_email_in_abuse_keys(redis_conn: redis.Redis) -> None:
    from app.core.redis_keys import hash_account_identifier

    email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
    account_hash = hash_account_identifier(email, key=b"test-hmac-key")

    record_login_failure(
        redis_conn,
        ip=_unique_ip(),
        account_hash=account_hash,
        ip_failure_threshold=1,
        account_failure_threshold=1,
        distinct_ip_threshold=1,
        window_seconds=60,
    )

    for key in redis_conn.scan_iter(match="abuse:*"):
        key_str = key.decode() if isinstance(key, bytes) else key
        assert email not in key_str
        assert "victim" not in key_str
        assert "@example.com" not in key_str


def test_no_raw_secrets_in_abuse_state_values(redis_conn: redis.Redis) -> None:
    """Values stored (strict-bucket token counts, block flags) are
    never anything but numbers/flags -- confirmed by construction, this
    test asserts the actual stored values contain no unexpected
    string content."""
    ip = _unique_ip()
    account_hash = _unique_account_hash()
    record_login_failure(
        redis_conn,
        ip=ip,
        account_hash=account_hash,
        ip_failure_threshold=1,
        account_failure_threshold=1,
        distinct_ip_threshold=1,
        window_seconds=60,
    )

    strict_key = strict_throttle_key("login", "ip", ip)
    fields = redis_conn.hgetall(strict_key)
    assert set(fields.keys()) <= {b"tokens", b"last_refill_at"}

    block_flag = redis_conn.get(block_key("login", "acct", account_hash))
    assert block_flag == b"1"


# --- 32: bounded lifecycle sweep ---------------------------------------------


def test_every_created_key_type_has_a_finite_ttl(redis_conn: redis.Redis) -> None:
    ip = _unique_ip()
    account_hash = _unique_account_hash()

    record_login_failure(
        redis_conn,
        ip=ip,
        account_hash=account_hash,
        ip_failure_threshold=1,
        account_failure_threshold=1,
        distinct_ip_threshold=1,
        window_seconds=60,
    )

    keys = [
        failcount_key("login", "ip", ip),
        failcount_key("login", "acct", account_hash),
        distinct_ips_key(account_hash),
        strict_throttle_key("login", "ip", ip),
        strict_throttle_key("login", "acct", account_hash),
        block_key("login", "acct", account_hash),
    ]
    for key in keys:
        ttl = redis_conn.ttl(key)
        assert ttl > 0, f"{key} has no finite TTL (ttl={ttl})"
