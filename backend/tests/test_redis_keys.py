from __future__ import annotations

from app.core.redis_keys import hash_account_identifier, rate_limit_key


def test_rate_limit_key_format() -> None:
    assert rate_limit_key("login", "ip", "203.0.113.4") == "rl:login:ip:203.0.113.4"


def test_rate_limit_key_distinguishes_operation() -> None:
    assert rate_limit_key("login", "ip", "203.0.113.4") != rate_limit_key(
        "refresh", "ip", "203.0.113.4"
    )


def test_rate_limit_key_distinguishes_dimension() -> None:
    assert rate_limit_key("login", "ip", "203.0.113.4") != rate_limit_key(
        "login", "session", "203.0.113.4"
    )


def test_hash_account_identifier_is_deterministic() -> None:
    key = b"server-secret"
    assert hash_account_identifier("user@example.com", key=key) == hash_account_identifier(
        "user@example.com", key=key
    )


def test_hash_account_identifier_is_case_insensitive() -> None:
    key = b"server-secret"
    assert hash_account_identifier("User@Example.com", key=key) == hash_account_identifier(
        "user@example.com", key=key
    )


def test_hash_account_identifier_strips_whitespace() -> None:
    key = b"server-secret"
    assert hash_account_identifier(" user@example.com ", key=key) == hash_account_identifier(
        "user@example.com", key=key
    )


def test_hash_account_identifier_differs_per_email() -> None:
    key = b"server-secret"
    assert hash_account_identifier("alice@example.com", key=key) != hash_account_identifier(
        "bob@example.com", key=key
    )


def test_hash_account_identifier_requires_the_key_to_reproduce() -> None:
    """The whole point of a keyed HMAC over a plain hash (ADR 0006 §14):
    a different key produces a different digest, even for the same
    email — an attacker without the server's key cannot precompute a
    matching table from a leaked email list alone."""
    digest_a = hash_account_identifier("user@example.com", key=b"secret-a")
    digest_b = hash_account_identifier("user@example.com", key=b"secret-b")

    assert digest_a != digest_b


def test_hash_account_identifier_never_contains_the_raw_email() -> None:
    digest = hash_account_identifier("someone@example.com", key=b"server-secret")

    assert "someone" not in digest
    assert "example.com" not in digest
    # A hex SHA-256 HMAC digest: 64 lowercase hex characters, nothing else.
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
