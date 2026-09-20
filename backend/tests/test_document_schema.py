"""Schema-only tests for GitHub Issue #3 Slice 3.1 (`documents` /
`document_chunks`). No API, storage, extraction, chunking, or embedding
code exists yet — these tests exercise the real Postgres schema directly
through the ORM, following this project's established no-mock-datastore
convention (docs/DECISIONS/0002; `tests/conftest.py`'s `db_session`).

The session-scoped `_migrated_database` autouse fixture (`conftest.py`)
already proves migration `0004` applies cleanly to a fresh database before
any test in the suite runs — if it didn't, every test here (and every
other test file) would fail at collection/session start.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.db import engine
from app.models import Document, DocumentChunk, DocumentStatus, User, Workspace


def _make_workspace(db_session: DbSession, name: str = "Test workspace") -> Workspace:
    workspace = Workspace(name=name)
    db_session.add(workspace)
    db_session.flush()
    return workspace


def _make_user(db_session: DbSession, email: str | None = None) -> User:
    user = User(
        email=email or f"user-{uuid.uuid4()}@example.com",
        password_hash="not-a-real-hash",
    )
    db_session.add(user)
    db_session.flush()
    return user


def _make_document(
    db_session: DbSession,
    *,
    workspace: Workspace,
    uploader: User | None = None,
    checksum: str | None = None,
    storage_key: str | None = None,
) -> Document:
    document = Document(
        workspace_id=workspace.id,
        uploaded_by=uploader.id if uploader is not None else None,
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256=checksum or uuid.uuid4().hex,
        storage_key=storage_key or f"{workspace.id}/{uuid.uuid4()}.pdf",
    )
    db_session.add(document)
    db_session.flush()
    return document


def test_documents_table_exists(db_session: DbSession) -> None:
    inspector = sa.inspect(engine)
    assert "documents" in inspector.get_table_names()


def test_document_chunks_table_exists(db_session: DbSession) -> None:
    inspector = sa.inspect(engine)
    assert "document_chunks" in inspector.get_table_names()


def test_document_can_reference_an_existing_workspace(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)

    fetched = db_session.get(Document, document.id)
    assert fetched is not None
    assert fetched.workspace_id == workspace.id


def test_document_can_reference_an_existing_uploader(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    user = _make_user(db_session)
    document = _make_document(db_session, workspace=workspace, uploader=user)

    fetched = db_session.get(Document, document.id)
    assert fetched is not None
    assert fetched.uploaded_by == user.id


def test_document_uploaded_by_is_nullable(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace, uploader=None)

    fetched = db_session.get(Document, document.id)
    assert fetched is not None
    assert fetched.uploaded_by is None


def test_invalid_workspace_fk_is_rejected(db_session: DbSession) -> None:
    document = Document(
        workspace_id=uuid.uuid4(),  # no such workspace
        filename="ghost.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        checksum_sha256=uuid.uuid4().hex,
        storage_key=str(uuid.uuid4()),
    )
    db_session.add(document)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_unique_workspace_and_checksum_constraint(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    checksum = uuid.uuid4().hex
    _make_document(db_session, workspace=workspace, checksum=checksum)
    db_session.flush()

    duplicate = Document(
        workspace_id=workspace.id,
        filename="duplicate.pdf",
        mime_type="application/pdf",
        size_bytes=2048,
        checksum_sha256=checksum,
        storage_key=str(uuid.uuid4()),
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_checksum_allowed_across_different_workspaces(db_session: DbSession) -> None:
    workspace_a = _make_workspace(db_session, name="Workspace A")
    workspace_b = _make_workspace(db_session, name="Workspace B")
    checksum = uuid.uuid4().hex

    _make_document(db_session, workspace=workspace_a, checksum=checksum)
    _make_document(db_session, workspace=workspace_b, checksum=checksum)
    db_session.flush()  # no IntegrityError — isolation is per-workspace, not global


def test_unique_storage_key_constraint(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    storage_key = str(uuid.uuid4())
    _make_document(db_session, workspace=workspace, storage_key=storage_key)
    db_session.flush()

    duplicate = Document(
        workspace_id=workspace.id,
        filename="other.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        checksum_sha256=uuid.uuid4().hex,
        storage_key=storage_key,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_chunk_references_document(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)

    chunk = DocumentChunk(
        document_id=document.id,
        workspace_id=workspace.id,
        chunk_index=0,
        content="First chunk of the document.",
    )
    db_session.add(chunk)
    db_session.flush()

    fetched = db_session.get(DocumentChunk, chunk.id)
    assert fetched is not None
    assert fetched.document_id == document.id


def test_chunk_references_workspace(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)

    chunk = DocumentChunk(
        document_id=document.id,
        workspace_id=workspace.id,
        chunk_index=0,
        content="Chunk content.",
    )
    db_session.add(chunk)
    db_session.flush()

    fetched = db_session.get(DocumentChunk, chunk.id)
    assert fetched is not None
    assert fetched.workspace_id == workspace.id


def test_invalid_document_fk_is_rejected_for_chunks(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    chunk = DocumentChunk(
        document_id=uuid.uuid4(),  # no such document
        workspace_id=workspace.id,
        chunk_index=0,
        content="Orphan chunk.",
    )
    db_session.add(chunk)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_unique_document_and_chunk_index_constraint(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)

    db_session.add(
        DocumentChunk(
            document_id=document.id, workspace_id=workspace.id, chunk_index=0, content="First."
        )
    )
    db_session.flush()

    db_session.add(
        DocumentChunk(
            document_id=document.id, workspace_id=workspace.id, chunk_index=0, content="Dup."
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_chunk_index_allowed_across_different_documents(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document_a = _make_document(db_session, workspace=workspace)
    document_b = _make_document(db_session, workspace=workspace)

    db_session.add(
        DocumentChunk(
            document_id=document_a.id, workspace_id=workspace.id, chunk_index=0, content="A0"
        )
    )
    db_session.add(
        DocumentChunk(
            document_id=document_b.id, workspace_id=workspace.id, chunk_index=0, content="B0"
        )
    )
    db_session.flush()  # no IntegrityError — the constraint is scoped per document


def test_deleting_a_document_cascades_to_its_chunks(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    chunk = DocumentChunk(
        document_id=document.id, workspace_id=workspace.id, chunk_index=0, content="Bye."
    )
    db_session.add(chunk)
    db_session.flush()
    chunk_id = chunk.id

    db_session.delete(document)
    db_session.flush()
    # `ON DELETE CASCADE` runs in Postgres, not through the ORM — the
    # session's identity map still holds the pre-delete `chunk` object
    # unless told to forget it, so `.get()` would otherwise return the
    # stale cached instance instead of re-querying.
    db_session.expire_all()

    assert db_session.get(DocumentChunk, chunk_id) is None


def test_nullable_metadata_fields_default_to_none(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)

    fetched = db_session.get(Document, document.id)
    assert fetched is not None
    assert fetched.failure_reason is None
    assert fetched.page_count is None
    assert fetched.processing_started_at is None
    assert fetched.processing_completed_at is None

    chunk = DocumentChunk(
        document_id=document.id, workspace_id=workspace.id, chunk_index=0, content="Text."
    )
    db_session.add(chunk)
    db_session.flush()
    fetched_chunk = db_session.get(DocumentChunk, chunk.id)
    assert fetched_chunk is not None
    assert fetched_chunk.page is None
    assert fetched_chunk.section is None


def test_document_status_defaults_to_uploaded_and_persists(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)

    fetched = db_session.get(Document, document.id)
    assert fetched is not None
    assert fetched.status == DocumentStatus.UPLOADED

    fetched.status = DocumentStatus.FAILED
    fetched.failure_reason = "unsupported_mime_type"
    db_session.flush()
    db_session.expire(fetched)

    refetched = db_session.get(Document, document.id)
    assert refetched is not None
    assert refetched.status == DocumentStatus.FAILED
    assert refetched.failure_reason == "unsupported_mime_type"


def test_document_timestamps_are_set_by_the_database(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)

    fetched = db_session.get(Document, document.id)
    assert fetched is not None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_document_chunk_timestamp_is_set_by_the_database(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    chunk = DocumentChunk(
        document_id=document.id, workspace_id=workspace.id, chunk_index=0, content="Text."
    )
    db_session.add(chunk)
    db_session.flush()

    fetched = db_session.get(DocumentChunk, chunk.id)
    assert fetched is not None
    assert fetched.created_at is not None
