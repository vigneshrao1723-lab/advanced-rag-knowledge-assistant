"""Redis connection abstraction (ADR 0006 §7, §13).

A single, small wrapping point for the Redis client the distributed rate
limiter uses — per ADR 0006 §6, raw `redis-py` calls must not be scattered
throughout the application; everything that needs Redis goes through this
module (for the connection itself) and `app.core.rate_limit`
(`RedisTokenBucketLimiter`, for the actual rate-limit operations).

Redis is optional infrastructure at this point in the project (see
`docs/SECURITY.md` "Rate limiting approach"): nothing in the running
application currently depends on it (the Redis-backed limiter is not wired
into any endpoint yet — ADR 0006 "Implementation status"). `REDIS_URL`
being unset simply means `get_redis_client()` returns `None`; callers must
treat that identically to "Redis is unreachable" and fall back per ADR
0006 §13's failure policy — never let a raw `redis` exception escape past
this module's boundary.
"""

from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import get_settings


class RedisUnavailableError(RuntimeError):
    """Raised at the rate-limiter boundary when Redis cannot be reached.

    Callers (ADR 0006 §13) catch this specifically and apply the
    operation-aware failure policy — it is never allowed to propagate as
    an uncaught exception into FastAPI's generic error handling.
    """


def build_redis_client(
    url: str, *, socket_timeout: float, socket_connect_timeout: float
) -> redis.Redis:
    """Construct a Redis client against an explicit URL and explicit,
    short timeouts — never hardcoded, always passed in by the caller (the
    application's own settings, or a test's own configuration)."""
    return redis.Redis.from_url(
        url,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        decode_responses=False,
    )


@lru_cache
def get_redis_client() -> redis.Redis | None:
    """The application-wide Redis client, or `None` if `REDIS_URL` is not
    configured for this deployment. Cached like `get_settings()` — one
    connection pool per process, not one per call."""
    settings = get_settings()
    if not settings.redis_url:
        return None
    return build_redis_client(
        settings.redis_url,
        socket_timeout=settings.redis_socket_timeout_seconds,
        socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
    )


def is_redis_available(client: redis.Redis | None) -> bool:
    """A clean, exception-free reachability check (ADR 0006 §13's failure
    policy needs this at the boundary of the request path, not an
    uncaught exception from deep inside `redis-py`).

    Deliberately does **not** back `/api/v1/health/ready` — ADR 0006 §13
    is explicit that general readiness must stay independent of Redis, so
    this function exists only for the rate limiter's own internal use.
    """
    if client is None:
        return False
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False
