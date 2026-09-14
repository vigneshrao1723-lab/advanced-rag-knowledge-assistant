from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_secret,
    parse_refresh_token,
    verify_password,
)


def test_hash_password_produces_a_verifiable_but_different_string() -> None:
    password = "correct horse battery staple"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("the-real-password")

    assert verify_password("not-the-real-password", hashed) is False


def test_hash_password_is_salted_so_two_hashes_of_the_same_password_differ() -> None:
    password = "same-password"

    assert hash_password(password) != hash_password(password)


def test_verify_password_rejects_garbage_hash_without_raising() -> None:
    assert verify_password("anything", "not-a-real-argon2-hash") is False


def test_access_token_round_trips_user_and_session_id() -> None:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    token, expires_at = create_access_token(user_id, session_id)
    claims = decode_access_token(token)

    assert claims is not None
    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert expires_at > datetime.now(UTC)


def test_decode_access_token_rejects_garbage() -> None:
    assert decode_access_token("not-a-jwt") is None


def test_decode_access_token_rejects_expired_token() -> None:
    settings = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "type": "access",
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(payload, settings.secret_key, algorithm="HS256")

    assert decode_access_token(expired_token) is None


def test_decode_access_token_rejects_wrong_signature() -> None:
    payload = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token_signed_with_wrong_key = jwt.encode(
        payload, "a-different-secret-that-is-long-enough-for-hs256", algorithm="HS256"
    )

    assert decode_access_token(token_signed_with_wrong_key) is None


def test_decode_access_token_rejects_non_access_token_type() -> None:
    settings = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "type": "refresh",  # not an access token
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")

    assert decode_access_token(token) is None


def test_refresh_token_encode_and_parse_round_trip() -> None:
    generated = generate_refresh_token()

    parsed = parse_refresh_token(generated.encode())

    assert parsed is not None
    session_id, secret = parsed
    assert session_id == generated.session_id
    assert secret == generated.secret


def test_parse_refresh_token_rejects_malformed_input() -> None:
    assert parse_refresh_token("no-dot-separator") is None
    assert parse_refresh_token("not-a-uuid.somesecret") is None
    assert parse_refresh_token(f"{uuid.uuid4()}.") is None


def test_hash_refresh_secret_is_deterministic_and_distinct() -> None:
    assert hash_refresh_secret("secret-a") == hash_refresh_secret("secret-a")
    assert hash_refresh_secret("secret-a") != hash_refresh_secret("secret-b")


def test_generate_refresh_token_secret_is_high_entropy_length() -> None:
    token = generate_refresh_token()
    assert len(token.secret) >= 32
