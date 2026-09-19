"""Atomic Redis primitives for the deterministic abuse-protection layer
(ADR 0006 §11/§12 — Slice 3a: foundation only).

**Scope boundary, stated explicitly per the reviewed implementation
plan:** this module has no knowledge of R1-R5 as named rules, no rule
table, and no endpoint wiring. It exposes generic, parameterized
primitives — "record a failure against this counter, escalate past this
threshold" — that a later, separate slice (`AbuseDecisionEngine`, the
R1-R5 rule table, and its wiring into `enforce_*_rate_limit`) will call
with the approved concrete threshold/window values. Nothing in this
module hardcodes a threshold, a window, or which operation maps to which
rule.

**What is intentionally fixed here, not left to the caller:** the
*mechanics* of the two escalation types themselves — STRICT_THROTTLE's
token-bucket shape (capacity/refill/TTL) and TEMPORARY_BLOCK's flag
shape — since ADR 0006 defines exactly one shape for each, used
uniformly by every rule that produces it. Only *which counter* and
*what threshold* varies per rule; that variation is the caller's
responsibility, not this module's.

**Failure boundary, matching `app/core/redis_client.py`'s own contract
exactly:** every function here raises `RedisUnavailableError` on any
`redis.RedisError` — it never lets a raw `redis` exception escape, and
it never silently swallows one into a fabricated "success". Deciding
*what to do* about that error (fail open, fall back, log) is explicitly
out of scope for this slice — there is no `check()`/`AbuseDecisionEngine`
yet for that policy to live in. A caller in a later slice must catch
`RedisUnavailableError` at its own boundary, exactly as
`_check_or_fallback()` already does today for the rate limiter.

**Multi-signal atomicity (ADR 0006's `CHECK ALL -> DECIDE -> WRITE ALL`
principle, extended from the token-bucket engine to this layer):** a
single login failure can affect three independent signals at once (the
IP failcount, the account failcount, and the account's distinct-IP
HyperLogLog) plus up to three escalation writes. `record_login_failure()`
performs all of this in **one** Lua invocation — Redis's single-threaded
script execution means no other command from any client can observe or
interleave with any of these keys partway through. There is no
plausible mid-script failure path here (every key touched by a given
script is used by that script's own operations only, by construction of
the key namespace above — never a different Redis data type sharing a
key with another use), so the atomicity guarantee holds without needing
a rollback strategy, the same reasoning already established for
`_TOKEN_BUCKET_LUA`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import redis

from app.core.abuse_keys import block_key, distinct_ips_key, failcount_key, strict_throttle_key
from app.core.redis_client import RedisUnavailableError
from app.core.token_bucket_types import DimensionSpec

# STRICT_THROTTLE's token-bucket shape (ADR 0006, approved parameters) —
# uniform across every rule that produces this state (R1, R2, R4); not a
# per-rule value, so it lives here rather than being passed in by callers.
STRICT_THROTTLE_CAPACITY = 2.0
STRICT_THROTTLE_REFILL_RATE = 2.0 / 600  # 2 tokens per 600 seconds

# TTL for the strict-throttle bucket, derived the same way ordinary `rl:*`
# buckets already derive theirs -- reusing `DimensionSpec.resolved_ttl_seconds()`
# and its `_TTL_SAFETY_FACTOR` rather than duplicating that formula here.
# capacity/refill_rate = 600s; x2.0 safety factor = 1200s (20 minutes).
_STRICT_THROTTLE_TTL_SECONDS = DimensionSpec(
    key="_unused_only_for_ttl_derivation",
    capacity=STRICT_THROTTLE_CAPACITY,
    refill_rate=STRICT_THROTTLE_REFILL_RATE,
).resolved_ttl_seconds()

# TEMPORARY_BLOCK's flag TTL (ADR 0006, approved parameters) -- a fixed
# duration, not derived from anything (there is no "refill" concept for
# a flag). "No manual unblock" per ADR §12: this TTL is the only way a
# block ever lifts.
TEMPORARY_BLOCK_TTL_SECONDS = 600


@dataclass(frozen=True)
class LoginFailureResult:
    """Result of `record_login_failure()`. `*_newly_escalated` is True
    only on the exact call whose increment first crossed that signal's
    threshold -- never on a later call while already escalated (the
    Lua script uses `HSETNX`/`SETNX` to distinguish "just created" from
    "already existed"). This is the signal a future audit-writing layer
    needs to avoid writing a duplicate escalation row on every
    subsequent already-escalated failure."""

    ip_failure_count: int
    account_failure_count: int
    distinct_ip_count: int
    ip_strict_throttle_newly_escalated: bool
    account_strict_throttle_newly_escalated: bool
    account_temporary_block_newly_escalated: bool


@dataclass(frozen=True)
class SingleDimensionFailureResult:
    """Result of `record_ip_failure()` — the single-counter, single-
    escalation shape shared by R4 (forgot-password, STRICT_THROTTLE) and
    R5 (reset-password, TEMPORARY_BLOCK)."""

    failure_count: int
    newly_escalated: bool


# --- record login failure: IP + account failcounts, distinct-IP HLL ---------

_RECORD_LOGIN_FAILURE_LUA = """
-- KEYS[1] = ip failcount key
-- KEYS[2] = account failcount key
-- KEYS[3] = account distinct-IPs HyperLogLog key
-- KEYS[4] = ip strict-throttle bucket key
-- KEYS[5] = account strict-throttle bucket key
-- KEYS[6] = account temporary-block flag key
-- ARGV[1] = window_seconds (failcount/HLL TTL)
-- ARGV[2] = ip_failure_threshold
-- ARGV[3] = account_failure_threshold
-- ARGV[4] = distinct_ip_threshold
-- ARGV[5] = strict_capacity
-- ARGV[6] = strict_ttl_seconds
-- ARGV[7] = block_ttl_seconds
-- ARGV[8] = ip_value (added to the HyperLogLog)
--
-- Returns: {ip_count, acct_count, distinct_ip_count,
--           ip_strict_newly_escalated, acct_strict_newly_escalated,
--           acct_block_newly_escalated}  (each flag: 1 or 0)
--
-- ADR 0006's "CHECK ALL -> DECIDE -> WRITE ALL" principle, extended:
-- every counter/HLL/escalation touched by one login-failure event is
-- mutated in this single script, so no concurrent request can observe
-- a partially-updated view of this event's effects.

local ip_failcount_key = KEYS[1]
local acct_failcount_key = KEYS[2]
local hll_key = KEYS[3]
local ip_strict_key = KEYS[4]
local acct_strict_key = KEYS[5]
local acct_block_key = KEYS[6]

local window = tonumber(ARGV[1])
local ip_threshold = tonumber(ARGV[2])
local acct_threshold = tonumber(ARGV[3])
local distinct_ip_threshold = tonumber(ARGV[4])
local strict_capacity = tonumber(ARGV[5])
local strict_ttl = tonumber(ARGV[6])
local block_ttl = tonumber(ARGV[7])
local ip_value = ARGV[8]

-- Fixed window from first failure: TTL is set only when a counter is
-- newly created, not refreshed on every subsequent failure. A simple,
-- deliberate choice (not a true sliding window) -- this signal only
-- needs coarse pattern detection, not precise rate control (that is
-- the token bucket's job).
local ip_count = redis.call('INCR', ip_failcount_key)
if ip_count == 1 then
    redis.call('EXPIRE', ip_failcount_key, window)
end

local acct_count = redis.call('INCR', acct_failcount_key)
if acct_count == 1 then
    redis.call('EXPIRE', acct_failcount_key, window)
end

local hll_existed = redis.call('EXISTS', hll_key)
redis.call('PFADD', hll_key, ip_value)
if hll_existed == 0 then
    redis.call('EXPIRE', hll_key, window)
end
local distinct_ip_count = redis.call('PFCOUNT', hll_key)

-- HSETNX/SETNX so an already-escalated dimension's state is never reset
-- by a later crossing -- only its TTL is refreshed (keeping the
-- escalation alive while abuse continues), and `created == 1` is
-- exactly the "this call newly escalated it" signal the result needs.
local ip_strict_newly_escalated = 0
if ip_count >= ip_threshold then
    local created = redis.call('HSETNX', ip_strict_key, 'tokens', strict_capacity)
    if created == 1 then
        local now = redis.call('TIME')
        local now_seconds = tonumber(now[1]) + (tonumber(now[2]) / 1000000)
        redis.call('HSET', ip_strict_key, 'last_refill_at', now_seconds)
        ip_strict_newly_escalated = 1
    end
    redis.call('EXPIRE', ip_strict_key, strict_ttl)
end

local acct_strict_newly_escalated = 0
if acct_count >= acct_threshold then
    local created = redis.call('HSETNX', acct_strict_key, 'tokens', strict_capacity)
    if created == 1 then
        local now = redis.call('TIME')
        local now_seconds = tonumber(now[1]) + (tonumber(now[2]) / 1000000)
        redis.call('HSET', acct_strict_key, 'last_refill_at', now_seconds)
        acct_strict_newly_escalated = 1
    end
    redis.call('EXPIRE', acct_strict_key, strict_ttl)
end

-- TEMPORARY_BLOCK: SETNX so this is only ever created, and its TTL
-- only ever set, once per episode -- a later crossing never refreshes
-- it. This is the actual guarantee behind ADR 0006 §12's "never
-- permanent or indefinite": if repeated crossings could keep
-- extending the TTL, a persistent low-level attacker could hold an
-- account blocked indefinitely. In the normal request path a blocked
-- account's requests never reach this script again until the block
-- expires (the future block-check gates them out first), but the
-- TTL-refresh asymmetry is what actually bounds the block, not just
-- an assumption about call order.
local acct_block_newly_escalated = 0
if distinct_ip_count >= distinct_ip_threshold then
    local created = redis.call('SETNX', acct_block_key, '1')
    if created == 1 then
        redis.call('EXPIRE', acct_block_key, block_ttl)
        acct_block_newly_escalated = 1
    end
end

return {
    ip_count, acct_count, distinct_ip_count,
    ip_strict_newly_escalated, acct_strict_newly_escalated, acct_block_newly_escalated,
}
"""


def record_login_failure(
    client: redis.Redis,
    *,
    ip: str,
    account_hash: str,
    ip_failure_threshold: int,
    account_failure_threshold: int,
    distinct_ip_threshold: int,
    window_seconds: int,
) -> LoginFailureResult:
    """R1 (IP failcount) + R2 (account failcount) + R3 (account
    distinct-IP HyperLogLog) -- one atomic Lua invocation per login
    failure, per this module's multi-signal atomicity requirement.

    `account_hash` must already be the HMAC identifier
    (`hash_account_identifier()`, `app/core/redis_keys.py`) -- this
    function never sees a raw email.
    """
    keys = [
        failcount_key("login", "ip", ip),
        failcount_key("login", "acct", account_hash),
        distinct_ips_key(account_hash),
        strict_throttle_key("login", "ip", ip),
        strict_throttle_key("login", "acct", account_hash),
        block_key("login", "acct", account_hash),
    ]
    args: list[str | int | float] = [
        window_seconds,
        ip_failure_threshold,
        account_failure_threshold,
        distinct_ip_threshold,
        STRICT_THROTTLE_CAPACITY,
        _STRICT_THROTTLE_TTL_SECONDS,
        TEMPORARY_BLOCK_TTL_SECONDS,
        ip,
    ]
    try:
        script = client.register_script(_RECORD_LOGIN_FAILURE_LUA)
        raw = script(keys=keys, args=args)
    except redis.RedisError as exc:
        raise RedisUnavailableError(str(exc)) from exc

    ip_count, acct_count, distinct_count, ip_strict, acct_strict, acct_block = raw
    return LoginFailureResult(
        ip_failure_count=int(ip_count),
        account_failure_count=int(acct_count),
        distinct_ip_count=int(distinct_count),
        ip_strict_throttle_newly_escalated=bool(ip_strict),
        account_strict_throttle_newly_escalated=bool(acct_strict),
        account_temporary_block_newly_escalated=bool(acct_block),
    )


# --- record a single-dimension IP failure: R4 (strict) / R5 (block) ---------

_RECORD_IP_FAILURE_LUA = """
-- KEYS[1] = ip failcount key
-- KEYS[2] = escalation key (strict-throttle bucket, or block flag)
-- ARGV[1] = window_seconds
-- ARGV[2] = threshold
-- ARGV[3] = escalation_mode (1 = strict-throttle, 0 = temporary-block --
--           numeric, not a string, to match this codebase's existing
--           all-numeric-ARGV convention (_TOKEN_BUCKET_LUA); avoids
--           relying on Lua string-argument round-tripping for a
--           distinction a plain integer already expresses)
-- ARGV[4] = strict_capacity (only meaningful when escalation_mode == 1)
-- ARGV[5] = escalation_ttl_seconds
--
-- Returns: {count, newly_escalated}

local failcount_key = KEYS[1]
local escalation_key = KEYS[2]

local window = tonumber(ARGV[1])
local threshold = tonumber(ARGV[2])
local escalation_mode = tonumber(ARGV[3])
local strict_capacity = tonumber(ARGV[4])
local escalation_ttl = tonumber(ARGV[5])

local count = redis.call('INCR', failcount_key)
if count == 1 then
    redis.call('EXPIRE', failcount_key, window)
end

local newly_escalated = 0
if count >= threshold then
    if escalation_mode == 1 then
        -- STRICT_THROTTLE: HSETNX never resets an already-escalated
        -- bucket's token state, but EXPIRE runs on every crossing
        -- (inside this branch, not gated on `created`) so the
        -- escalation window keeps extending while abuse continues.
        local created = redis.call('HSETNX', escalation_key, 'tokens', strict_capacity)
        if created == 1 then
            local now = redis.call('TIME')
            local now_seconds = tonumber(now[1]) + (tonumber(now[2]) / 1000000)
            redis.call('HSET', escalation_key, 'last_refill_at', now_seconds)
            newly_escalated = 1
        end
        redis.call('EXPIRE', escalation_key, escalation_ttl)
    else
        -- TEMPORARY_BLOCK: deliberately the opposite -- EXPIRE is set
        -- ONLY inside the `created == 1` branch, never refreshed by a
        -- later crossing. ADR 0006 §12 requires a block to be strictly
        -- bounded and "never permanent or indefinite"; if a later
        -- crossing could keep extending the TTL, a persistent
        -- low-level attacker could hold a dimension blocked
        -- indefinitely. In the normal request path this situation
        -- should not arise at all (a blocked dimension is rejected by
        -- the future block-check before it can ever reach this script
        -- again), but the TTL-refresh asymmetry is the actual
        -- guarantee, not merely a defensive assumption about call order.
        local created = redis.call('SETNX', escalation_key, '1')
        if created == 1 then
            redis.call('EXPIRE', escalation_key, escalation_ttl)
            newly_escalated = 1
        end
    end
end

return {count, newly_escalated}
"""


def record_ip_failure(
    client: redis.Redis,
    *,
    operation: str,
    ip: str,
    threshold: int,
    window_seconds: int,
    escalation: Literal["strict", "block"],
) -> SingleDimensionFailureResult:
    """The single-counter, single-escalation shape shared by R4
    (`operation="forgot-password"`, `escalation="strict"`) and R5
    (`operation="reset-password"`, `escalation="block"`). One atomic Lua
    invocation per failure -- the increment and the threshold check/
    escalation-write happen together, never as a separate follow-up
    command that could race against a concurrent failure.
    """
    fc_key = failcount_key(operation, "ip", ip)
    esc_key = (
        strict_throttle_key(operation, "ip", ip)
        if escalation == "strict"
        else block_key(operation, "ip", ip)
    )
    escalation_ttl = (
        _STRICT_THROTTLE_TTL_SECONDS if escalation == "strict" else TEMPORARY_BLOCK_TTL_SECONDS
    )
    args: list[str | int | float] = [
        window_seconds,
        threshold,
        1 if escalation == "strict" else 0,
        STRICT_THROTTLE_CAPACITY,
        escalation_ttl,
    ]
    try:
        script = client.register_script(_RECORD_IP_FAILURE_LUA)
        count, newly_escalated = script(keys=[fc_key, esc_key], args=args)
    except redis.RedisError as exc:
        raise RedisUnavailableError(str(exc)) from exc

    return SingleDimensionFailureResult(
        failure_count=int(count),
        newly_escalated=bool(newly_escalated),
    )


# --- successful-login decay: account-scoped reset only -----------------------


def reset_account_state(client: redis.Redis, *, account_hash: str) -> None:
    """Successful-login decay (ADR 0006 decision: account-scoped state
    resets on that account's own success; IP-scoped state and
    TEMPORARY_BLOCK flags never do -- see this module's docstring and
    the approved design review for why a uniform reset would let an
    attacker "launder" a shared IP's failure history via an unrelated
    account's legitimate success).

    Clears only R2's account failcount and R3's distinct-IP HyperLogLog
    for this account. Never touches `abuse:failcount:login:ip:*`,
    `abuse:strict:*`, or `abuse:block:*` -- deleting those is
    deliberately not this function's job.

    A plain multi-key `DEL` is already atomic as a single Redis command
    (Redis processes one command at a time) -- no Lua script is needed
    for a delete-only operation with no conditional logic.

    Concurrency semantics, stated exactly (not glossed over): Redis
    serializes all commands in a strict total order, so for a
    concurrent success and failure racing for the same account, the
    operation that reaches the Redis server *last* determines the final
    state -- reset-then-failure leaves the failure counted against a
    clean baseline; failure-then-reset clears it. Both are individually
    correct outcomes of "what actually happened at the server," not
    corruption; this is a bounded, self-healing, non-attacker-exploitable
    trade-off (an attacker cannot trigger their own success without
    already possessing the correct credential, at which point there is
    nothing left for a reset to protect). No generation/version
    mechanism is used here -- analysis in the approved design review
    found none is required for this specific race.
    """
    keys = [
        failcount_key("login", "acct", account_hash),
        distinct_ips_key(account_hash),
    ]
    try:
        client.delete(*keys)
    except redis.RedisError as exc:
        raise RedisUnavailableError(str(exc)) from exc


# --- read-only escalation checks (for a future check()/AbuseDecisionEngine) -


def is_strict_throttle_active(
    client: redis.Redis, *, operation: str, dimension: str, value: str
) -> bool:
    """Whether a STRICT_THROTTLE bucket currently exists for this
    dimension -- the primitive a later `AbuseDecisionEngine.check()`
    needs to decide whether to append the strict bucket as an extra
    `DimensionSpec` to `RedisTokenBucketLimiter.check_all()`. A single
    `EXISTS` is already atomic; no Lua needed for a pure read."""
    try:
        return bool(client.exists(strict_throttle_key(operation, dimension, value)))
    except redis.RedisError as exc:
        raise RedisUnavailableError(str(exc)) from exc


def is_temporarily_blocked(
    client: redis.Redis, *, operation: str, dimension: str, value: str
) -> bool:
    """Whether a TEMPORARY_BLOCK flag currently exists for this
    dimension -- the primitive a later `AbuseDecisionEngine.check()`
    needs for its read-only, pre-bucket rejection gate (ADR 0006 §6)."""
    try:
        return bool(client.exists(block_key(operation, dimension, value)))
    except redis.RedisError as exc:
        raise RedisUnavailableError(str(exc)) from exc


def temporary_block_ttl_seconds(
    client: redis.Redis, *, operation: str, dimension: str, value: str
) -> int | None:
    """Remaining TTL (seconds) for an active TEMPORARY_BLOCK, or `None`
    if this dimension isn't currently blocked -- Slice 3b (ADR 0006 §12)
    needs this, not just `is_temporarily_blocked()`'s plain boolean, to
    build an accurate `Retry-After` for a blocked response. Read-only
    (`TTL`) -- doesn't create, refresh, or consume anything, and doesn't
    change `is_temporarily_blocked()`'s own existing contract; the two
    coexist as separate, minimal reads for their separate callers."""
    try:
        ttl = client.ttl(block_key(operation, dimension, value))
    except redis.RedisError as exc:
        raise RedisUnavailableError(str(exc)) from exc
    # TTL returns -2 (key missing) / -1 (key exists, no expiry -- never
    # happens here, since creation and EXPIRE are always paired) for "not
    # blocked"; only a positive integer means an active, bounded block.
    return ttl if ttl > 0 else None
