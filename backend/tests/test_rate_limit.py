from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from app.core.rate_limit import FixedWindowRateLimiter


def test_allows_requests_under_the_limit() -> None:
    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60)

    for _ in range(3):
        limiter.check("client-a")  # must not raise


def test_blocks_requests_over_the_limit() -> None:
    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("client-a")

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("client-a")

    assert exc_info.value.status_code == 429


def test_limits_are_tracked_independently_per_key() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60)

    limiter.check("client-a")
    limiter.check("client-b")  # different key — must not raise


def test_window_expiry_allows_requests_again() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=0.05)

    limiter.check("client-a")
    with pytest.raises(HTTPException):
        limiter.check("client-a")

    time.sleep(0.1)
    limiter.check("client-a")  # window has passed — must not raise
