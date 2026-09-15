"""Rate limiting for auth endpoints.

`FixedWindowRateLimiter` is the in-process limiter that has run this
project's rate limiting since Issue #2 — correct for the single-process
deployment this project runs today (see
infra/docker/backend.Dockerfile's entrypoint: one `uvicorn` process, no
`--workers`). Every `enforce_*_rate_limit` function below is unchanged
from that behavior in this slice.

`RedisTokenBucketLimiter` (ADR 0006 §8/§10) is the distributed engine
this slice adds: one atomic Lua (`EVAL`) invocation per *operation*, over
every dimension key that operation has, evaluating every dimension
before writing any of them, so a rejected request never partially
consumes a dimension it happened to pass. **Not wired into any endpoint
yet** — same scope boundary as `app/core/redis_client.py` and
`app/core/ip_resolution.py`; wiring this engine into
`enforce_*_rate_limit` is a separate, later, reviewed slice.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import redis
from fastapi import HTTPException, Request, status

from app.core.redis_client import RedisUnavailableError


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
forgot_password_rate_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)
reset_password_rate_limiter = FixedWindowRateLimiter(limit=10, window_seconds=60)


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


def enforce_forgot_password_rate_limit(request: Request) -> None:
    forgot_password_rate_limiter.check(client_ip(request))


def enforce_reset_password_rate_limit(request: Request) -> None:
    reset_password_rate_limiter.check(client_ip(request))


# --- Redis-backed distributed token bucket (ADR 0006 §8, §10) ---------------

_TOKEN_BUCKET_LUA = """
-- KEYS[i]: rate-limit bucket hash key for dimension i
-- ARGV: for i=1..#KEYS, four values in order:
--   capacity_i, refill_rate_i (tokens/sec), cost_i, ttl_i (seconds)
-- Returns: {allowed (1 or 0), retry_after_ms (integer, 0 when allowed)}
--
-- ADR 0006 sections 8/10: reads and refills every dimension first, checks
-- all of them, and only writes to any of them if every dimension passes. A
-- rejected request never mutates any bucket, for any dimension -- this is
-- check-before-write, not write-then-rollback.

local now = redis.call('TIME')
local now_seconds = tonumber(now[1]) + (tonumber(now[2]) / 1000000)

local n = #KEYS
local refilled = {}
local allowed = true
local max_wait_ms = 0

for i = 1, n do
    local key = KEYS[i]
    local capacity = tonumber(ARGV[(i - 1) * 4 + 1])
    local refill_rate = tonumber(ARGV[(i - 1) * 4 + 2])
    local cost = tonumber(ARGV[(i - 1) * 4 + 3])

    local bucket = redis.call('HMGET', key, 'tokens', 'last_refill_at')
    local tokens
    local last_refill_at

    if bucket[1] == false then
        -- No existing key: first request for this dimension starts with
        -- a full bucket -- never penalized for a Redis restart or a
        -- prior key's TTL expiry.
        tokens = capacity
        last_refill_at = now_seconds
    else
        tokens = tonumber(bucket[1])
        last_refill_at = tonumber(bucket[2])
    end

    local elapsed = now_seconds - last_refill_at
    if elapsed < 0 then
        elapsed = 0
    end

    local current = math.min(capacity, tokens + elapsed * refill_rate)
    refilled[i] = current

    if current < cost then
        allowed = false
        local wait_ms = math.ceil(((cost - current) / refill_rate) * 1000)
        if wait_ms > max_wait_ms then
            max_wait_ms = wait_ms
        end
    end
end

if not allowed then
    -- At least one dimension failed -- nothing computed above is written.
    return {0, max_wait_ms}
end

for i = 1, n do
    local key = KEYS[i]
    local cost = tonumber(ARGV[(i - 1) * 4 + 3])
    local ttl = tonumber(ARGV[(i - 1) * 4 + 4])
    local remaining = refilled[i] - cost
    redis.call('HSET', key, 'tokens', remaining, 'last_refill_at', now_seconds)
    redis.call('EXPIRE', key, ttl)
end

return {1, 0}
"""

_TTL_SAFETY_FACTOR = 2.0


@dataclass(frozen=True)
class DimensionSpec:
    """One dimension's bucket parameters for a single operation check.

    `ttl_seconds`, if not given, is derived from `capacity`/`refill_rate`
    (ADR 0006 §10: "comfortably longer than the time to fully refill from
    empty") so every bucket key this design creates always has a finite
    TTL — no immortal Redis keys.
    """

    key: str
    capacity: float
    refill_rate: float
    cost: float = 1.0
    ttl_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError(f"capacity must be > 0 for key {self.key!r}.")
        if self.refill_rate <= 0:
            raise ValueError(f"refill_rate must be > 0 for key {self.key!r}.")
        if self.cost <= 0:
            raise ValueError(f"cost must be > 0 for key {self.key!r}.")
        if self.ttl_seconds is not None and self.ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0 for key {self.key!r}.")

    def resolved_ttl_seconds(self) -> int:
        if self.ttl_seconds is not None:
            return self.ttl_seconds
        return max(1, math.ceil((self.capacity / self.refill_rate) * _TTL_SAFETY_FACTOR))


@dataclass(frozen=True)
class TokenBucketResult:
    allowed: bool
    retry_after_seconds: float


class RedisTokenBucketLimiter:
    """ADR 0006 §8/§10's token-bucket engine: one Lua script invocation
    per *operation*, parameterized over every dimension key that
    operation has.

    A single-dimension operation passes one `DimensionSpec` to
    `check_all()`; a multi-dimension operation passes several together in
    the same call -- there is deliberately no per-dimension `check()`
    method, since that shape is exactly the atomicity flaw ADR 0006's
    adversarial review found and corrected (§10).
    """

    def __init__(self, client: redis.Redis) -> None:
        self._client = client
        self._script = client.register_script(_TOKEN_BUCKET_LUA)

    def check_all(self, dimensions: Sequence[DimensionSpec]) -> TokenBucketResult:
        if not dimensions:
            raise ValueError("check_all() requires at least one dimension.")

        keys = [dimension.key for dimension in dimensions]
        argv: list[float | int] = []
        for dimension in dimensions:
            argv.extend(
                [
                    dimension.capacity,
                    dimension.refill_rate,
                    dimension.cost,
                    dimension.resolved_ttl_seconds(),
                ]
            )

        try:
            raw_result = self._script(keys=keys, args=argv)
        except redis.RedisError as exc:
            raise RedisUnavailableError(str(exc)) from exc

        allowed_flag, retry_after_ms = raw_result
        return TokenBucketResult(
            allowed=bool(allowed_flag),
            retry_after_seconds=float(retry_after_ms) / 1000.0,
        )
