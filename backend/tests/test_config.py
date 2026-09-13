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
