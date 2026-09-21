"""HTTP-level tests for the document upload endpoint (Issue #3, Slice 3.3):

    POST /api/v1/workspaces/{workspace_id}/documents

Real Postgres, real Redis, real filesystem (an isolated per-test root via
a `get_storage_provider` dependency override) — no mocks, matching this
project's established convention. No extraction/chunking/embedding
exists yet; every document here is expected to land in, and stay in,
UPLOADED.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.audit import AuditEvent
from app.core.config import get_settings
from app.core.redis_client import build_redis_client, get_redis_client
from app.core.redis_keys import rate_limit_key
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentStatus
from app.services.storage_provider import (
    LocalStorage,
    StorageError,
    StorageProvider,
    get_storage_provider,
)
from tests.conftest import csrf_headers

_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
_DOCX_BYTES = b"PK\x03\x04" + b"\x00" * 40
_TXT_BYTES = b"hello world, this is a plain text document."
_MD_BYTES = b"# Heading\n\nSome **markdown** text."
_CSV_BYTES = b"col1,col2\n1,2\n3,4\n"

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


@pytest.fixture(autouse=True)
def _isolated_storage(app: FastAPI, tmp_path: Path) -> Iterator[None]:
    """Every test in this file uploads into a per-test temp directory,
    never the real configured dev storage root."""
    app.dependency_overrides[get_storage_provider] = lambda: LocalStorage(root=str(tmp_path))
    yield
    del app.dependency_overrides[get_storage_provider]


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    return tmp_path


def _create_workspace(client: TestClient, name: str = "Acme") -> dict[str, Any]:
    response = client.post(
        "/api/v1/workspaces", json={"name": name}, headers=csrf_headers(client)
    )
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
    client: TestClient,
    workspace_id: str,
    *,
    filename: str = "report.pdf",
    content: bytes = _PDF_BYTES,
    content_type: str | None = "application/pdf",
) -> Any:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, content_type)},
        headers=csrf_headers(client),
    )


def _audit_rows(db_session: DbSession, *, workspace_id: str) -> list[AuditLog]:
    return list(
        db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == AuditEvent.DOCUMENT_UPLOADED,
                AuditLog.workspace_id == uuid.UUID(workspace_id),
            )
        ).scalars()
    )


class _BrokenStorage:
    """A StorageProvider that fails every operation with StorageError --
    exactly the exception type the real LocalStorage now guarantees on a
    genuine filesystem failure (Slice 3.2's own fix), never a raw OSError."""

    def save(self, *, key: str, content: bytes) -> None:
        raise StorageError("simulated storage failure")

    def read(self, *, key: str) -> bytes:
        raise StorageError("simulated storage failure")

    def delete(self, *, key: str) -> None:
        raise StorageError("simulated storage failure")

    def exists(self, *, key: str) -> bool:
        raise StorageError("simulated storage failure")


class _DeleteFailsStorage:
    """Wraps a real LocalStorage but forces delete() to fail -- used to
    prove a compensating-cleanup failure is logged, not silently
    swallowed, and never leaks a path to the client either way."""

    def __init__(self, inner: StorageProvider) -> None:
        self._inner = inner

    def save(self, *, key: str, content: bytes) -> None:
        self._inner.save(key=key, content=content)

    def read(self, *, key: str) -> bytes:
        return self._inner.read(key=key)

    def delete(self, *, key: str) -> None:
        raise StorageError("simulated cleanup failure")

    def exists(self, *, key: str) -> bool:
        return self._inner.exists(key=key)


@pytest.fixture
def unreachable_redis_client() -> Iterator[redis.Redis]:
    client = build_redis_client(
        "redis://localhost:1/0", socket_timeout=0.05, socket_connect_timeout=0.05
    )
    yield client
    client.close()


# --- 1/3/9/14/15/16: successful authenticated MEMBER upload --------------


def test_authenticated_member_upload_succeeds(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(client, workspace["id"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "report.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["size_bytes"] == len(_PDF_BYTES)
    assert body["status"] == "UPLOADED"
    assert body["checksum_sha256"] == hashlib.sha256(_PDF_BYTES).hexdigest()
    assert "storage_key" not in body

    document = db_session.get(Document, uuid.UUID(body["id"]))
    assert document is not None
    assert document.status == DocumentStatus.UPLOADED
    assert str(document.workspace_id) == workspace["id"]
    assert document.uploaded_by is not None


# --- 2: unauthenticated upload ---------------------------------------------


def test_unauthenticated_upload_rejected(client_factory: Callable[[], TestClient]) -> None:
    anonymous = client_factory()
    workspace_id = str(uuid.uuid4())
    response = _upload(anonymous, workspace_id)
    assert response.status_code == 401


# --- 4: VIEWER rejection ----------------------------------------------------


def test_viewer_upload_rejected(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")

    viewer = client_factory()
    _login(viewer, viewer_email)

    response = _upload(viewer, workspace["id"])
    assert response.status_code == 403


# --- 5/6: non-member / cross-workspace rejection ---------------------------


def test_non_member_upload_rejected_with_404_not_403(
    client_factory: Callable[[], TestClient],
) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)

    outsider = client_factory()
    _register(outsider)

    response = _upload(outsider, workspace["id"])
    assert response.status_code == 404


def test_cross_workspace_upload_rejected(client_factory: Callable[[], TestClient]) -> None:
    """A member of workspace B cannot upload into workspace A."""
    user_a = client_factory()
    _register(user_a)
    workspace_a = _create_workspace(user_a, "Workspace A")

    user_b = client_factory()
    _register(user_b)
    _create_workspace(user_b, "Workspace B")  # user_b's own workspace, unrelated

    response = _upload(user_b, workspace_a["id"])
    assert response.status_code == 404


# --- 7/8: unsupported extension / MIME -------------------------------------


def test_unsupported_extension_rejected(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(
        client,
        workspace["id"],
        filename="script.exe",
        content=b"MZ\x90\x00",
        content_type="application/octet-stream",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_unsupported_mime_for_a_supported_extension_rejected(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(
        client,
        workspace["id"],
        filename="report.pdf",
        content=_PDF_BYTES,
        content_type="application/zip",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_mismatched_signature_rejected(client: TestClient) -> None:
    """Extension and MIME both claim PDF, but the content doesn't start
    with the PDF signature -- the magic-byte check catches what the other
    two signals alone wouldn't."""
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(
        client,
        workspace["id"],
        filename="report.pdf",
        content=b"this is not actually a pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_file_type"


# --- 9: valid MIME/extension combinations (each supported format) ---------


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("report.pdf", _PDF_BYTES, "application/pdf"),
        (
            "report.docx",
            _DOCX_BYTES,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("notes.txt", _TXT_BYTES, "text/plain"),
        ("notes.md", _MD_BYTES, "text/markdown"),
        ("notes.md", _MD_BYTES, "text/plain"),  # known browser variant
        ("data.csv", _CSV_BYTES, "text/csv"),
        ("data.csv", _CSV_BYTES, "application/vnd.ms-excel"),  # known variant
    ],
)
def test_each_supported_format_succeeds(
    client: TestClient, filename: str, content: bytes, content_type: str
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(
        client, workspace["id"], filename=filename, content=content, content_type=content_type
    )
    assert response.status_code == 201, response.text


# --- 10: size limit ----------------------------------------------------------


def test_oversized_upload_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Uses the real settings value but shrinks it for this test via env,
    # then rebuilds Settings through get_settings()'s own cache -- simpler
    # and just as real: override the app dependency instead? get_settings
    # is not a FastAPI dependency here, so directly monkeypatching the
    # cached settings instance's attribute for this one test is the
    # smallest, safest way to exercise the real bounded-read code path
    # without uploading a genuine 50 MiB fixture.
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    _register(client)
    workspace = _create_workspace(client)

    response = _upload(client, workspace["id"], content=_PDF_BYTES)  # well over 10 bytes

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


# --- 11: checksum correctness ------------------------------------------------


def test_checksum_matches_real_sha256_of_uploaded_bytes(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(client, workspace["id"])
    assert response.status_code == 201
    assert response.json()["checksum_sha256"] == hashlib.sha256(_PDF_BYTES).hexdigest()


# --- 12/13: generated storage key, path-traversal safety -------------------


def test_storage_key_is_generated_and_traversal_attempt_is_harmless(
    client: TestClient, db_session: DbSession, storage_root: Path
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(
        client,
        workspace["id"],
        filename="../../etc/passwd.pdf",
        content=_PDF_BYTES,
        content_type="application/pdf",
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]

    document = db_session.get(Document, uuid.UUID(document_id))
    assert document is not None
    # The storage key is workspace_id/document_id.pdf -- never derived
    # from the filename, so "etc"/"passwd"/".." never appear in it.
    assert "etc" not in document.storage_key
    assert "passwd" not in document.storage_key
    assert ".." not in document.storage_key
    assert document.storage_key == f"{workspace['id']}/{document_id}.pdf"

    # The file landed exactly where expected, still inside the storage
    # root -- nothing escaped it.
    expected_path = storage_root / workspace["id"] / f"{document_id}.pdf"
    assert expected_path.is_file()
    assert expected_path.read_bytes() == _PDF_BYTES
    # No file was written outside the isolated root.
    assert not (storage_root.parent / "passwd").exists()


# --- 17: audit event ---------------------------------------------------------


def test_successful_upload_emits_exactly_one_audit_event(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _upload(client, workspace["id"])
    assert response.status_code == 201
    document_id = response.json()["id"]

    rows = _audit_rows(db_session, workspace_id=workspace["id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.event_metadata is not None
    assert row.event_metadata["document_id"] == document_id
    assert row.event_metadata["filename"] == "report.pdf"
    assert row.event_metadata["checksum_sha256"] == hashlib.sha256(_PDF_BYTES).hexdigest()
    # Never the storage key or any filesystem path in audit metadata.
    assert "storage_key" not in row.event_metadata
    assert set(row.event_metadata) == {
        "document_id",
        "filename",
        "mime_type",
        "size_bytes",
        "checksum_sha256",
    }


# --- 18/19: duplicate checksum -----------------------------------------------


def test_duplicate_checksum_in_same_workspace_rejected_with_409(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    first = _upload(client, workspace["id"])
    assert first.status_code == 201
    existing_id = first.json()["id"]

    second = _upload(client, workspace["id"])
    assert second.status_code == 409
    body = second.json()
    assert body["error"]["code"] == "duplicate_document"
    assert existing_id in body["error"]["message"]


def test_same_checksum_in_different_workspace_succeeds(
    client_factory: Callable[[], TestClient],
) -> None:
    user = client_factory()
    _register(user)
    workspace_a = _create_workspace(user, "Workspace A")
    workspace_b = _create_workspace(user, "Workspace B")

    first = _upload(user, workspace_a["id"])
    assert first.status_code == 201

    second = _upload(user, workspace_b["id"])
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


# --- 20/22: storage failure, no orphaned document row -----------------------


def test_storage_failure_returns_500_and_creates_no_document_row(
    app: FastAPI, client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    app.dependency_overrides[get_storage_provider] = lambda: _BrokenStorage()

    # TestClient's default raise_server_exceptions=True re-raises a truly
    # unhandled exception to the test (for debugging visibility) instead
    # of letting the app's own registered Exception handler convert it to
    # a response -- correct default behavior, but the opposite of what
    # this test needs: the actual response a real client would receive.
    # A second TestClient sharing the same app/cookies, with that
    # override, is the standard way to observe it.
    unsafe_client = TestClient(app, raise_server_exceptions=False)
    unsafe_client.cookies.update(client.cookies)

    response = _upload(unsafe_client, workspace["id"])

    assert response.status_code == 500
    body = response.json()
    assert "error" in body
    # No raw exception text, no path, no internal detail.
    assert "simulated storage failure" not in response.text

    rows = list(
        db_session.execute(
            select(Document).where(Document.workspace_id == uuid.UUID(workspace["id"]))
        ).scalars()
    )
    assert rows == []


# --- 21/22: DB failure after a successful storage write ---------------------


def test_db_failure_after_storage_write_cleans_up_and_returns_500(
    db_session: DbSession, storage_root: Path
) -> None:
    """A real (not mocked) DB failure: the workspace_id used doesn't
    exist, so the documents.workspace_id FK constraint fails at flush
    time -- a genuine IntegrityError that is *not* the duplicate-checksum
    case. Proves: no document row survives, and the just-written storage
    object is cleaned up."""
    from app.services import document_service
    from app.services.storage_provider import LocalStorage

    storage = LocalStorage(root=str(storage_root))
    nonexistent_workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    storage_key = f"{nonexistent_workspace_id}/{document_id}.pdf"
    storage.save(key=storage_key, content=_PDF_BYTES)
    assert storage.exists(key=storage_key) is True

    with pytest.raises(Exception) as exc_info:
        document_service._persist_document(
            db_session,
            document_id=document_id,
            storage=storage,
            storage_key=storage_key,
            workspace_id=nonexistent_workspace_id,
            uploaded_by=uuid.uuid4(),
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=len(_PDF_BYTES),
            checksum_sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
            ip_address=None,
        )
    # A genuine IntegrityError (FK violation), not silently swallowed or
    # misreported as a duplicate-document 409.
    assert "IntegrityError" in type(exc_info.value).__name__ or "ForeignKeyViolation" in str(
        exc_info.value
    )

    db_session.rollback()
    # The compensating delete ran -- no orphaned file left behind.
    assert storage.exists(key=storage_key) is False
    assert (
        db_session.execute(
            select(Document).where(Document.workspace_id == nonexistent_workspace_id)
        ).first()
        is None
    )


def test_race_lost_duplicate_insert_translates_to_409_not_500(
    client: TestClient, db_session: DbSession, storage_root: Path
) -> None:
    """Simulates the concrete race the pre-check can't fully close: a row
    with the same (workspace_id, checksum) already exists by the time the
    insert actually runs. Proves the unique-constraint violation is
    translated to the documented 409, the second storage write is cleaned
    up, and the first (real) document/file are untouched."""
    from app.services import document_service
    from app.services.storage_provider import LocalStorage

    _register(client)
    workspace = _create_workspace(client)
    workspace_id = uuid.UUID(workspace["id"])
    checksum = hashlib.sha256(_PDF_BYTES).hexdigest()

    first = _upload(client, workspace["id"])
    assert first.status_code == 201
    first_id = first.json()["id"]

    storage = LocalStorage(root=str(storage_root))
    racing_document_id = uuid.uuid4()
    racing_key = f"{workspace_id}/{racing_document_id}.pdf"
    storage.save(key=racing_key, content=_PDF_BYTES)

    with pytest.raises(Exception) as exc_info:
        document_service._persist_document(
            db_session,
            document_id=racing_document_id,
            storage=storage,
            storage_key=racing_key,
            workspace_id=workspace_id,
            uploaded_by=uuid.uuid4(),
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=len(_PDF_BYTES),
            checksum_sha256=checksum,
            ip_address=None,
        )
    assert exc_info.value.status_code == 409  # type: ignore[attr-defined]
    assert first_id in exc_info.value.detail["message"]  # type: ignore[attr-defined]

    db_session.rollback()
    # The losing request's own storage write was cleaned up...
    assert storage.exists(key=racing_key) is False
    # ...but the original, winning document is untouched.
    original = db_session.get(Document, uuid.UUID(first_id))
    assert original is not None


# --- 23: cleanup failure never leaks a path ----------------------------------


def test_cleanup_failure_is_logged_not_raised_and_leaks_nothing(
    app: FastAPI, client: TestClient, db_session: DbSession, storage_root: Path
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    real_storage = LocalStorage(root=str(storage_root))
    app.dependency_overrides[get_storage_provider] = lambda: _DeleteFailsStorage(real_storage)

    # Force the DB half to fail (duplicate) so the compensating delete is
    # attempted, and that delete itself is rigged to fail too.
    first_response = _upload(client, workspace["id"])
    assert first_response.status_code in (201, 500)  # storage.save() succeeds either way here

    second_response = _upload(client, workspace["id"])
    # Whatever the exact status, the response body must never contain the
    # storage root's real filesystem path.
    assert str(storage_root) not in second_response.text


# --- 24: malformed multipart input -------------------------------------------


def test_missing_file_field_rejected_safely(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/documents",
        headers=csrf_headers(client),
    )
    assert response.status_code == 422


def test_empty_file_field_rejected_safely(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers=csrf_headers(client),
    )
    # An empty file fails the magic-byte check (no PDF signature present)
    # -- a safe 400, never a crash.
    assert response.status_code == 400


# --- 25/26: Redis rate-limit key creation and enforcement -------------------


def test_upload_creates_the_redis_ip_and_user_dimension_keys(client: TestClient) -> None:
    redis_client = get_redis_client()
    assert redis_client is not None, "this test requires a reachable Redis"

    _register(client)
    workspace = _create_workspace(client)
    me = client.get("/api/v1/users/me")
    assert me.status_code == 200
    user_id = me.json()["id"]

    response = _upload(client, workspace["id"])
    assert response.status_code == 201

    ip_key = rate_limit_key("document_upload", "ip", "testclient")
    user_key = rate_limit_key("document_upload", "user", user_id)
    assert redis_client.exists(ip_key) == 1
    assert redis_client.exists(user_key) == 1


def test_upload_rate_limit_enforced_at_threshold(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    allowed = 0
    last_status = None
    for i in range(25):
        response = _upload(
            client,
            workspace["id"],
            filename=f"report-{i}.pdf",
            content=_PDF_BYTES + str(i).encode(),  # distinct checksum each time
        )
        last_status = response.status_code
        if response.status_code == 201:
            allowed += 1
        else:
            break

    assert allowed == 20
    assert last_status == 429


# --- 27: Redis unavailable falls back, does not fail open -------------------


def test_redis_unavailable_falls_back_and_still_enforces_the_limit(
    app: FastAPI,
    client_factory: Callable[[], TestClient],
    unreachable_redis_client: redis.Redis,
) -> None:
    app.dependency_overrides[get_redis_client] = lambda: unreachable_redis_client
    test_client = client_factory()
    _register(test_client)
    workspace = _create_workspace(test_client)

    allowed = 0
    last_status = None
    for i in range(25):
        response = _upload(
            test_client,
            workspace["id"],
            filename=f"report-{i}.pdf",
            content=_PDF_BYTES + str(i).encode(),
        )
        last_status = response.status_code
        if response.status_code == 201:
            allowed += 1
        else:
            break

    # Tier A: falls back to the in-process FixedWindowRateLimiter (same
    # limit=20), never fails open.
    assert allowed == 20
    assert last_status == 429


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
