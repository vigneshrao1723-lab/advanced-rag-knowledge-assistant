"""In-process rate limiting for auth endpoints.

Per docs/SECURITY.md "Rate limiting approach": no external session/cache
store (Redis) is introduced for this. This is a fixed-window limiter held in
application memory — correct for the single-process deployment this
project runs today (see infra/docker/backend.Dockerfile's entrypoint: one
`uvicorn` process, no `--workers`). If a future measured requirement needs
distributed rate limiting, that is a new ADR, not a silent change here.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.monotonic()
        window_start = now - self._window_seconds
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.pop(0)

        if len(hits) >= self._limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Try again later.",
            )

        hits.append(now)

    def reset(self) -> None:
        """Test-only: clear all recorded hits."""
        self._hits.clear()


# Separate limiters per endpoint so a burst on one doesn't lock out another.
login_rate_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)
register_rate_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)
refresh_rate_limiter = FixedWindowRateLimiter(limit=20, window_seconds=60)


def client_ip(request: Request) -> str:
    if request.client is not None:
        return request.client.host
    return "unknown"


def enforce_login_rate_limit(request: Request) -> None:
    login_rate_limiter.check(client_ip(request))


def enforce_register_rate_limit(request: Request) -> None:
    register_rate_limiter.check(client_ip(request))


def enforce_refresh_rate_limit(request: Request) -> None:
    refresh_rate_limiter.check(client_ip(request))
