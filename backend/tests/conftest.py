from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# Config is read at import time (app.core.config.get_settings via
# app.main); tests must not depend on a real database being reachable
# unless a test explicitly exercises readiness, so a syntactically valid
# placeholder URL is supplied when the environment doesn't already have one.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")

from app.main import create_app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
