"""HTTP-level tests for document management beyond list/get/upload/
process (GitHub Issue #41, feature-completion sprint priority 5):
rename, delete, download, and filter/search over the document list.
Real Postgres/filesystem, no mocks, matching this project's established
integration-testing convention.
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

from app.models.citation import Citation
from app.models.document_chunk import DocumentChunk
from app.models.message import Message, MessageRole
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


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    return tmp_path


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
    client: TestClient, workspace_id: str, *, filename: str = "a.txt", content: bytes = _TXT_BYTES
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, "text/plain")},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _ingest_ready_document(
    client: TestClient, workspace_id: str, *, filename: str = "a.txt", content: bytes = _TXT_BYTES
) -> dict[str, Any]:
    document = _upload(client, workspace_id, filename=filename, content=content)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}/process",
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"
    return document


def _rename(client: TestClient, workspace_id: str, document_id: str, filename: str) -> Any:
    return client.patch(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        json={"filename": filename},
        headers=csrf_headers(client),
    )


def _delete(client: TestClient, workspace_id: str, document_id: str) -> Any:
    return client.delete(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=csrf_headers(client),
    )


def _download(client: TestClient, workspace_id: str, document_id: str) -> Any:
    return client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/download")


# --- rename -------------------------------------------------------------------


def test_rename_document_updates_filename(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(client, workspace["id"])

    response = _rename(client, workspace["id"], document["id"], "new-name.txt")

    assert response.status_code == 200, response.text
    assert response.json()["filename"] == "new-name.txt"

    get_response = client.get(f"/api/v1/workspaces/{workspace['id']}/documents/{document['id']}")
    assert get_response.json()["filename"] == "new-name.txt"


def test_rename_document_not_found_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = _rename(client, workspace["id"], str(uuid.uuid4()), "new-name.txt")
    assert response.status_code == 404


def test_rename_cross_workspace_is_not_reachable(client_factory: Callable[[], TestClient]) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    document = _upload(owner_a, workspace_a["id"])

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = _rename(owner_b, workspace_b["id"], document["id"], "stolen.txt")
    assert response.status_code == 404


def test_viewer_cannot_rename_document(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    document = _upload(owner, workspace["id"])

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    viewer = client_factory()
    _login(viewer, viewer_email)

    response = _rename(viewer, workspace["id"], document["id"], "renamed.txt")
    assert response.status_code == 403


def test_rename_rejects_an_empty_filename(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(client, workspace["id"])

    response = _rename(client, workspace["id"], document["id"], "")
    assert response.status_code == 422


# --- download -----------------------------------------------------------------


def test_download_document_returns_original_bytes(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(client, workspace["id"], filename="report.txt", content=_TXT_BYTES)

    response = _download(client, workspace["id"], document["id"])

    assert response.status_code == 200, response.text
    assert response.content == _TXT_BYTES
    assert response.headers["content-type"].startswith("text/plain")
    assert 'filename="report.txt"' in response.headers["content-disposition"]


def test_download_sanitizes_an_unsafe_filename_in_the_header(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(client, workspace["id"], content=_TXT_BYTES)
    # A filename is purely a display label (never used as a storage
    # path) -- rename it to something that would corrupt the
    # Content-Disposition header, or inject a second header, if used
    # verbatim.
    unsafe_filename = 'evil"\r\nX-Injected: true'
    rename_response = _rename(client, workspace["id"], document["id"], unsafe_filename)
    assert rename_response.status_code == 200, rename_response.text

    response = _download(client, workspace["id"], document["id"])

    assert response.status_code == 200, response.text
    content_disposition = response.headers["content-disposition"]
    assert "\r" not in content_disposition
    assert "\n" not in content_disposition
    assert '"' not in content_disposition[len('attachment; filename="') : -1]
    assert "X-Injected" not in response.headers
    assert "x-injected" not in response.headers


def test_download_document_not_found_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = _download(client, workspace["id"], str(uuid.uuid4()))
    assert response.status_code == 404


def test_download_cross_workspace_is_not_reachable(
    client_factory: Callable[[], TestClient]
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    document = _upload(owner_a, workspace_a["id"])

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = _download(owner_b, workspace_b["id"], document["id"])
    assert response.status_code == 404


def test_viewer_can_download_document(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    document = _upload(owner, workspace["id"])

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    viewer = client_factory()
    _login(viewer, viewer_email)

    response = _download(viewer, workspace["id"], document["id"])
    assert response.status_code == 200, response.text


# --- delete -------------------------------------------------------------------


def test_delete_document_removes_row_and_storage_file(
    client: TestClient, storage_root: Path
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(client, workspace["id"])
    expected_path = storage_root / workspace["id"] / f"{document['id']}.txt"
    assert expected_path.is_file()

    response = _delete(client, workspace["id"], document["id"])

    assert response.status_code == 204, response.text
    assert not expected_path.exists()

    get_response = client.get(f"/api/v1/workspaces/{workspace['id']}/documents/{document['id']}")
    assert get_response.status_code == 404


def test_delete_document_not_found_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = _delete(client, workspace["id"], str(uuid.uuid4()))
    assert response.status_code == 404


def test_delete_cross_workspace_is_not_reachable(client_factory: Callable[[], TestClient]) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    document = _upload(owner_a, workspace_a["id"])

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = _delete(owner_b, workspace_b["id"], document["id"])
    assert response.status_code == 404


def test_viewer_cannot_delete_document(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    document = _upload(owner, workspace["id"])

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    viewer = client_factory()
    _login(viewer, viewer_email)

    response = _delete(viewer, workspace["id"], document["id"])
    assert response.status_code == 403


def test_delete_document_cascades_chunks_and_citations_but_preserves_message_content(
    client: TestClient, db_session: DbSession
) -> None:
    """The documented, deliberate consequence of deleting a document
    (docs/API_CONTRACT.md "Document delete"): its chunks and any
    citations pointing at them cascade-delete, but a chat message's own
    text content is never affected -- there is no foreign key from
    `messages` to `documents` at all."""
    _register(client)
    workspace = _create_workspace(client)
    document = _ingest_ready_document(client, workspace["id"])
    conversation = client.post(
        f"/api/v1/workspaces/{workspace['id']}/conversations", headers=csrf_headers(client)
    ).json()
    post_response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/messages",
        json={"content": "What is the refund policy?"},
        headers=csrf_headers(client),
    )
    assert post_response.status_code == 201, post_response.text
    assistant_message_id = post_response.json()["id"]
    assert len(post_response.json()["citations"]) >= 1

    response = _delete(client, workspace["id"], document["id"])
    assert response.status_code == 204, response.text

    remaining_chunks = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document["id"]))
    ).scalars().all()
    assert remaining_chunks == []

    remaining_citations = db_session.execute(
        select(Citation).where(Citation.message_id == uuid.UUID(assistant_message_id))
    ).scalars().all()
    assert remaining_citations == []

    # The message itself -- its actual answer text -- still exists.
    assistant_message = db_session.get(Message, uuid.UUID(assistant_message_id))
    assert assistant_message is not None
    assert assistant_message.role == MessageRole.ASSISTANT
    assert "refund policy" in assistant_message.content


# --- list filter/search --------------------------------------------------------


def test_list_documents_filters_by_status(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    _ingest_ready_document(client, workspace["id"], filename="ready.txt", content=_TXT_BYTES)
    _upload(client, workspace["id"], filename="uploaded.txt", content=b"different content")

    response = client.get(f"/api/v1/workspaces/{workspace['id']}/documents?status=READY")

    assert response.status_code == 200, response.text
    filenames = {d["filename"] for d in response.json()}
    assert filenames == {"ready.txt"}


def test_list_documents_searches_by_filename(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    _upload(client, workspace["id"], filename="refund-policy.txt", content=b"refund content")
    _upload(client, workspace["id"], filename="shipping-times.txt", content=b"shipping content")

    response = client.get(f"/api/v1/workspaces/{workspace['id']}/documents?q=refund")

    assert response.status_code == 200, response.text
    filenames = {d["filename"] for d in response.json()}
    assert filenames == {"refund-policy.txt"}
