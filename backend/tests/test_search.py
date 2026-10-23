"""HTTP-level tests for standalone search (GitHub Issue #41, feature-
completion sprint priority 2): retrieval-only, no generation. Real
Postgres/Redis/filesystem, no mocks, exercising the full Issue #3
ingestion pipeline (upload -> process -> READY) before searching it,
matching this project's established integration-testing convention
(see tests/test_conversations.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.retrieval_event import RetrievalEvent
from app.services.storage_provider import LocalStorage, get_storage_provider
from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"
_TXT_BYTES = (
    b"Our refund policy allows returns within thirty days of purchase. "
    b"Contact support for assistance with your return."
)


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


def _ingest_ready_document(
    client: TestClient, workspace_id: str, *, filename: str = "a.txt", content: bytes
) -> dict[str, Any]:
    upload_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, "text/plain")},
        headers=csrf_headers(client),
    )
    assert upload_response.status_code == 201, upload_response.text
    document: dict[str, Any] = upload_response.json()
    process_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}/process",
        headers=csrf_headers(client),
    )
    assert process_response.status_code == 200, process_response.text
    assert process_response.json()["status"] == "READY"
    return document


def _search(client: TestClient, workspace_id: str, query: str) -> Any:
    return client.get(f"/api/v1/workspaces/{workspace_id}/search", params={"q": query})


def test_search_returns_ranked_results_with_source_info(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _ingest_ready_document(client, workspace["id"], content=_TXT_BYTES)

    response = _search(client, workspace["id"], "What is the refund policy?")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == "What is the refund policy?"
    assert body["method"] == "hybrid"
    assert len(body["results"]) >= 1
    first = body["results"][0]
    assert first["document_id"] == document["id"]
    assert first["document_filename"] == "a.txt"
    assert "refund policy" in first["content"]
    assert first["rank"] == 0
    assert isinstance(first["score"], float)


def test_search_with_no_documents_returns_empty_results(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = _search(client, workspace["id"], "anything")

    assert response.status_code == 200, response.text
    assert response.json()["results"] == []


def test_search_is_workspace_isolated(client_factory: Callable[[], TestClient]) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    _ingest_ready_document(owner_a, workspace_a["id"], content=_TXT_BYTES)

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = _search(owner_b, workspace_b["id"], "refund policy")

    assert response.status_code == 200, response.text
    assert response.json()["results"] == []


def test_search_requires_authentication(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    anonymous = client_factory()

    response = _search(anonymous, workspace["id"], "anything")

    assert response.status_code == 401


def test_viewer_can_search(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    _ingest_ready_document(owner, workspace["id"], content=_TXT_BYTES)
    viewer = client_factory()
    viewer_body = _register(viewer)
    _add_member(owner, workspace["id"], viewer_body["user"]["email"], "VIEWER")

    response = _search(viewer, workspace["id"], "refund policy")

    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) >= 1


def test_empty_search_query_is_rejected(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = _search(client, workspace["id"], "")

    assert response.status_code == 422


def test_search_records_a_retrieval_event_with_no_conversation(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    _ingest_ready_document(client, workspace["id"], content=_TXT_BYTES)

    response = _search(client, workspace["id"], "refund policy")
    assert response.status_code == 200, response.text

    event = db_session.execute(
        select(RetrievalEvent)
        .where(RetrievalEvent.workspace_id == uuid.UUID(workspace["id"]))
        .order_by(RetrievalEvent.created_at.desc())
    ).scalars().first()
    assert event is not None
    assert event.conversation_id is None
    assert event.message_id is None
    assert event.query_text == "refund policy"
    assert event.method == "hybrid"


def test_search_rate_limit_enforced_at_threshold(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    last_status = None
    for _ in range(21):
        last_status = _search(client, workspace["id"], "anything").status_code
    assert last_status == 429
