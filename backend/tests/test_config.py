from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config must fail loudly, not silently default, when a required
    setting is missing (docs/SECURITY.md "Secret management")."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database_url == "postgresql+psycopg://u:p@localhost:5432/db"
    assert settings.environment == "local"
    assert settings.secret_key == "test-secret"
    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_token_expire_days == 30
    assert settings.cookie_samesite == "lax"
    assert settings.cookie_domain is None
    assert settings.cookie_secure is None


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("SECRET_KEY", "test-secret")


def test_cookie_secure_defaults_to_false_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "local")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.cookie_secure_resolved is False


def test_cookie_secure_defaults_to_true_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.cookie_secure_resolved is True


def test_cookie_secure_forced_true_when_samesite_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.cookie_secure_resolved is True


def test_cookie_secure_explicit_false_with_samesite_none_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browsers reject `SameSite=None` cookies without `Secure` — this
    combination must fail at config load time, not silently ship a cookie
    no browser will actually accept."""
    _base_env(monkeypatch)
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_email_provider_console_in_production_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The console provider prints password-reset tokens to stdout, which
    real deployments typically capture into log aggregation — this must
    fail at config load time rather than silently leak reset tokens into
    production logs if EMAIL_PROVIDER is ever left unset/misconfigured."""
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_email_provider_console_is_fine_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.email_provider == "console"


def test_email_provider_smtp_in_production_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.email_provider == "smtp"


def test_cookie_secure_explicit_override_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("COOKIE_SECURE", "true")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.cookie_secure_resolved is True


def test_cookie_domain_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("COOKIE_DOMAIN", ".example.com")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.cookie_domain == ".example.com"
