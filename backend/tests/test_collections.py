"""HTTP-level tests for collections (GitHub Issue #41): logical grouping
of documents within a workspace. Real Postgres/filesystem, no mocks,
matching this project's established integration-testing convention
(see tests/test_document_listing.py, tests/test_workspaces.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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


@pytest.fixture(autouse=True)
def _isolated_storage(app: FastAPI, tmp_path: Path) -> Iterator[None]:
    app.dependency_overrides[get_storage_provider] = lambda: LocalStorage(root=str(tmp_path))
    yield
    del app.dependency_overrides[get_storage_provider]


def _upload(
    client: TestClient, workspace_id: str, *, filename: str = "a.txt", content: bytes = b"content"
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, "text/plain")},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _create_collection(
    client: TestClient, workspace_id: str, *, name: str = "Research", description: str | None = None
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/collections",
        json={"name": name, "description": description},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


# --- create / list -----------------------------------------------------------


def test_create_collection_starts_with_zero_documents(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    collection = _create_collection(
        client, workspace["id"], name="Papers", description="Research papers"
    )

    assert collection["name"] == "Papers"
    assert collection["description"] == "Research papers"
    assert collection["document_count"] == 0


def test_list_collections_includes_document_counts(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    collection = _create_collection(client, workspace["id"])
    document = _upload(client, workspace["id"])
    client.post(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}/documents",
        json={"document_id": document["id"]},
        headers=csrf_headers(client),
    )

    response = client.get(f"/api/v1/workspaces/{workspace['id']}/collections")

    assert response.status_code == 200, response.text
    [result] = response.json()
    assert result["id"] == collection["id"]
    assert result["document_count"] == 1


def test_list_collections_is_workspace_isolated(client_factory: Callable[[], TestClient]) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    _create_collection(owner_a, workspace_a["id"], name="A's collection")

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = owner_b.get(f"/api/v1/workspaces/{workspace_b['id']}/collections")

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_create_collection_requires_authentication(
    client_factory: Callable[[], TestClient]
) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    anonymous = client_factory()

    response = anonymous.post(
        f"/api/v1/workspaces/{workspace['id']}/collections",
        json={"name": "x"},
        headers=csrf_headers(anonymous),
    )

    assert response.status_code == 401


def test_viewer_cannot_create_collection(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    owner_body = _register(owner)
    workspace = _create_workspace(owner)
    viewer = client_factory()
    viewer_body = _register(viewer)
    _add_member(owner, workspace["id"], viewer_body["user"]["email"], "VIEWER")

    response = viewer.post(
        f"/api/v1/workspaces/{workspace['id']}/collections",
        json={"name": "x"},
        headers=csrf_headers(viewer),
    )

    assert response.status_code == 403
    assert owner_body["user"]["email"] != viewer_body["user"]["email"]


def test_viewer_can_list_and_get_collections(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    collection = _create_collection(owner, workspace["id"])
    viewer = client_factory()
    viewer_body = _register(viewer)
    _add_member(owner, workspace["id"], viewer_body["user"]["email"], "VIEWER")

    list_response = viewer.get(f"/api/v1/workspaces/{workspace['id']}/collections")
    get_response = viewer.get(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}"
    )

    assert list_response.status_code == 200, list_response.text
    assert get_response.status_code == 200, get_response.text


# --- get (with documents) ----------------------------------------------------


def test_get_collection_returns_its_documents(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    collection = _create_collection(client, workspace["id"])
    document = _upload(client, workspace["id"], content=b"doc content")
    client.post(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}/documents",
        json={"document_id": document["id"]},
        headers=csrf_headers(client),
    )

    response = client.get(f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document_count"] == 1
    assert [d["id"] for d in body["documents"]] == [document["id"]]


def test_get_collection_cross_workspace_returns_404(
    client_factory: Callable[[], TestClient]
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    collection_a = _create_collection(owner_a, workspace_a["id"])

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = owner_b.get(
        f"/api/v1/workspaces/{workspace_b['id']}/collections/{collection_a['id']}"
    )

    assert response.status_code == 404


def test_get_nonexistent_collection_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/collections/{uuid.uuid4()}"
    )

    assert response.status_code == 404


# --- update / delete ----------------------------------------------------------


def test_update_collection_renames_and_updates_description(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    collection = _create_collection(client, workspace["id"], name="Old", description="Old desc")

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}",
        json={"name": "New", "description": None},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "New"
    assert body["description"] is None


def test_delete_collection_removes_it_but_not_its_documents(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    collection = _create_collection(client, workspace["id"])
    document = _upload(client, workspace["id"])
    client.post(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}/documents",
        json={"document_id": document["id"]},
        headers=csrf_headers(client),
    )

    delete_response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}",
        headers=csrf_headers(client),
    )
    get_collection_response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}"
    )
    get_document_response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/documents/{document['id']}"
    )

    assert delete_response.status_code == 204, delete_response.text
    assert get_collection_response.status_code == 404
    assert get_document_response.status_code == 200, get_document_response.text


# --- document association -----------------------------------------------------


def test_add_document_to_collection_is_idempotent(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    collection = _create_collection(client, workspace["id"])
    document = _upload(client, workspace["id"])

    for _ in range(2):
        response = client.post(
            f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}/documents",
            json={"document_id": document["id"]},
            headers=csrf_headers(client),
        )
        assert response.status_code == 201, response.text

    get_response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}"
    )
    assert get_response.json()["document_count"] == 1


def test_add_document_from_another_workspace_returns_404(
    client_factory: Callable[[], TestClient]
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    collection_a = _create_collection(owner_a, workspace_a["id"])

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")
    document_b = _upload(owner_b, workspace_b["id"])

    response = owner_a.post(
        f"/api/v1/workspaces/{workspace_a['id']}/collections/{collection_a['id']}/documents",
        json={"document_id": document_b["id"]},
        headers=csrf_headers(owner_a),
    )

    assert response.status_code == 404


def test_remove_document_from_collection(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    collection = _create_collection(client, workspace["id"])
    document = _upload(client, workspace["id"])
    client.post(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}/documents",
        json={"document_id": document["id"]},
        headers=csrf_headers(client),
    )

    response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}/documents/{document['id']}",
        headers=csrf_headers(client),
    )
    get_response = client.get(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}"
    )

    assert response.status_code == 204, response.text
    assert get_response.json()["document_count"] == 0


def test_remove_document_not_in_collection_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    collection = _create_collection(client, workspace["id"])
    document = _upload(client, workspace["id"])

    response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/collections/{collection['id']}/documents/{document['id']}",
        headers=csrf_headers(client),
    )

    assert response.status_code == 404
