from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
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
    forgot_password_rate_limiter,
    login_rate_limiter,
    refresh_rate_limiter,
    register_rate_limiter,
    reset_password_rate_limiter,
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
    forgot_password_rate_limiter.reset()
    reset_password_rate_limiter.reset()


@pytest.fixture
def app(db_session: DbSession) -> Iterator[FastAPI]:
    application = create_app()

    def _override_get_db() -> Iterator[DbSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client_factory(app: FastAPI) -> Iterator[Callable[[], TestClient]]:
    """Auth is now cookie-based (ADR 0005): a single `TestClient`'s cookie
    jar can only hold one "logged in" identity at a time, unlike the old
    per-request `Authorization` header, which let a test juggle several
    users through one client. Tests that need several concurrently
    "logged in" identities (owner/admin/member/attacker) must ask for a
    separate `TestClient` per identity — same `app`/`db_session`
    (so they see the same data), independent cookie jars (so logging in as
    one doesn't clobber another's session cookies).
    """
    created: list[TestClient] = []

    def _make() -> TestClient:
        test_client = TestClient(app)
        created.append(test_client)
        return test_client

    yield _make
    for test_client in created:
        test_client.close()


@pytest.fixture
def client(client_factory: Callable[[], TestClient]) -> TestClient:
    return client_factory()


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    """Fetch a CSRF cookie for this client (as the frontend does before
    rendering login/register) and return the header a state-changing
    request must echo it in."""
    test_client.get("/api/v1/auth/csrf")
    token = test_client.cookies.get("csrf_token")
    assert token is not None, "CSRF cookie was not set"
    return {"X-CSRF-Token": token}
