"""Shared data types for the Redis token-bucket engine (ADR 0006 §8/§10).

Split out from `app/core/rate_limit.py` (Slice 1/2) specifically to
break an import cycle introduced by Slice 3b: `app/core/abuse_state.py`
and `app/core/abuse_decision.py` need `DimensionSpec` to build
strict-throttle dimension specs that reuse the same bucket shape and TTL
derivation as the base rate limiter (ADR 0006's "no new bucket engine"
requirement), while `app/core/rate_limit.py` itself needs to call into
`abuse_decision.check()` — two modules that would otherwise need to
import from each other's main module. These plain, dependency-free data
types live here instead, owned by neither, and `rate_limit.py` still
re-exports both names unchanged (`from app.core.rate_limit import
DimensionSpec` continues to work everywhere it already did) so no
existing call site needed to change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

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
