"""HTTP-level tests for the Slice 3.6/3.7 lifecycle extension: the existing

    POST /api/v1/workspaces/{workspace_id}/documents/{document_id}/process

endpoint continues past PARSED through CLEANED, CHUNKED, EMBEDDED, and
INDEXED, to READY, persisting `document_chunks` rows (Slice 3.6) and their
embedding vectors (Slice 3.7). Real Postgres/Redis/filesystem, no mocks,
matching this project's established convention (see
`tests/test_document_processing.py`, which this file complements rather
than duplicates — that file still owns extraction-stage-specific coverage;
this one owns cleaning/chunking/embedding/persistence/resume/concurrency).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.audit import AuditEvent
from app.ingestion import chunking
from app.ingestion.chunking import Chunk, ChunkingError
from app.ingestion.embedding import EmbeddingError
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.repositories import document_chunk_repository
from app.services import document_service
from app.services.storage_provider import LocalStorage, get_storage_provider
from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"


def _pdf_with_text(*, pages: int = 1, text: str = "Hello world.") -> bytes:
    """Hand-built so every page has genuinely extractable text, not just
    a valid-but-empty page -- Slice 3.7 treats a document with zero
    extractable text as a real, honest failure (see
    `app/services/document_service.py`), and these tests need to reach
    READY. Byte offsets are computed here, not hand-copied. Mirrors
    `tests/test_document_processing.py`'s identical helper."""
    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    ]
    page_object_numbers = list(range(3, 3 + pages))
    kids = " ".join(f"{n} 0 R" for n in page_object_numbers)
    objects.append(
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {pages} >>\nendobj\n".encode("ascii")
    )
    content_object_number = 3 + pages
    font_object_number = content_object_number + 1
    for page_number in page_object_numbers:
        objects.append(
            (
                f"{page_number} 0 obj\n<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 200 200] "
                f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
                f"/Contents {content_object_number} 0 R >>\nendobj\n"
            ).encode("ascii")
        )
    stream = f"BT /F1 24 Tf 10 100 Td ({text}) Tj ET".encode("latin-1")
    objects.append(
        b"%d 0 obj\n<< /Length %d >>\nstream\n" % (content_object_number, len(stream))
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(
        f"{font_object_number} 0 obj\n<< /Type /Font /Subtype /Type1 "
        f"/BaseFont /Helvetica >>\nendobj\n".encode("ascii")
    )

    header = b"%PDF-1.4\n"
    body = b""
    offsets = [0]
    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        body += obj
        pos += len(obj)

    xref_offset = len(header) + len(body)
    object_count = len(objects) + 1
    xref = b"xref\n0 %d\n0000000000 65535 f \n" % object_count
    for offset in offsets[1:]:
        xref += b"%010d 00000 n \n" % offset

    trailer = b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        object_count,
        xref_offset,
    )
    return header + body + xref + trailer


_PDF_BYTES = _pdf_with_text(pages=1)
_TXT_BYTES = b"Alpha beta gamma.\n\nDelta epsilon zeta eta theta iota kappa."


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
    client: TestClient, workspace_id: str, *, filename: str, content: bytes, content_type: str
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, content_type)},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _process(client: TestClient, workspace_id: str, document_id: str) -> Any:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
        headers=csrf_headers(client),
    )


def _chunks_for(db_session: DbSession, document_id: str) -> list[DocumentChunk]:
    return list(
        db_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == uuid.UUID(document_id))
            .order_by(DocumentChunk.chunk_index)
        ).scalars()
    )


def _audit_rows(db_session: DbSession, *, event_type: str, workspace_id: str) -> list[AuditLog]:
    return list(
        db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == event_type,
                AuditLog.workspace_id == uuid.UUID(workspace_id),
            )
        ).scalars()
    )


# --- full pipeline: UPLOADED -> ... -> READY, with persisted embeddings ----


def test_pdf_reaches_ready_with_persisted_chunks(client: TestClient, db_session: DbSession) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client,
        workspace["id"],
        filename="a.pdf",
        content=_PDF_BYTES,
        content_type="application/pdf",
    )

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"

    row = db_session.get(Document, uuid.UUID(document["id"]))
    assert row is not None
    assert row.status == DocumentStatus.READY


def test_txt_reaches_ready_and_chunks_are_persisted_with_correct_metadata(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"

    chunks = _chunks_for(db_session, document["id"])
    assert len(chunks) >= 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))  # gapless, zero-based
    assert all(c.document_id == uuid.UUID(document["id"]) for c in chunks)
    assert all(c.workspace_id == uuid.UUID(workspace["id"]) for c in chunks)
    assert all(c.content.strip() for c in chunks)  # no empty chunk rows
    # TXT has no page/heading -- both must be None, never invented.
    assert all(c.page is None for c in chunks)
    assert all(c.section is None for c in chunks)


def test_txt_reaches_ready_with_correctly_shaped_embeddings(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"

    chunks = _chunks_for(db_session, document["id"])
    assert chunks
    for chunk in chunks:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 384
        assert chunk.embedding_model == "local-hashing"
        assert chunk.embedding_dimension == 384
        # A non-empty chunk's vector is L2-normalized -- magnitude ~1.0.
        magnitude = sum(component * component for component in chunk.embedding) ** 0.5
        assert magnitude == pytest.approx(1.0, abs=1e-6)


def test_no_duplicate_chunk_rows_from_normal_processing(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    _process(client, workspace["id"], document["id"])

    chunks = _chunks_for(db_session, document["id"])
    indexes = [c.chunk_index for c in chunks]
    assert len(indexes) == len(set(indexes))  # no duplicate chunk_index values


def test_document_deletion_cascades_to_chunks(client: TestClient, db_session: DbSession) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    _process(client, workspace["id"], document["id"])
    assert _chunks_for(db_session, document["id"])

    row = db_session.get(Document, uuid.UUID(document["id"]))
    assert row is not None
    db_session.delete(row)
    db_session.flush()

    assert _chunks_for(db_session, document["id"]) == []


# --- resume behavior: PARSED / CLEANED / CHUNKED / EMBEDDED / INDEXED are --
# --- not terminal ------------------------------------------------------------


def test_resume_from_parsed_reaches_ready(client: TestClient, db_session: DbSession) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    # Simulate a prior interrupted attempt that got as far as PARSED and
    # no further (a real crash between the PARSED and CLEANED commits).
    row = db_session.get(Document, uuid.UUID(document["id"]))
    assert row is not None
    row.status = DocumentStatus.PARSED
    db_session.flush()

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"
    assert _chunks_for(db_session, document["id"])


def test_resume_from_cleaned_reaches_ready(client: TestClient, db_session: DbSession) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    row = db_session.get(Document, uuid.UUID(document["id"]))
    assert row is not None
    row.status = DocumentStatus.CLEANED
    db_session.flush()

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"
    assert _chunks_for(db_session, document["id"])


def test_resume_from_chunked_reaches_ready_without_reinserting_chunks(
    client: TestClient, db_session: DbSession
) -> None:
    # Simulates a crash after Slice 3.6's chunk-persistence commit but
    # before embedding ever ran: document_chunks rows already exist and
    # the document is already at CHUNKED. Resuming must skip extraction/
    # cleaning/chunking entirely -- proven here by asserting the exact
    # same chunk row IDs survive the resume, not a fresh, duplicate set.
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    doc_id = uuid.UUID(document["id"])
    ws_id = uuid.UUID(workspace["id"])

    row = db_session.get(Document, doc_id)
    assert row is not None
    row.status = DocumentStatus.CHUNKED
    db_session.flush()
    pre_existing = document_chunk_repository.bulk_create(
        db_session,
        document_id=doc_id,
        workspace_id=ws_id,
        chunks=[Chunk(chunk_index=0, page=None, section=None, content="Alpha beta gamma.")],
    )
    db_session.commit()
    pre_existing_ids = {chunk.id for chunk in pre_existing}

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"

    chunks = _chunks_for(db_session, document["id"])
    assert {chunk.id for chunk in chunks} == pre_existing_ids  # no re-chunking, no duplicates
    assert all(chunk.embedding is not None for chunk in chunks)


def test_resume_from_embedded_reaches_ready(client: TestClient, db_session: DbSession) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    # A normal run already drives this all the way to READY; roll it back
    # to EMBEDDED to simulate a crash between the EMBEDDED and INDEXED
    # commits, then resume.
    first = _process(client, workspace["id"], document["id"])
    assert first.json()["status"] == "READY"
    row = db_session.get(Document, uuid.UUID(document["id"]))
    assert row is not None
    row.status = DocumentStatus.EMBEDDED
    db_session.flush()

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"


# --- READY rejection ---------------------------------------------------------
# (see also test_document_processing.py's
# test_processing_an_already_ready_document_is_rejected_with_409, which
# covers the same behavior for a fresh, non-resumed document.)


def test_processing_an_already_ready_document_is_rejected_with_409_after_resume(
    client: TestClient,
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    first = _process(client, workspace["id"], document["id"])
    assert first.status_code == 200
    assert first.json()["status"] == "READY"

    second = _process(client, workspace["id"], document["id"])
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "document_already_processed"


# --- cleaning / chunking failure paths --------------------------------------


def test_cleaning_failure_transitions_to_failed_not_a_500(
    client: TestClient, db_session: DbSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_document: object) -> object:
        raise RuntimeError("simulated cleaning failure -- narrow, to prove this path is handled")

    monkeypatch.setattr(document_service, "clean_extracted_document", _boom)

    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert "simulated cleaning failure" not in body["failure_reason"]

    rows = _audit_rows(
        db_session, event_type=AuditEvent.DOCUMENT_CLEANING_FAILED, workspace_id=workspace["id"]
    )
    assert len(rows) == 1


def test_chunking_error_transitions_to_failed_not_a_500(
    client: TestClient, db_session: DbSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _AlwaysFailsChunker:
        def chunk(self, _document: object) -> list[Chunk]:
            raise ChunkingError("simulated chunking failure")

    monkeypatch.setattr(chunking, "StructureAwareChunker", _AlwaysFailsChunker)

    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_reason"] == "simulated chunking failure"
    assert _chunks_for(db_session, document["id"]) == []

    rows = _audit_rows(
        db_session, event_type=AuditEvent.DOCUMENT_CHUNKING_FAILED, workspace_id=workspace["id"]
    )
    assert len(rows) == 1


def test_unexpected_chunking_exception_transitions_to_failed_not_a_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _RaisesUnexpectedly:
        def chunk(self, _document: object) -> list[Chunk]:
            raise RuntimeError("totally unexpected failure")

    monkeypatch.setattr(chunking, "StructureAwareChunker", _RaisesUnexpectedly)

    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert "totally unexpected failure" not in body["failure_reason"]


# --- audit: successful chunking ---------------------------------------------


def test_successful_chunking_emits_exactly_one_document_chunked_audit_event(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    _process(client, workspace["id"], document["id"])

    rows = _audit_rows(
        db_session, event_type=AuditEvent.DOCUMENT_CHUNKED, workspace_id=workspace["id"]
    )
    assert len(rows) == 1
    assert rows[0].event_metadata is not None
    assert rows[0].event_metadata["document_id"] == document["id"]
    chunk_count = rows[0].event_metadata["chunk_count"]
    assert chunk_count == len(_chunks_for(db_session, document["id"]))


# --- embedding: success / failure paths (Slice 3.7) -------------------------


def test_embedding_failure_transitions_to_failed_not_a_500_and_preserves_chunks(
    client: TestClient, db_session: DbSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> list[list[float]]:
        raise EmbeddingError("simulated embedding provider failure")

    monkeypatch.setattr(document_service, "embed_with_retry", _boom)

    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_reason"] == "simulated embedding provider failure"

    # Chunking already committed before embedding was attempted -- a
    # failure here must not lose the already-persisted chunks, and none
    # of them should have an embedding written (the failed batch/attempt
    # never got that far, and set_embeddings() is never called).
    chunks = _chunks_for(db_session, document["id"])
    assert chunks
    assert all(chunk.embedding is None for chunk in chunks)

    rows = _audit_rows(
        db_session, event_type=AuditEvent.DOCUMENT_EMBEDDING_FAILED, workspace_id=workspace["id"]
    )
    assert len(rows) == 1


def test_zero_chunk_document_fails_with_a_clear_reason_not_ready(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _EmptyChunker:
        def chunk(self, _document: object) -> list[Chunk]:
            return []

    monkeypatch.setattr(chunking, "StructureAwareChunker", _EmptyChunker)

    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_reason"] == "The document contains no extractable text content to process."


def test_successful_processing_emits_exactly_one_document_ready_audit_event(
    client: TestClient, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    response = _process(client, workspace["id"], document["id"])
    assert response.json()["status"] == "READY"

    rows = _audit_rows(
        db_session, event_type=AuditEvent.DOCUMENT_READY, workspace_id=workspace["id"]
    )
    assert len(rows) == 1
    assert rows[0].event_metadata is not None
    assert rows[0].event_metadata["document_id"] == document["id"]
    assert rows[0].event_metadata["embedding_model"] == "local-hashing"
    assert rows[0].event_metadata["embedding_dimension"] == 384
    chunk_count = rows[0].event_metadata["chunk_count"]
    assert chunk_count == len(_chunks_for(db_session, document["id"]))


def test_no_document_cleaned_success_audit_event_exists() -> None:
    # Deliberate design decision, not an oversight: cleaning's success is
    # not separately audited (see document_service.process_document()'s
    # own docstring) -- only its failure is. Confirms the constant simply
    # doesn't exist, so nobody accidentally reintroduces audit noise for
    # this internal, always-conservative stage.
    assert not hasattr(AuditEvent, "DOCUMENT_CLEANED")


# --- authorization / workspace isolation for chunks -------------------------


def test_viewer_cannot_trigger_chunking(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    document = _upload(
        owner, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    viewer = client_factory()
    _login(viewer, viewer_email)

    response = _process(viewer, workspace["id"], document["id"])
    assert response.status_code == 403


def test_cross_workspace_chunks_are_not_reachable(
    client_factory: Callable[[], TestClient], db_session: DbSession
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    document = _upload(
        owner_a, workspace_a["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    _process(owner_a, workspace_a["id"], document["id"])
    chunks = _chunks_for(db_session, document["id"])
    assert chunks
    assert all(c.workspace_id == uuid.UUID(workspace_a["id"]) for c in chunks)

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")
    # The document (and its chunks) belong to workspace A -- unreachable
    # through workspace B's id, even for a real member of workspace B.
    response = _process(owner_b, workspace_b["id"], document["id"])
    assert response.status_code == 404


# --- concurrency: duplicate chunk-insert race -------------------------------


def test_concurrent_duplicate_chunk_insert_recovers_gracefully(
    client: TestClient, db_session: DbSession, tmp_path: Path
) -> None:
    # Simulates the exact race two simultaneous /process calls on the
    # same document would hit at the final persistence step: chunk rows
    # for this document_id/chunk_index pair already exist (as a
    # concurrent request would have just committed) by the time this
    # request's own bulk_create() runs. document_chunks' own
    # UNIQUE(document_id, chunk_index) constraint must catch this, and
    # the service must recover with a 200 (the other request's result),
    # never a raw 500.
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )
    doc_id = uuid.UUID(document["id"])
    ws_id = uuid.UUID(workspace["id"])

    # Pre-seed the exact chunks a real run would produce, as if a
    # concurrent request already won the race and committed them --
    # then also mark the document CHUNKED to match (a real winner would
    # have done both atomically).
    row = db_session.get(Document, doc_id)
    assert row is not None
    row.status = DocumentStatus.CLEANED  # this request will resume from here
    db_session.flush()

    winning_chunks = [Chunk(chunk_index=0, page=None, section=None, content="Alpha beta gamma.")]
    document_chunk_repository.bulk_create(
        db_session, document_id=doc_id, workspace_id=ws_id, chunks=winning_chunks
    )
    db_session.commit()

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text  # never a raw 500
    assert response.json()["status"] == "READY"
    # No duplicate rows: the pre-seeded chunk_index=0 row is still the
    # only one for that index, regardless of which path was taken.
    chunks = _chunks_for(db_session, document["id"])
    indexes = [c.chunk_index for c in chunks]
    assert len(indexes) == len(set(indexes))


# --- transaction / crash-safety for the new stages --------------------------


def test_cleaned_transition_is_committed_before_chunking_is_attempted(
    client: TestClient, db_session: DbSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set up the document (register/workspace/upload) *before* attaching
    # the commit tracker -- those calls share the same db_session and
    # commit for their own, unrelated reasons; tracking must only cover
    # what happens during the /process call itself.
    _register(client)
    workspace = _create_workspace(client)
    document = _upload(
        client, workspace["id"], filename="a.txt", content=_TXT_BYTES, content_type="text/plain"
    )

    order: list[str] = []
    real_commit = db_session.commit

    def _tracking_commit() -> None:
        order.append("commit")
        real_commit()

    real_chunker_cls = chunking.StructureAwareChunker

    class _TrackingChunker(real_chunker_cls):  # type: ignore[misc, valid-type]
        def chunk(self, document: object) -> list[Chunk]:
            order.append("chunking_started")
            return super().chunk(document)  # type: ignore[no-any-return]

    monkeypatch.setattr(db_session, "commit", _tracking_commit)
    monkeypatch.setattr(chunking, "StructureAwareChunker", _TrackingChunker)

    response = _process(client, workspace["id"], document["id"])
    assert response.status_code == 200, response.text

    # 4 commits happen before chunking should ever start, not 3: PROCESSING
    # (1 commit), PARSED (2 -- record_audit_event()'s own repository
    # commits internally for DOCUMENT_PARSED, and the explicit db.commit()
    # right after it is a second, harmless no-op commit on top -- the same
    # confirmed-and-accepted pattern from Slices 3.3/3.4), CLEANED (1,
    # no audit event recorded for this internal, always-conservative
    # stage -- see process_document()'s own docstring). Whatever the
    # exact count, chunking must not begin until every one of them has
    # already happened.
    chunking_index = order.index("chunking_started")
    commits_before_chunking = order[:chunking_index].count("commit")
    assert commits_before_chunking == 4, order


@pytest.mark.asyncio
async def test_slow_chunking_does_not_block_unrelated_concurrent_requests(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mirrors the identical Slice 3.4 regression test for extraction --
    # chunking is also synchronous, CPU-bound work and must run via
    # asyncio.to_thread(), not directly on the event loop, or a single
    # slow/large document would stall every other concurrent request
    # this single-process server is serving. Absolute shared clock
    # (t_zero), not per-coroutine-relative timing -- a relative measure
    # would hide exactly this class of bug (see Slice 3.4's own report
    # on why an earlier draft of that diagnostic was itself misleading).
    app.dependency_overrides[get_storage_provider] = lambda: LocalStorage(root=str(tmp_path))

    class _SlowChunker:
        def chunk(self, _document: object) -> list[Chunk]:
            time.sleep(1.0)
            return [Chunk(chunk_index=0, page=None, section=None, content="x")]

    monkeypatch.setattr(chunking, "StructureAwareChunker", _SlowChunker)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        csrf_response = await async_client.get("/api/v1/auth/csrf")
        csrf_token = csrf_response.cookies.get("csrf_token")
        headers = {"X-CSRF-Token": csrf_token or ""}

        register_response = await async_client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email(), "password": _PASSWORD},
            headers=headers,
        )
        assert register_response.status_code == 201, register_response.text

        workspace_response = await async_client.post(
            "/api/v1/workspaces", json={"name": "concurrency-check"}, headers=headers
        )
        assert workspace_response.status_code == 201, workspace_response.text
        workspace_id = workspace_response.json()["id"]

        upload_response = await async_client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files={"file": ("a.txt", _TXT_BYTES, "text/plain")},
            headers=headers,
        )
        assert upload_response.status_code == 201, upload_response.text
        document_id = upload_response.json()["id"]

        t_zero = time.monotonic()

        async def slow_process() -> None:
            response = await async_client.post(
                f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
                headers=headers,
            )
            assert response.status_code == 200, response.text

        async def fast_health() -> float:
            await asyncio.sleep(0.2)
            response = await async_client.get("/api/v1/health")
            assert response.status_code == 200
            return time.monotonic() - t_zero

        _, fast_finish = await asyncio.gather(slow_process(), fast_health())

    assert fast_finish < 0.6  # generous; well under the 1s slow-chunk duration
