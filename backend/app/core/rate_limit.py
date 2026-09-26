"""Rate limiting for auth endpoints.

`FixedWindowRateLimiter` is the in-process limiter that has run this
project's rate limiting since Issue #2 — correct for the single-process
deployment this project runs today (see
infra/docker/backend.Dockerfile's entrypoint: one `uvicorn` process, no
`--workers`). It remains the **fallback** implementation (ADR 0006 §6,
§13), not dead code: every `enforce_*_rate_limit` dependency below falls
back to it whenever Redis is unconfigured or unreachable.

`RedisTokenBucketLimiter` (ADR 0006 §8/§10) is the distributed engine:
one atomic Lua (`EVAL`) invocation per *operation*, over every dimension
key that operation has, evaluating every dimension before writing any of
them, so a rejected request never partially consumes a dimension it
happened to pass.

**Slice 2: the Redis engine is wired into every `enforce_*_rate_limit`
dependency**, per ADR 0006 §6's flow and §13's operation-aware failure
policy — see `_check_or_fallback()` and each `enforce_*` function below
for exactly how.

**Slice 3b: the deterministic abuse-decision layer (ADR 0006 §11/§12,
`app.core.abuse_decision`) is now also consulted, but only for `login`,
`forgot-password`, and `reset-password`** — no rule targets `register`/
`refresh`, so `enforce_register_rate_limit`/`enforce_refresh_rate_limit`
are unchanged. For the three affected operations: an active
`TEMPORARY_BLOCK` rejects the request before the base bucket is ever
consulted; any active `STRICT_THROTTLE` dimension is folded into the
*same* `check_all()` invocation as the base dimension(s), never a
separate Redis round trip (see `abuse_decision.check()`'s own docstring
for why that atomicity matters). Recording an outcome after the request
completes is the endpoint layer's responsibility
(`app/api/v1/auth.py`), not this module's — see that module for exactly
when.

**Failure-policy interpretation, recorded here because ADR 0006 §13
explicitly left it open ("whether register should actually share Tier
A's fallback instead is a reasonable alternative"):** this implementation
distinguishes "Redis was never configured for this deployment"
(`get_redis_client()` returns `None`) from "Redis is configured but is
currently unreachable" (`RedisTokenBucketLimiter.check_all()` raises
`RedisUnavailableError`). Only the second case triggers ADR §13's
per-tier policy (Tier A falls back to `FixedWindowRateLimiter`; Tier B —
`register` — fails open). The first case *always* falls back to
`FixedWindowRateLimiter`, for every operation including `register`,
identically to this module's pre-slice-2 behavior. Rationale: `REDIS_URL`
defaults to unset, so treating "never configured" the same as "Tier B's
mid-outage fail-open" would mean `register` has *zero* rate limiting by
default in every environment that hasn't explicitly opted into Redis —
an unacceptable regression of `docs/SECURITY.md` principle 8 for a
default state, not an outage. Tier B's genuine fail-open behavior is
reserved for its intended scenario: a deployment that *has* chosen
Redis-backed limiting hitting a transient outage ("a Redis blip", per the
ADR's own phrasing).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Sequence

import redis
from fastapi import Depends, HTTPException, Request, status

from app.core.abuse_decision import AbuseContext
from app.core.abuse_decision import check as abuse_check
from app.core.config import get_settings
from app.core.cookies import REFRESH_TOKEN_COOKIE
from app.core.ip_resolution import resolve_client_ip
from app.core.redis_client import RedisUnavailableError, get_redis_client
from app.core.redis_keys import hash_account_identifier, rate_limit_key
from app.core.security import parse_refresh_token
from app.core.token_bucket_types import DimensionSpec as DimensionSpec
from app.core.token_bucket_types import TokenBucketResult as TokenBucketResult

logger = logging.getLogger("app.rate_limit")


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

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
# Their (limit, window_seconds) pairs are also where the Redis-backed
# engine's capacity/refill-rate numbers come from (ADR 0006 §8's
# "Continuity with today's numbers") — see `_dimension_for()` below, which
# reads `.limit`/`.window_seconds` from these same objects rather than
# duplicating the numbers.
login_rate_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)
register_rate_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)
refresh_rate_limiter = FixedWindowRateLimiter(limit=20, window_seconds=60)
forgot_password_rate_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)
reset_password_rate_limiter = FixedWindowRateLimiter(limit=10, window_seconds=60)
# Issue #3, Slice 3.3 — document upload. Authenticated and materially more
# expensive (disk I/O + DB write) than register/login, so it gets Tier A
# semantics (falls back on a Redis outage, never fails open) rather than
# register's Tier B — see enforce_document_upload_rate_limit() below.
upload_rate_limiter = FixedWindowRateLimiter(limit=20, window_seconds=60)
# Issue #3, Slice 3.4 — document processing (text extraction). CPU-bound
# synchronous work, not just I/O like upload -- a member repeatedly
# triggering re-processing of the same (or a large) document is a
# self-service resource-exhaustion vector on shared infrastructure, not
# just a per-workspace cost. Same numbers as upload pending real usage
# data; Tier A for the same reason (a defensive control, not UX).
process_rate_limiter = FixedWindowRateLimiter(limit=20, window_seconds=60)
# Issue #4, Slice 4.3 — posting a conversation message (retrieval +
# generation). Same reasoning as document processing: CPU-bound
# (embedding the query, reranking) and a real per-call compute cost
# (a future real LLM/reranker provider would also be a metered external
# call) -- Tier A, same numbers pending real usage data.
conversation_message_rate_limiter = FixedWindowRateLimiter(limit=20, window_seconds=60)
# Issue #6 — posting a voice message (STT + the same retrieval/generation
# work as a text message). Strictly more expensive than
# `conversation_message` (adds a real transcription pass over the
# uploaded audio), so it gets its own dimension rather than sharing one,
# but the same Tier A numbers pending real usage data.
voice_message_rate_limiter = FixedWindowRateLimiter(limit=20, window_seconds=60)


def client_ip(request: Request) -> str:
    """The direct TCP peer, with no trusted-proxy handling.

    Still used by call sites outside the rate limiter (audit logging,
    session IP recording in `app/api/v1/auth.py`) — deliberately left
    unchanged in this slice, which only wires `resolve_client_ip()` (ADR
    0006 §9a) into the rate-limit dependencies below. Changing what IP
    address audit logs/sessions record is a separate decision, out of
    scope here.
    """
    if request.client is not None:
        return request.client.host
    return "unknown"


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

# DimensionSpec/TokenBucketResult now live in `token_bucket_types.py`
# (Slice 3b — breaks an import cycle with `abuse_state.py`/
# `abuse_decision.py`, see that module's docstring). Re-exported here
# unchanged so every existing `from app.core.rate_limit import
# DimensionSpec` call site keeps working.


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


# --- Endpoint wiring (ADR 0006 §6, §9, §13) ----------------------------------


def _dimension(
    operation: str, dimension: str, value: str, limiter: FixedWindowRateLimiter
) -> DimensionSpec:
    """Build a `DimensionSpec` whose capacity/refill-rate are derived
    live from an existing `FixedWindowRateLimiter`'s own numbers (ADR
    0006 §8's "Continuity with today's numbers") — never a second,
    independently-maintained copy of the same limit."""
    return DimensionSpec(
        key=rate_limit_key(operation, dimension, value),
        capacity=limiter.limit,
        refill_rate=limiter.limit / limiter.window_seconds,
    )


async def _extract_email_from_json_body(request: Request) -> str | None:
    """Best-effort peek at a JSON request body's `email` field, for the
    account dimension (ADR 0006 §9's `login`/`forgot-password` rows).

    Deliberately tolerant of any parse failure: this is a hint used to
    build a *stronger* rate-limit key when possible, never a validator —
    a malformed body still reaches the endpoint's own Pydantic validation
    afterward (`Request.json()`/`.body()` cache the raw bytes, so reading
    them here doesn't consume them). On any failure, callers simply fall
    back to the IP-only dimension.
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - untrusted input, any parse failure means "no email available"
        return None
    if not isinstance(body, dict):
        return None
    email = body.get("email")
    if not isinstance(email, str) or not email:
        return None
    return email


def _log_redis_fallback(*, operation: str, fail_open: bool) -> None:
    """ADR 0006 §13 ("Mechanics common to both tiers"): a Redis-failure
    fallback event must be observable via structured logging — not a
    Postgres audit row, which §15 reserves for abuse-layer escalations,
    not ordinary degraded operation. This is the only signal an operator
    gets that the rate limiter has fallen back to the in-process limiter
    for an already-configured Redis that's currently unreachable.

    Deliberately logs only the fixed, non-secret operation name and
    which failure-policy tier applied — never a request-derived value
    (email, IP, token, session ID), consistent with this codebase's
    existing logging convention (see `auth_service.py`'s `logger.info`
    calls, which log `user_id`, never raw email/password).
    """
    logger.warning(
        "redis_rate_limit_unavailable",
        extra={
            "operation": operation,
            "policy": "fail_open" if fail_open else "fallback_to_in_process_limiter",
        },
    )


def _check_or_fallback(
    *,
    operation: str,
    dimensions: list[DimensionSpec],
    redis_client: redis.Redis | None,
    fallback: FixedWindowRateLimiter,
    fallback_key: str,
    fail_open_on_redis_error: bool,
) -> None:
    """ADR 0006 §13's operation-aware failure policy, applied uniformly.

    `redis_client is None` (Redis never configured for this deployment)
    always falls back to `fallback.check()` — see the module docstring
    for why this is treated differently from a genuine mid-request
    `RedisUnavailableError`, where `fail_open_on_redis_error` selects
    Tier A (`False` — fall back) vs. Tier B (`True` — fail open,
    `register` only). Only the second case is logged (`_log_redis_fallback`)
    — Redis never being configured at all is this deployment's normal,
    expected default, not a degradation worth a log line on every request.
    """
    if redis_client is None:
        fallback.check(fallback_key)
        return

    limiter = RedisTokenBucketLimiter(redis_client)
    try:
        result = limiter.check_all(dimensions)
    except RedisUnavailableError:
        _log_redis_fallback(operation=operation, fail_open=fail_open_on_redis_error)
        if fail_open_on_redis_error:
            return
        fallback.check(fallback_key)
        return

    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )


async def enforce_register_rate_limit(
    request: Request,
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> None:
    """Tier B (ADR 0006 §13): fails open on a genuine Redis outage — see
    the module docstring for why "never configured" is not treated as
    that outage."""
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)

    _check_or_fallback(
        operation="register",
        dimensions=[_dimension("register", "ip", ip, register_rate_limiter)],
        redis_client=redis_client,
        fallback=register_rate_limiter,
        fallback_key=ip,
        fail_open_on_redis_error=True,
    )


async def enforce_login_rate_limit(
    request: Request,
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> None:
    """Tier A (ADR 0006 §13). Dimensions per ADR §9: IP, and the
    submitted email (keyed HMAC, §14) when it's extractable.

    Also consults the abuse-decision layer (ADR 0006 §11/§12, Slice 3b)
    ahead of the base check: an active TEMPORARY_BLOCK (R3) rejects the
    request outright; any active STRICT_THROTTLE dimension (R1/R2) is
    folded into the same `check_all()` invocation as the base
    dimensions, so strict-bucket consumption stays atomic with the base
    bucket's own consumption.
    """
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)
    email = await _extract_email_from_json_body(request)
    account_hash = (
        hash_account_identifier(email, key=settings.rate_limit_hash_key_resolved.encode("utf-8"))
        if email is not None
        else None
    )

    decision = abuse_check(
        redis_client, AbuseContext(operation="login", ip=ip, account_hash=account_hash)
    )
    if decision.temporary_blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )

    dimensions = [_dimension("login", "ip", ip, login_rate_limiter)]
    if account_hash is not None:
        dimensions.append(_dimension("login", "acct", account_hash, login_rate_limiter))
    dimensions.extend(decision.strict_dimensions)

    _check_or_fallback(
        operation="login",
        dimensions=dimensions,
        redis_client=redis_client,
        fallback=login_rate_limiter,
        fallback_key=ip,
        fail_open_on_redis_error=False,
    )


def enforce_refresh_rate_limit(
    request: Request,
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> None:
    """Tier A (ADR 0006 §13). Dimensions per ADR §9: session ID (parsed
    from the refresh-token cookie without a DB round-trip — ADR §7) and
    IP, when the cookie is present and well-formed."""
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)

    dimensions = [_dimension("refresh", "ip", ip, refresh_rate_limiter)]
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if raw_refresh_token is not None:
        parsed = parse_refresh_token(raw_refresh_token)
        if parsed is not None:
            session_id, _secret = parsed
            dimensions.append(
                _dimension("refresh", "session", str(session_id), refresh_rate_limiter)
            )

    _check_or_fallback(
        operation="refresh",
        dimensions=dimensions,
        redis_client=redis_client,
        fallback=refresh_rate_limiter,
        fallback_key=ip,
        fail_open_on_redis_error=False,
    )


async def enforce_forgot_password_rate_limit(
    request: Request,
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> None:
    """Tier A (ADR 0006 §13). Dimensions per ADR §9: IP, and the
    submitted email (keyed HMAC, §14) when it's extractable.

    Also consults the abuse-decision layer (Slice 3b): no TEMPORARY_BLOCK
    rule targets `forgot-password`, but an active STRICT_THROTTLE (R4) is
    folded into the same `check_all()` invocation as the base dimensions.
    """
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)
    email = await _extract_email_from_json_body(request)
    account_hash = (
        hash_account_identifier(email, key=settings.rate_limit_hash_key_resolved.encode("utf-8"))
        if email is not None
        else None
    )

    decision = abuse_check(
        redis_client, AbuseContext(operation="forgot-password", ip=ip, account_hash=account_hash)
    )
    # No TEMPORARY_BLOCK rule targets forgot-password (see
    # abuse_decision._BLOCK_DIMENSIONS), so decision.temporary_blocked is
    # always False here -- no rejection branch needed, only the strict
    # dimension fold-in below.

    dimensions = [_dimension("forgot-password", "ip", ip, forgot_password_rate_limiter)]
    if account_hash is not None:
        dimensions.append(
            _dimension("forgot-password", "acct", account_hash, forgot_password_rate_limiter)
        )
    dimensions.extend(decision.strict_dimensions)

    _check_or_fallback(
        operation="forgot-password",
        dimensions=dimensions,
        redis_client=redis_client,
        fallback=forgot_password_rate_limiter,
        fallback_key=ip,
        fail_open_on_redis_error=False,
    )


def enforce_reset_password_rate_limit(
    request: Request,
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> None:
    """Tier A (ADR 0006 §13). IP only per ADR §9 — the reset token's own
    256-bit entropy is the real defense; see the ADR for why dimensioning
    by token or account isn't used here.

    Also consults the abuse-decision layer (Slice 3b): an active
    TEMPORARY_BLOCK (R5) rejects the request outright. No STRICT_THROTTLE
    rule targets `reset-password`.
    """
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)

    decision = abuse_check(redis_client, AbuseContext(operation="reset-password", ip=ip))
    if decision.temporary_blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )

    _check_or_fallback(
        operation="reset-password",
        dimensions=[_dimension("reset-password", "ip", ip, reset_password_rate_limiter)],
        redis_client=redis_client,
        fallback=reset_password_rate_limiter,
        fallback_key=ip,
        fail_open_on_redis_error=False,
    )


def enforce_document_upload_rate_limit(
    request: Request,
    *,
    user_id: uuid.UUID,
    redis_client: redis.Redis | None,
) -> None:
    """Tier A (ADR 0006 §13) — IP + authenticated user ID.

    Deliberately a plain function, not itself a `Depends()`-shaped FastAPI
    dependency: it needs the authenticated caller's ID, which is only
    available after `require_workspace_role` has already run. Importing
    `get_current_user` here to make this self-contained would create a
    circular import (`app.core.dependencies` already imports `client_ip`
    from this module) — the same class of cycle `token_bucket_types.py`
    was extracted to solve for the abuse layer. The route calls this
    explicitly, after its own `WorkspaceContext` dependency has resolved,
    passing `redis_client` through from its own `Depends(get_redis_client)`
    parameter so tests can override it exactly like every other
    `enforce_*` function here.

    No abuse-decision-layer consultation — R1–R5 target the
    login/forgot-password/reset-password credential-stuffing threat model
    specifically; uploading a file doesn't fit it, and extending that
    closed rule table isn't warranted for this operation.
    """
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)

    dimensions = [
        _dimension("document_upload", "ip", ip, upload_rate_limiter),
        _dimension("document_upload", "user", str(user_id), upload_rate_limiter),
    ]

    _check_or_fallback(
        operation="document_upload",
        dimensions=dimensions,
        redis_client=redis_client,
        fallback=upload_rate_limiter,
        fallback_key=str(user_id),
        fail_open_on_redis_error=False,
    )


def enforce_document_process_rate_limit(
    request: Request,
    *,
    user_id: uuid.UUID,
    redis_client: redis.Redis | None,
) -> None:
    """Tier A (ADR 0006 §13) — IP + authenticated user ID. Same shape and
    rationale as `enforce_document_upload_rate_limit()` above, including
    why this is a plain function rather than a `Depends()`-shaped
    dependency."""
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)

    dimensions = [
        _dimension("document_process", "ip", ip, process_rate_limiter),
        _dimension("document_process", "user", str(user_id), process_rate_limiter),
    ]

    _check_or_fallback(
        operation="document_process",
        dimensions=dimensions,
        redis_client=redis_client,
        fallback=process_rate_limiter,
        fallback_key=str(user_id),
        fail_open_on_redis_error=False,
    )


def enforce_conversation_message_rate_limit(
    request: Request,
    *,
    user_id: uuid.UUID,
    redis_client: redis.Redis | None,
) -> None:
    """Tier A (ADR 0006 §13) — IP + authenticated user ID. Same shape and
    rationale as `enforce_document_process_rate_limit()` above."""
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)

    dimensions = [
        _dimension("conversation_message", "ip", ip, conversation_message_rate_limiter),
        _dimension("conversation_message", "user", str(user_id), conversation_message_rate_limiter),
    ]

    _check_or_fallback(
        operation="conversation_message",
        dimensions=dimensions,
        redis_client=redis_client,
        fallback=conversation_message_rate_limiter,
        fallback_key=str(user_id),
        fail_open_on_redis_error=False,
    )


def enforce_voice_message_rate_limit(
    request: Request,
    *,
    user_id: uuid.UUID,
    redis_client: redis.Redis | None,
) -> None:
    """Tier A (ADR 0006 §13) — IP + authenticated user ID. Same shape and
    rationale as `enforce_conversation_message_rate_limit()` above."""
    settings = get_settings()
    ip = resolve_client_ip(request, settings.trusted_proxy_cidrs_list)

    dimensions = [
        _dimension("voice_message", "ip", ip, voice_message_rate_limiter),
        _dimension("voice_message", "user", str(user_id), voice_message_rate_limiter),
    ]

    _check_or_fallback(
        operation="voice_message",
        dimensions=dimensions,
        redis_client=redis_client,
        fallback=voice_message_rate_limiter,
        fallback_key=str(user_id),
        fail_open_on_redis_error=False,
    )
