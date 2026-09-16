from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import redis

from app.core.redis_client import build_redis_client, is_redis_available

_REDIS_URL = os.environ["REDIS_URL"]  # set by conftest.py / the environment


@pytest.fixture
def redis_client() -> Iterator[redis.Redis]:
    client = build_redis_client(_REDIS_URL, socket_timeout=1.0, socket_connect_timeout=1.0)
    yield client
    client.close()


def test_is_redis_available_returns_true_for_a_reachable_redis(redis_client: redis.Redis) -> None:
    assert is_redis_available(redis_client) is True


def test_is_redis_available_returns_false_for_none() -> None:
    assert is_redis_available(None) is False


def test_is_redis_available_returns_false_without_raising_for_unreachable_redis() -> None:
    """ADR 0006 §13: a Redis failure must never surface as an uncaught
    exception -- this is the boundary function every failure-aware caller
    relies on to stay exception-free."""
    unreachable = build_redis_client(
        "redis://localhost:1/0", socket_timeout=0.05, socket_connect_timeout=0.05
    )

    try:
        assert is_redis_available(unreachable) is False
    finally:
        unreachable.close()


def test_build_redis_client_applies_explicit_timeouts(redis_client: redis.Redis) -> None:
    connection_kwargs = redis_client.get_connection_kwargs()
    assert connection_kwargs["socket_timeout"] == 1.0
    assert connection_kwargs["socket_connect_timeout"] == 1.0
