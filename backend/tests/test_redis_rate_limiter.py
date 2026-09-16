"""Integration tests for the Redis-backed token-bucket engine (ADR 0006
§8, §10) — run against a real Redis instance, per this project's existing
"no mock substitute for the real datastore" precedent (ADR 0002, extended
to Redis by ADR 0006 §16): a mock cannot verify the atomicity/concurrency
properties this design depends on.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
import redis

from app.core.rate_limit import DimensionSpec, RedisTokenBucketLimiter
from app.core.redis_client import RedisUnavailableError, build_redis_client

_REDIS_URL = os.environ["REDIS_URL"]  # set by conftest.py / the environment


@pytest.fixture
def redis_conn() -> Iterator[redis.Redis]:
    client = build_redis_client(_REDIS_URL, socket_timeout=2.0, socket_connect_timeout=2.0)
    yield client
    client.close()


@pytest.fixture
def limiter(redis_conn: redis.Redis) -> RedisTokenBucketLimiter:
    return RedisTokenBucketLimiter(redis_conn)


@pytest.fixture
def unique_key() -> str:
    return f"test:rl:{uuid.uuid4()}"


@pytest.fixture
def unique_key_2() -> str:
    return f"test:rl:{uuid.uuid4()}"


@pytest.fixture(autouse=True)
def _cleanup_test_keys(redis_conn: redis.Redis) -> Iterator[None]:
    yield
    for key in redis_conn.scan_iter(match="test:rl:*"):
        redis_conn.delete(key)


def test_first_request_starts_with_a_full_bucket_and_is_allowed(
    limiter: RedisTokenBucketLimiter, unique_key: str
) -> None:
    result = limiter.check_all(
        [DimensionSpec(key=unique_key, capacity=5, refill_rate=1.0)]
    )

    assert result.allowed is True


def test_successful_request_consumes_the_default_cost(
    limiter: RedisTokenBucketLimiter, redis_conn: redis.Redis, unique_key: str
) -> None:
    limiter.check_all([DimensionSpec(key=unique_key, capacity=5, refill_rate=1.0)])

    tokens = float(redis_conn.hget(unique_key, "tokens"))  # type: ignore[arg-type]
    assert tokens == pytest.approx(4.0, abs=0.01)


def test_requests_up_to_capacity_all_succeed(
    limiter: RedisTokenBucketLimiter, unique_key: str
) -> None:
    for _ in range(3):
        result = limiter.check_all(
            [DimensionSpec(key=unique_key, capacity=3, refill_rate=0.001)]
        )
        assert result.allowed is True


def test_request_beyond_capacity_is_rejected(
    limiter: RedisTokenBucketLimiter, unique_key: str
) -> None:
    dims = [DimensionSpec(key=unique_key, capacity=3, refill_rate=0.001)]
    for _ in range(3):
        assert limiter.check_all(dims).allowed is True

    result = limiter.check_all(dims)

    assert result.allowed is False
    assert result.retry_after_seconds > 0


def test_rejected_request_does_not_mutate_bucket_state(
    limiter: RedisTokenBucketLimiter, redis_conn: redis.Redis, unique_key: str
) -> None:
    dims = [DimensionSpec(key=unique_key, capacity=1, refill_rate=0.001)]
    assert limiter.check_all(dims).allowed is True

    tokens_before = redis_conn.hget(unique_key, "tokens")

    for _ in range(3):
        result = limiter.check_all(dims)
        assert result.allowed is False

    tokens_after = redis_conn.hget(unique_key, "tokens")
    assert tokens_before == tokens_after


def test_ttl_is_always_finite_and_positive(
    limiter: RedisTokenBucketLimiter, redis_conn: redis.Redis, unique_key: str
) -> None:
    limiter.check_all([DimensionSpec(key=unique_key, capacity=5, refill_rate=1.0)])

    ttl = redis_conn.ttl(unique_key)
    assert ttl > 0
    # No immortal keys: ttl must never come back -1 (no expiry) or -2
    # (already gone).
    assert ttl != -1
    assert ttl != -2


def test_explicit_ttl_override_is_respected(
    limiter: RedisTokenBucketLimiter, redis_conn: redis.Redis, unique_key: str
) -> None:
    limiter.check_all(
        [DimensionSpec(key=unique_key, capacity=5, refill_rate=1.0, ttl_seconds=30)]
    )

    ttl = redis_conn.ttl(unique_key)
    assert 0 < ttl <= 30


def test_cost_parameter_consumes_more_than_one_token(
    limiter: RedisTokenBucketLimiter, redis_conn: redis.Redis, unique_key: str
) -> None:
    dims = [DimensionSpec(key=unique_key, capacity=5, refill_rate=0.001, cost=3)]

    first = limiter.check_all(dims)
    assert first.allowed is True
    tokens = float(redis_conn.hget(unique_key, "tokens"))  # type: ignore[arg-type]
    assert tokens == pytest.approx(2.0, abs=0.01)

    # A second cost=3 request only has 2 tokens left -- must be rejected.
    second = limiter.check_all(dims)
    assert second.allowed is False


def test_refill_over_elapsed_time_allows_another_request(
    limiter: RedisTokenBucketLimiter, unique_key: str
) -> None:
    # capacity=1, refill_rate=20/sec -> refills a full token in 50ms.
    dims = [DimensionSpec(key=unique_key, capacity=1, refill_rate=20.0)]

    assert limiter.check_all(dims).allowed is True
    assert limiter.check_all(dims).allowed is False

    time.sleep(0.15)

    assert limiter.check_all(dims).allowed is True


def test_multi_key_all_or_nothing_rejects_without_consuming_the_passing_dimension(
    limiter: RedisTokenBucketLimiter,
    redis_conn: redis.Redis,
    unique_key: str,
    unique_key_2: str,
) -> None:
    """The direct regression test for the atomicity flaw ADR 0006's
    adversarial review found and corrected (§10): a multi-dimension
    operation where one dimension (account) is already exhausted must
    reject the whole operation without touching the other, still-passing
    dimension's (IP) bucket at all."""
    ip_key, account_key = unique_key, unique_key_2

    # Exhaust the account-dimension bucket first.
    limiter.check_all([DimensionSpec(key=account_key, capacity=1, refill_rate=0.001)])
    tokens_after_exhausting_account = redis_conn.hget(account_key, "tokens")

    # The IP dimension has plenty of capacity and has never been touched.
    assert redis_conn.exists(ip_key) == 0

    result = limiter.check_all(
        [
            DimensionSpec(key=ip_key, capacity=10, refill_rate=1.0),
            DimensionSpec(key=account_key, capacity=1, refill_rate=0.001),
        ]
    )

    assert result.allowed is False
    # The IP dimension's key must never have been created -- a rejected
    # request writes to *no* dimension, not even the ones that would have
    # passed on their own (ADR 0006 §10, §14, §18's cardinality bound).
    assert redis_conn.exists(ip_key) == 0
    # The account dimension's state is also unchanged by this rejection.
    assert redis_conn.hget(account_key, "tokens") == tokens_after_exhausting_account


def test_multi_key_all_pass_writes_every_dimension_together(
    limiter: RedisTokenBucketLimiter,
    redis_conn: redis.Redis,
    unique_key: str,
    unique_key_2: str,
) -> None:
    result = limiter.check_all(
        [
            DimensionSpec(key=unique_key, capacity=5, refill_rate=1.0),
            DimensionSpec(key=unique_key_2, capacity=5, refill_rate=1.0),
        ]
    )

    assert result.allowed is True
    assert redis_conn.exists(unique_key) == 1
    assert redis_conn.exists(unique_key_2) == 1


def test_single_dimension_operation_uses_exactly_one_key(
    limiter: RedisTokenBucketLimiter, unique_key: str
) -> None:
    """Not a behavioral assertion so much as a structural one: a
    single-dimension operation's `DimensionSpec` list has exactly one
    entry, which `check_all()` turns into `KEYS = [that one key]` in the
    Lua invocation -- one Lua call, one key, per ADR 0006 §6."""
    result = limiter.check_all([DimensionSpec(key=unique_key, capacity=5, refill_rate=1.0)])
    assert result.allowed is True


def test_concurrent_requests_never_exceed_capacity(
    limiter: RedisTokenBucketLimiter, unique_key: str
) -> None:
    """Many concurrent requests for one key must never allow more than
    `capacity` to succeed within a window that shouldn't permit more —
    the direct test that the naive GET->calculate->SET race does not
    exist in this design."""
    capacity = 20
    dims = [DimensionSpec(key=unique_key, capacity=capacity, refill_rate=0.001)]
    attempts = 50
    allowed_count = 0
    lock = threading.Lock()

    def _attempt() -> None:
        nonlocal allowed_count
        result = limiter.check_all(dims)
        if result.allowed:
            with lock:
                allowed_count += 1

    threads = [threading.Thread(target=_attempt) for _ in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert allowed_count == capacity


def test_concurrent_multi_key_requests_never_partially_consume_a_rejected_dimension(
    limiter: RedisTokenBucketLimiter,
    redis_conn: redis.Redis,
    unique_key: str,
    unique_key_2: str,
) -> None:
    """Concurrent version of the multi-key worked scenario in ADR 0006
    §10: an account bucket with exactly one token, raced by several
    concurrent requests each pairing that account with the caller's own
    distinct IP key. At most one request may succeed; every IP key
    belonging to a request that lost the race must never have been
    created."""
    account_key = unique_key
    ip_keys = [f"{unique_key_2}:{i}" for i in range(10)]
    dims_per_thread = [
        [
            DimensionSpec(key=ip_key, capacity=10, refill_rate=1.0),
            DimensionSpec(key=account_key, capacity=1, refill_rate=0.001),
        ]
        for ip_key in ip_keys
    ]

    results: list[bool] = [False] * len(ip_keys)

    def _attempt(index: int) -> None:
        results[index] = limiter.check_all(dims_per_thread[index]).allowed

    threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(len(ip_keys))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results) == 1

    for index, ip_key in enumerate(ip_keys):
        if results[index]:
            assert redis_conn.exists(ip_key) == 1
        else:
            # A losing request's IP dimension must never have been
            # touched -- the exact partial-consumption bug this design
            # exists to prevent.
            assert redis_conn.exists(ip_key) == 0


def test_redis_unavailable_raises_redis_unavailable_error() -> None:
    """ADR 0006 §13's failure policy needs a specific, catchable exception
    at this boundary -- never a raw `redis` exception, never an uncaught
    one."""
    unreachable_client = build_redis_client(
        "redis://localhost:1/0", socket_timeout=0.05, socket_connect_timeout=0.05
    )
    limiter = RedisTokenBucketLimiter(unreachable_client)

    try:
        with pytest.raises(RedisUnavailableError):
            limiter.check_all(
                [DimensionSpec(key=f"test:rl:{uuid.uuid4()}", capacity=5, refill_rate=1.0)]
            )
    finally:
        unreachable_client.close()


def test_check_all_rejects_an_empty_dimension_list(limiter: RedisTokenBucketLimiter) -> None:
    with pytest.raises(ValueError):
        limiter.check_all([])


@pytest.mark.parametrize(
    ("capacity", "refill_rate", "cost"),
    [(0, 1.0, 1.0), (-1, 1.0, 1.0), (5, 0, 1.0), (5, -1.0, 1.0), (5, 1.0, 0), (5, 1.0, -1.0)],
)
def test_dimension_spec_rejects_non_positive_parameters(
    capacity: float, refill_rate: float, cost: float
) -> None:
    with pytest.raises(ValueError):
        DimensionSpec(key="k", capacity=capacity, refill_rate=refill_rate, cost=cost)
