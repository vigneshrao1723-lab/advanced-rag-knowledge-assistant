"""Deterministic abuse-decision policy layer (ADR 0006 §11/§12 — Slice 3b).

Consumes Slice 3a's low-level Redis primitives (`app/core/abuse_state.py`)
and applies the approved R1-R5 rule table. This module owns *policy*
(thresholds, windows, which rule maps to which primitive call) — it has
no knowledge of HTTP, FastAPI, or PostgreSQL, and never calls
`app.core.audit` (audit emission is Slice 3c's responsibility, not this
one's).

Only `login`, `forgot-password`, and `reset-password` participate here —
no rule in R1-R5 targets `register`/`refresh`, so this module is never
consulted for them.

`check()` is a pre-request, read-only decision: it never creates or
consumes any Redis state, only inspects what a *prior* request may have
already escalated. The `record_*` functions are called only after an
endpoint's real outcome is known — never before (see each function's own
docstring for exactly when).

Redis-outage behavior (deliberately simpler than the base token-bucket
limiter's operation-aware Tier A/B split in `app/core/rate_limit.py`):
every function here fails open unconditionally on `RedisUnavailableError`
(logged, never re-raised) and is a safe no-op when `client` is `None`
(Redis not configured for this deployment). The base rate limiter's own
independent failure policy is completely unaffected either way, since
this module never touches it directly — it only ever contributes
additional `DimensionSpec`s for the caller to fold into that limiter's
own `check_all()` invocation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import redis

from app.core.abuse_keys import strict_throttle_key
from app.core.abuse_state import (
    STRICT_THROTTLE_CAPACITY,
    STRICT_THROTTLE_REFILL_RATE,
    is_strict_throttle_active,
    record_ip_failure,
    reset_account_state,
    temporary_block_ttl_seconds,
)
from app.core.abuse_state import record_login_failure as _record_login_failure_primitive
from app.core.redis_client import RedisUnavailableError
from app.core.token_bucket_types import DimensionSpec

logger = logging.getLogger("app.abuse_decision")

_WINDOW_SECONDS = 600

# Rule table (ADR 0006 §11, approved thresholds) — plain module-level
# data, not a class hierarchy. One entry per rule; R1/R2 share the
# multi-signal `record_login_failure()` primitive, so their thresholds
# are grouped with R3's below rather than duplicated as separate rules.
_LOGIN_IP_FAILURE_THRESHOLD = 10  # R1 -> STRICT_THROTTLE
_LOGIN_ACCOUNT_FAILURE_THRESHOLD = 10  # R2 -> STRICT_THROTTLE
_LOGIN_DISTINCT_IP_THRESHOLD = 5  # R3 -> TEMPORARY_BLOCK
_FORGOT_PASSWORD_IP_THRESHOLD = 10  # R4 -> STRICT_THROTTLE
_RESET_PASSWORD_IP_THRESHOLD = 15  # R5 -> TEMPORARY_BLOCK

Operation = Literal["login", "forgot-password", "reset-password"]
Dimension = Literal["ip", "acct"]

# Which dimensions `check()` must inspect for each operation — the
# precedence-defining data: TEMPORARY_BLOCK dimensions are always
# consulted, and always resolved, before any STRICT_THROTTLE dimension
# for the same operation (see `check()` below).
_BLOCK_DIMENSIONS: dict[Operation, tuple[Dimension, ...]] = {
    "login": ("acct",),  # R3
    "forgot-password": (),  # no TEMPORARY_BLOCK rule targets forgot-password
    "reset-password": ("ip",),  # R5
}
_STRICT_DIMENSIONS: dict[Operation, tuple[Dimension, ...]] = {
    "login": ("ip", "acct"),  # R1, R2
    "forgot-password": ("ip",),  # R4
    "reset-password": (),  # no STRICT_THROTTLE rule targets reset-password
}


@dataclass(frozen=True)
class AbuseContext:
    """Everything the abuse-decision layer needs, entirely decoupled
    from FastAPI's `Request` — mirrors `app/core/ip_resolution.py`'s own
    split (a pure function here; a thin `Request`-aware construction at
    the call site, in `app/core/rate_limit.py`/`app/api/v1/auth.py`).

    `account_hash` must already be the HMAC identifier
    (`hash_account_identifier()`, `app/core/redis_keys.py`) — this
    module never sees a raw email. `None` when no account identity is
    available (e.g. `reset-password`, where identity is only knowable
    after the token itself validates, or a `login`/`forgot-password`
    request whose body didn't yield a parseable email).
    """

    operation: Operation
    ip: str
    account_hash: str | None = None


@dataclass(frozen=True)
class AbuseDecision:
    """Result of `check()`.

    `strict_dimensions` are zero or more additional `DimensionSpec`s the
    caller must fold into the *same* `check_all()` invocation as the
    operation's base dimension(s) — never a separate Redis round trip.
    Consuming them separately would reopen exactly the partial-
    consumption race ADR 0006 §10 already closed once for the base
    limiter (a request could consume the base bucket, then separately
    fail the strict bucket, having already spent a base-bucket token for
    nothing).

    `retry_after_seconds` is populated only when `temporary_blocked` is
    `True` (sourced from the block key's own remaining TTL). A
    `STRICT_THROTTLE` rejection's retry-after comes from `check_all()`'s
    own `TokenBucketResult.retry_after_seconds` instead, once the strict
    dimension is folded in — this type does not duplicate that value.
    """

    temporary_blocked: bool
    retry_after_seconds: float | None
    strict_dimensions: list[DimensionSpec] = field(default_factory=list)


@dataclass(frozen=True)
class AbuseRecordOutcome:
    """What a `record_*` call actually did, in enough detail for a
    future Slice 3c to decide whether/what to audit.

    `newly_escalated` is the transition signal: `True` only on the exact
    call whose increment first crossed that rule's threshold, never on a
    later, already-escalated repeat — this is what lets a future
    audit-writing layer avoid a duplicate escalation row on every
    subsequent already-escalated failure (mirrors
    `LoginFailureResult`'s own `*_newly_escalated` fields in
    `abuse_state.py`).
    """

    rule_id: Literal["R1", "R2", "R3", "R4", "R5"] | None
    action: Literal["STRICT_THROTTLE", "TEMPORARY_BLOCK"] | None
    newly_escalated: bool
    operation: str
    dimension: Dimension | None


def _no_escalation(operation: str) -> AbuseRecordOutcome:
    return AbuseRecordOutcome(
        rule_id=None, action=None, newly_escalated=False, operation=operation, dimension=None
    )


def _dimension_value(context: AbuseContext, dimension: Dimension) -> str | None:
    return context.ip if dimension == "ip" else context.account_hash


def _strict_dimension_spec(operation: str, dimension: str, value: str) -> DimensionSpec:
    return DimensionSpec(
        key=strict_throttle_key(operation, dimension, value),
        capacity=STRICT_THROTTLE_CAPACITY,
        refill_rate=STRICT_THROTTLE_REFILL_RATE,
    )


def check(client: redis.Redis | None, context: AbuseContext) -> AbuseDecision:
    """Pre-request: is this operation's dimension currently blocked, and
    which already-escalated strict-throttle buckets (if any) must this
    request's own `check_all()` call also satisfy?

    Read-only — only `EXISTS`/`TTL` commands, never a write. Block
    dimensions (per `_BLOCK_DIMENSIONS`) are always resolved in full
    before any strict-throttle dimension is even inspected — this
    ordering, not a race-dependent property, is what guarantees
    `TEMPORARY_BLOCK` deterministically dominates `STRICT_THROTTLE`
    whenever both are active for the same operation.
    """
    if client is None:
        return AbuseDecision(temporary_blocked=False, retry_after_seconds=None)

    try:
        for dimension in _BLOCK_DIMENSIONS[context.operation]:
            value = _dimension_value(context, dimension)
            if value is None:
                continue
            ttl = temporary_block_ttl_seconds(
                client, operation=context.operation, dimension=dimension, value=value
            )
            if ttl is not None:
                return AbuseDecision(temporary_blocked=True, retry_after_seconds=float(ttl))

        strict_dimensions: list[DimensionSpec] = []
        for dimension in _STRICT_DIMENSIONS[context.operation]:
            value = _dimension_value(context, dimension)
            if value is None:
                continue
            if is_strict_throttle_active(
                client, operation=context.operation, dimension=dimension, value=value
            ):
                strict_dimensions.append(
                    _strict_dimension_spec(context.operation, dimension, value)
                )
        return AbuseDecision(
            temporary_blocked=False,
            retry_after_seconds=None,
            strict_dimensions=strict_dimensions,
        )
    except RedisUnavailableError:
        logger.warning("abuse_check_redis_unavailable", extra={"operation": context.operation})
        return AbuseDecision(temporary_blocked=False, retry_after_seconds=None)


def record_login_failure(client: redis.Redis | None, context: AbuseContext) -> AbuseRecordOutcome:
    """Call exactly once, only after `auth_service.login()` has actually
    raised (a real, confirmed authentication failure) — never before the
    outcome is known, and never on a request rejected earlier by `check()`
    or the base rate limiter (those never reach authentication at all).

    Updates R1 (IP failcount), R2 (account failcount), and R3
    (distinct-IP HyperLogLog) together, in the one atomic Lua invocation
    `abuse_state.record_login_failure()` already provides.
    """
    if client is None or context.account_hash is None:
        return _no_escalation(context.operation)
    try:
        result = _record_login_failure_primitive(
            client,
            ip=context.ip,
            account_hash=context.account_hash,
            ip_failure_threshold=_LOGIN_IP_FAILURE_THRESHOLD,
            account_failure_threshold=_LOGIN_ACCOUNT_FAILURE_THRESHOLD,
            distinct_ip_threshold=_LOGIN_DISTINCT_IP_THRESHOLD,
            window_seconds=_WINDOW_SECONDS,
        )
    except RedisUnavailableError:
        logger.warning("abuse_record_redis_unavailable", extra={"operation": "login"})
        return _no_escalation(context.operation)

    # Report at most one escalation per call, highest severity first —
    # matches `check()`'s own block-dominates-strict ordering.
    if result.account_temporary_block_newly_escalated:
        return AbuseRecordOutcome("R3", "TEMPORARY_BLOCK", True, "login", "acct")
    if result.account_strict_throttle_newly_escalated:
        return AbuseRecordOutcome("R2", "STRICT_THROTTLE", True, "login", "acct")
    if result.ip_strict_throttle_newly_escalated:
        return AbuseRecordOutcome("R1", "STRICT_THROTTLE", True, "login", "ip")
    return _no_escalation("login")


def record_login_success(client: redis.Redis | None, context: AbuseContext) -> None:
    """Call exactly once, only after `auth_service.login()` has actually
    returned successfully.

    Clears R2's account failcount and R3's distinct-IP HyperLogLog for
    this account only (`reset_account_state()`) — never R1's IP
    failcount, and never any active `STRICT_THROTTLE`/`TEMPORARY_BLOCK`
    state, per ADR 0006's decay policy (see `abuse_state.py`'s own
    docstring for the full concurrency-semantics analysis this reuses
    unchanged).
    """
    if client is None or context.account_hash is None:
        return
    try:
        reset_account_state(client, account_hash=context.account_hash)
    except RedisUnavailableError:
        logger.warning("abuse_record_redis_unavailable", extra={"operation": "login"})


def record_forgot_password_request(
    client: redis.Redis | None, context: AbuseContext
) -> AbuseRecordOutcome:
    """Call exactly once per forgot-password request, unconditionally.

    R4 counts *requests*, not failures — `forgot-password` always
    returns the same generic response regardless of whether the email
    exists (enumeration-resistance design in
    `password_reset_service.request_password_reset()`), so there is no
    success/failure outcome for this call to branch on. Deliberately a
    distinct function from `record_login_failure()`/
    `record_reset_validation_failure()` rather than a shared function
    with a `succeeded` flag that would always be the same value here —
    that shape would misleadingly imply a real outcome distinction
    exists for this endpoint.
    """
    if client is None:
        return _no_escalation(context.operation)
    try:
        result = record_ip_failure(
            client,
            operation="forgot-password",
            ip=context.ip,
            threshold=_FORGOT_PASSWORD_IP_THRESHOLD,
            window_seconds=_WINDOW_SECONDS,
            escalation="strict",
        )
    except RedisUnavailableError:
        logger.warning("abuse_record_redis_unavailable", extra={"operation": "forgot-password"})
        return _no_escalation(context.operation)
    if result.newly_escalated:
        return AbuseRecordOutcome("R4", "STRICT_THROTTLE", True, "forgot-password", "ip")
    return _no_escalation("forgot-password")


def record_reset_validation_failure(
    client: redis.Redis | None, context: AbuseContext
) -> AbuseRecordOutcome:
    """Call exactly once, only when `reset-password` validation fails
    with `reset_token_invalid` / `reset_token_expired` /
    `reset_token_already_used` (`password_reset_service.reset_password()`'s
    own error codes) — never on a successful reset.
    """
    if client is None:
        return _no_escalation(context.operation)
    try:
        result = record_ip_failure(
            client,
            operation="reset-password",
            ip=context.ip,
            threshold=_RESET_PASSWORD_IP_THRESHOLD,
            window_seconds=_WINDOW_SECONDS,
            escalation="block",
        )
    except RedisUnavailableError:
        logger.warning("abuse_record_redis_unavailable", extra={"operation": "reset-password"})
        return _no_escalation(context.operation)
    if result.newly_escalated:
        return AbuseRecordOutcome("R5", "TEMPORARY_BLOCK", True, "reset-password", "ip")
    return _no_escalation("reset-password")
