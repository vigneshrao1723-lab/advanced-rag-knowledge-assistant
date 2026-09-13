from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

# Config is read at import time; tests run against a real PostgreSQL +
# pgvector instance (per docs/DECISIONS/0002 — no sqlite substitute), the
# same one `infra/compose/docker-compose.yml` provides for local dev. Only
# overridden if the environment doesn't already set these.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://raguser:ragpass@localhost:5432/ragdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

from app.core.db import engine, get_db  # noqa: E402
from app.core.rate_limit import (  # noqa: E402
    login_rate_limiter,
    refresh_rate_limiter,
    register_rate_limiter,
)
from app.main import create_app  # noqa: E402

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    """Apply every Alembic migration once per test session, against the
    real database — proves the migration chain works and gives tests real
    tables to exercise (docs/DECISIONS/0002; Issue #2 testing requirements)."""
    config = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    command.upgrade(config, "head")


@pytest.fixture
def db_session() -> Iterator[DbSession]:
    """A real-database session scoped to one test: every change is rolled
    back afterwards via SQLAlchemy 2.0's "join an external transaction"
    pattern, so application code calling `session.commit()` (as our
    services do) doesn't leak state between tests."""
    connection = engine.connect()
    transaction = connection.begin()
    session = DbSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiters() -> None:
    """The TestClient always presents the same fake client host, so without
    a reset every test would share one rate-limit bucket per limiter —
    tests that don't specifically exercise rate limiting shouldn't trip it."""
    login_rate_limiter.reset()
    register_rate_limiter.reset()
    refresh_rate_limiter.reset()


@pytest.fixture
def client(db_session: DbSession) -> Iterator[TestClient]:
    app = create_app()

    def _override_get_db() -> Iterator[DbSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
