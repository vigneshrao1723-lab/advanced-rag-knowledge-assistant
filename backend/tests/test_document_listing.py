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
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.core.audit import AuditEvent
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
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


def test_get_document_not_found_records_an_audit_event(
    client: TestClient, db_session: DbSession
) -> None:
    # GitHub Issue #7: a resource-ID lookup denied within an
    # already-workspace-authorized request is audited (distinct from
    # AUTHORIZATION_DENIED, which fires at the workspace-membership gate).
    _register(client)
    workspace = _create_workspace(client)
    attempted_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{attempted_id}",
        headers=csrf_headers(client),
    )
    assert response.status_code == 404

    rows = (
        db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEvent.CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED,
                AuditLog.workspace_id == uuid.UUID(workspace["id"]),
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].event_metadata is not None
    assert rows[0].event_metadata["resource_type"] == "document"
    assert rows[0].event_metadata["attempted_document_id"] == str(attempted_id)
    assert rows[0].user_id is not None


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


# --- get document chunk (source inspection) ----------------------------------


def _process(client: TestClient, workspace_id: str, document_id: str) -> Any:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
        headers=csrf_headers(client),
    )


_TXT_BYTES = (
    b"Our refund policy allows returns within thirty days of purchase. "
    b"Contact support for assistance with your return."
)


def _ingest_ready_document(
    client: TestClient, workspace_id: str, *, content: bytes = _TXT_BYTES
) -> dict[str, Any]:
    document = _upload(client, workspace_id, content=content)
    response = _process(client, workspace_id, document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY", response.text
    return document


def test_get_document_chunk_returns_the_actual_evidence_text(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _ingest_ready_document(client, workspace["id"])

    chunk = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document["id"]))
    ).scalars().first()
    assert chunk is not None

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{document['id']}/chunks/{chunk.id}",
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(chunk.id)
    assert body["document_id"] == document["id"]
    assert body["content"] == chunk.content
    assert "refund policy" in body["content"]


def test_get_document_chunk_not_found_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _ingest_ready_document(client, workspace["id"])

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{document['id']}/chunks/{uuid.uuid4()}",
        headers=csrf_headers(client),
    )
    assert response.status_code == 404


def test_get_document_chunk_from_another_document_is_not_reachable(
    client: TestClient, db_session: DbSession
) -> None:
    # A chunk_id that genuinely exists, but belongs to a *different*
    # document within the same workspace, must not be fetchable through
    # this document's own URL -- IDOR-shaped, even inside one workspace.
    _register(client)
    workspace = _create_workspace(client)
    document_a = _ingest_ready_document(client, workspace["id"], content=_TXT_BYTES)
    document_b = _ingest_ready_document(
        client, workspace["id"], content=b"Shipping takes five to seven business days."
    )

    chunk_b = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_b["id"]))
    ).scalars().first()
    assert chunk_b is not None

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{document_a['id']}/chunks/{chunk_b.id}",
        headers=csrf_headers(client),
    )
    assert response.status_code == 404


def test_get_document_chunk_from_another_workspace_is_not_reachable(
    client_factory: Callable[[], TestClient], db_session: DbSession
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    document = _ingest_ready_document(owner_a, workspace_a["id"])
    chunk = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document["id"]))
    ).scalars().first()
    assert chunk is not None

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = owner_b.get(
        f"/api/v1/workspaces/{workspace_b['id']}/documents/{document['id']}/chunks/{chunk.id}",
        headers=csrf_headers(owner_b),
    )
    assert response.status_code == 404


def test_viewer_can_get_document_chunk(
    client_factory: Callable[[], TestClient], db_session: DbSession
) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    document = _ingest_ready_document(owner, workspace["id"])
    chunk = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document["id"]))
    ).scalars().first()
    assert chunk is not None

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    viewer = client_factory()
    _login(viewer, viewer_email)

    response = viewer.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{document['id']}/chunks/{chunk.id}",
        headers=csrf_headers(viewer),
    )
    assert response.status_code == 200, response.text
