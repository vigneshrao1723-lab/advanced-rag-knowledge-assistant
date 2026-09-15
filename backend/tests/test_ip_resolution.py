from __future__ import annotations

from app.core.ip_resolution import resolve_ip


def test_no_trusted_cidrs_ignores_forwarded_header_entirely() -> None:
    """ADR 0006 §9a default: TRUSTED_PROXY_CIDRS unset -> always the
    direct TCP peer, never a client-supplied header."""
    result = resolve_ip(
        direct_peer="203.0.113.4",
        forwarded_for="1.2.3.4",
        trusted_cidrs=[],
    )

    assert result == "203.0.113.4"


def test_spoofed_header_from_an_untrusted_direct_peer_is_ignored() -> None:
    """A direct attacker cannot choose their own rate-limit key by setting
    X-Forwarded-For on a request that goes straight to the backend."""
    result = resolve_ip(
        direct_peer="198.51.100.9",
        forwarded_for="1.2.3.4",
        trusted_cidrs=["10.0.0.0/8"],
    )

    assert result == "198.51.100.9"


def test_trusted_proxy_with_no_forwarded_header_falls_back_to_direct_peer() -> None:
    result = resolve_ip(
        direct_peer="10.0.0.5",
        forwarded_for=None,
        trusted_cidrs=["10.0.0.0/8"],
    )

    assert result == "10.0.0.5"


def test_trusted_proxy_header_is_honored_and_walked_from_the_right() -> None:
    """The immediate peer (10.0.0.5) is trusted, so its appended entry is
    used."""
    result = resolve_ip(
        direct_peer="10.0.0.5",
        forwarded_for="198.51.100.9",
        trusted_cidrs=["10.0.0.0/8"],
    )

    assert result == "198.51.100.9"


def test_chained_trusted_proxies_walk_past_every_trusted_hop() -> None:
    """A CDN (203.0.113.1) in front of an internal load balancer
    (10.0.0.5), both trusted: walk from the right past both trusted
    entries to the real client."""
    result = resolve_ip(
        direct_peer="10.0.0.5",
        forwarded_for="198.51.100.9, 203.0.113.1",
        trusted_cidrs=["10.0.0.0/8", "203.0.113.0/24"],
    )

    assert result == "198.51.100.9"


def test_client_supplied_prefix_on_the_header_cannot_be_chosen() -> None:
    """A client sending its own forged leftmost entry cannot make that
    entry the resolved IP -- only entries appended by trusted proxies are
    ever walked past."""
    result = resolve_ip(
        direct_peer="10.0.0.5",
        forwarded_for="9.9.9.9, 198.51.100.9",
        trusted_cidrs=["10.0.0.0/8"],
    )

    # The walk starts at the rightmost entry and stops at the first one
    # that isn't itself a trusted proxy address -- "198.51.100.9" isn't,
    # so it's the resolved IP. The client's own forged leftmost entry
    # ("9.9.9.9") is never even reached, let alone chosen.
    assert result == "198.51.100.9"


def test_fully_trusted_chain_with_no_untrusted_entry_falls_back_to_direct_peer() -> None:
    result = resolve_ip(
        direct_peer="10.0.0.5",
        forwarded_for="10.0.0.1, 10.0.0.2",
        trusted_cidrs=["10.0.0.0/8"],
    )

    assert result == "10.0.0.5"


def test_malformed_header_entries_are_not_trusted() -> None:
    result = resolve_ip(
        direct_peer="10.0.0.5",
        forwarded_for="not-an-ip",
        trusted_cidrs=["10.0.0.0/8"],
    )

    assert result == "not-an-ip"


def test_invalid_direct_peer_with_trusted_cidrs_is_not_trusted() -> None:
    result = resolve_ip(
        direct_peer="not-an-ip",
        forwarded_for="198.51.100.9",
        trusted_cidrs=["10.0.0.0/8"],
    )

    assert result == "not-an-ip"
