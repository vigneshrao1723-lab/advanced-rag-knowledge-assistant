"""Redis key construction for the deterministic abuse-protection layer
(ADR 0006 §11/§12/§14 — Slice 3a).

Centralized here, mirroring `app/core/redis_keys.py`'s own role for the
`rl:` namespace: no other module builds an `abuse:` key by hand. Every
key this module returns is consumed exclusively by
`app/core/abuse_state.py`'s Redis primitives.

Namespace (ADR 0006 §14, extended by this slice for the strict-throttle
bucket, which the ADR's original key list didn't need to spell out since
it's a Slice-2-era implementation detail of *how* STRICT_THROTTLE is
realized, not a new concept):

    abuse:failcount:{operation}:{dimension}:{value}
    abuse:distinct_ips:acct:{account_hash}
    abuse:strict:{operation}:{dimension}:{value}
    abuse:block:{operation}:{dimension}:{value}

`operation` is reused as the "signal" identifier (e.g. `"login"`,
`"forgot-password"`, `"reset-password"`) rather than inventing a
separate signal vocabulary — this mirrors the `rl:{operation}:...`
convention exactly. `value` is always an already-resolved identifier
(an IP address, or the HMAC account identifier already computed by
`hash_account_identifier()` in `redis_keys.py`) — this module never
sees, hashes, or accepts a raw email address.
"""

from __future__ import annotations

_ABUSE_PREFIX = "abuse"


def failcount_key(operation: str, dimension: str, value: str) -> str:
    """`abuse:failcount:{operation}:{dimension}:{value}` — a simple
    fixed-window failure counter (ADR §11's R1/R2/R4/R5 signals)."""
    return f"{_ABUSE_PREFIX}:failcount:{operation}:{dimension}:{value}"


def distinct_ips_key(account_hash: str) -> str:
    """`abuse:distinct_ips:acct:{account_hash}` — the HyperLogLog behind
    R3 (ADR §11's coordinated-abuse signal). Deliberately account-only
    and operation-less, matching ADR §14's literal key pattern: R3 is
    specifically about `login` failures against one account, the only
    case this signal exists for today."""
    return f"{_ABUSE_PREFIX}:distinct_ips:acct:{account_hash}"


def strict_throttle_key(operation: str, dimension: str, value: str) -> str:
    """`abuse:strict:{operation}:{dimension}:{value}` — the second,
    stricter token-bucket hash a STRICT_THROTTLE escalation (R1/R2/R4)
    creates. Same hash shape (`tokens`/`last_refill_at`) the existing
    `rl:*` buckets already use, so it can be consumed as an ordinary
    `DimensionSpec` by the existing `RedisTokenBucketLimiter` — no new
    bucket engine."""
    return f"{_ABUSE_PREFIX}:strict:{operation}:{dimension}:{value}"


def block_key(operation: str, dimension: str, value: str) -> str:
    """`abuse:block:{operation}:{dimension}:{value}` — the TEMPORARY_BLOCK
    flag a hard escalation (R3/R5) creates. A plain existence flag, not a
    bucket: presence means "reject outright," per ADR §12."""
    return f"{_ABUSE_PREFIX}:block:{operation}:{dimension}:{value}"
