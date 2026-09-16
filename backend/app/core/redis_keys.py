"""Redis key construction for the distributed rate limiter (ADR 0006 §14).

Centralized here so no other module builds a Redis key by hand — every
key used by `RedisTokenBucketLimiter` (`app/core/rate_limit.py`) goes
through `rate_limit_key()`, and every email-derived identifier goes
through `hash_account_identifier()`. This is deliberately the *only*
place in the codebase allowed to know the namespace layout.

Namespace (ADR 0006 §14): `rl:{operation}:{dimension}:{value}` for
rate-limit buckets. The `abuse:` prefix for the abuse/risk layer is not
implemented in this slice (ADR 0006 §11/§12 — a later slice).
"""

from __future__ import annotations

import hashlib
import hmac

_RATE_LIMIT_PREFIX = "rl"


def rate_limit_key(operation: str, dimension: str, value: str) -> str:
    """Build a namespaced rate-limit bucket key.

    `operation` (e.g. `"login"`), `dimension` (e.g. `"ip"`, `"acct"`,
    `"session"`), and `value` (the already-resolved identifier — an IP
    address, an HMAC digest, a session ID) are never allowed to contain a
    Redis key-delimiter `:` themselves in a way that could cause two
    distinct (operation, dimension, value) triples to collide, since none
    of the values this design uses (IP addresses, hex HMAC digests,
    UUID session IDs) can contain a literal `:` inside their own encoding
    in a way that fabricates a different key's exact string — hex digests
    and UUIDs are `[0-9a-f-]` only, and this function does not accept
    attacker-controlled `operation`/`dimension` names (always literal
    strings from call sites in this codebase, never request input).
    """
    return f"{_RATE_LIMIT_PREFIX}:{operation}:{dimension}:{value}"


def hash_account_identifier(email: str, *, key: bytes) -> str:
    """HMAC-SHA256(key, lowercase(email)) — ADR 0006 §14's corrected
    design for email-derived Redis identifiers.

    A plain hash of an email address is not a meaningful privacy
    protection (low-entropy, dictionary/rainbow-table-matchable); a keyed
    HMAC requires knowing the server-held `key` to precompute a matching
    table, which an external holder of a leaked email list does not have.
    Never used for passwords, tokens, or other high-entropy secrets —
    those already use plain SHA-256 in `app/core/security.py`, which is
    the correct (and simpler) primitive for a value that's already
    infeasible to guess or enumerate.
    """
    normalized = email.strip().lower().encode("utf-8")
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()
