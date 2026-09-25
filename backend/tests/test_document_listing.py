"""HTTP-level tests for the document list/get endpoints (Issue #5,
Slice 5.1): the frontend's document-list and processing/status-display
features need a real, workspace-scoped way to fetch a workspace's
documents and a single document's current status. Real Postgres/
filesystem, no mocks, matching this project's established
integration-testing convention.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session as DbSession

from app.models.document import Document
from app.services.storage_provider import LocalStorage, get_storage_provider
from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def _register(client: TestClient, email: str | None = None) -> dict[str, Any]:
    email = email or _unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text


@pytest.fixture(autouse=True)
def _isolated_storage(app: FastAPI, tmp_path: Path) -> Iterator[None]:
    app.dependency_overrides[get_storage_provider] = lambda: LocalStorage(root=str(tmp_path))
    yield
    del app.dependency_overrides[get_storage_provider]


def _create_workspace(client: TestClient, name: str = "Acme") -> dict[str, Any]:
    response = client.post("/api/v1/workspaces", json={"name": name}, headers=csrf_headers(client))
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _add_member(client: TestClient, workspace_id: str, email: str, role: str) -> None:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": email, "role": role},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text


def _upload(
    client: TestClient, workspace_id: str, *, filename: str = "a.txt", content: bytes
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, "text/plain")},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


# --- list documents ---------------------------------------------------------


def test_list_documents_returns_uploaded_documents_newest_first(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    first = _upload(client, workspace["id"], content=b"first document content")
    second = _upload(client, workspace["id"], content=b"second document content")

    # A single test runs inside one Postgres transaction (see
    # `conftest.db_session`), where `now()` -- this column's
    # `server_default` -- is constant for the whole transaction, so two
    # rows created moments apart in the same test would otherwise tie on
    # `created_at`. Force distinct timestamps directly to test the
    # ordering itself, which is real (and distinct) across separate
    # requests/transactions in production.
    now = datetime.now(UTC)
    db_session.execute(
        update(Document).where(Document.id == uuid.UUID(first["id"])).values(created_at=now)
    )
    db_session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(second["id"]))
        .values(created_at=now + timedelta(seconds=1))
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents", headers=csrf_headers(client)
    )
    assert response.status_code == 200, response.text
    ids = [d["id"] for d in response.json()]
    assert ids == [second["id"], first["id"]]


def test_list_documents_is_workspace_isolated(client_factory: Callable[[], TestClient]) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    _upload(owner_a, workspace_a["id"], content=b"workspace A secret content")

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = owner_b.get(
        f"/api/v1/workspaces/{workspace_b['id']}/documents", headers=csrf_headers(owner_b)
    )
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_viewer_can_list_documents(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    _upload(owner, workspace["id"], content=b"some content")

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    viewer = client_factory()
    _login(viewer, viewer_email)

    response = viewer.get(
        f"/api/v1/workspaces/{workspace['id']}/documents", headers=csrf_headers(viewer)
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1


# --- get single document -----------------------------------------------------


def test_get_document_returns_current_status(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(client, workspace["id"], content=b"some content")

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{document['id']}",
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == document["id"]
    assert body["status"] == "UPLOADED"


def test_get_document_not_found_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{uuid.uuid4()}",
        headers=csrf_headers(client),
    )
    assert response.status_code == 404


def test_get_document_from_another_workspace_is_not_reachable(
    client_factory: Callable[[], TestClient],
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    document = _upload(owner_a, workspace_a["id"], content=b"workspace A secret content")

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = owner_b.get(
        f"/api/v1/workspaces/{workspace_b['id']}/documents/{document['id']}",
        headers=csrf_headers(owner_b),
    )
    assert response.status_code == 404
