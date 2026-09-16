"""Trusted-proxy-aware client IP resolution (ADR 0006 §9a).

Not wired into any endpoint yet — this slice only implements the
reusable abstraction the Redis-backed limiter's IP dimension will use
once a future slice switches `enforce_*_rate_limit` over to it. Today's
`app.core.rate_limit.client_ip()` (a direct, unconditional
`request.client.host` read) is unchanged and remains what every existing
endpoint actually uses — that is a deliberate scope boundary for this
slice, not an oversight.

Model, exactly as ADR 0006 §9a specifies:

- `TRUSTED_PROXY_CIDRS` unset/empty (the default): `X-Forwarded-For` and
  `Forwarded` are ignored unconditionally; the resolved IP is always the
  direct TCP peer.
- `TRUSTED_PROXY_CIDRS` configured: if the direct TCP peer falls inside a
  trusted CIDR, walk `X-Forwarded-For` **from the right** (the entry
  closest to this server), continuing left through any further trusted
  hops, stopping at the first entry that is *not* inside a trusted CIDR —
  that entry is the resolved client IP. If the direct peer itself is not
  trusted, the header is ignored and the direct peer is used, exactly as
  in the empty-configuration case.

Never trusts a client-supplied header by default, and never lets a
client choose its own rate-limit key by spoofing `X-Forwarded-For` on a
direct, untrusted connection.
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network

from fastapi import Request


def _is_trusted(candidate: str, trusted_cidrs: list[str]) -> bool:
    try:
        parsed = ip_address(candidate.strip())
    except ValueError:
        return False
    for cidr in trusted_cidrs:
        try:
            network = ip_network(cidr.strip(), strict=False)
        except ValueError:
            continue
        if parsed in network:
            return True
    return False


def resolve_ip(
    *,
    direct_peer: str,
    forwarded_for: str | None,
    trusted_cidrs: list[str],
) -> str:
    """Pure resolution logic (ADR 0006 §9a) — no FastAPI dependency, so
    it's directly unit-testable against synthetic inputs.

    `forwarded_for` is the raw `X-Forwarded-For` header value (a
    comma-separated list, leftmost = original client, each subsequent
    entry appended by one hop); `trusted_cidrs` are the operator-configured
    trusted proxy ranges (empty = trust nothing, use `direct_peer` as-is).
    """
    if not trusted_cidrs or not _is_trusted(direct_peer, trusted_cidrs):
        return direct_peer

    if not forwarded_for:
        return direct_peer

    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    # Walk from the right (closest to this server, appended by the
    # nearest trusted proxy) — never trust the client-controlled leftmost
    # entry without first confirming every hop back to it was itself
    # appended by a configured trusted proxy.
    for hop in reversed(hops):
        if _is_trusted(hop, trusted_cidrs):
            continue
        return hop

    # Every hop was inside a trusted CIDR (a fully trusted chain with no
    # untrusted entry) — fall back to the direct peer rather than
    # fabricate a client IP out of proxy addresses.
    return direct_peer


def resolve_client_ip(request: Request, trusted_cidrs: list[str]) -> str:
    """`Request`-based wrapper around `resolve_ip()`. Not called from any
    endpoint in this slice — see module docstring."""
    direct_peer = request.client.host if request.client is not None else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    return resolve_ip(
        direct_peer=direct_peer,
        forwarded_for=forwarded_for,
        trusted_cidrs=trusted_cidrs,
    )
