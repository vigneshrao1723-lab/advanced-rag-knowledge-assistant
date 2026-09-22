"""Document upload and processing orchestration (Issue #3, Slices 3.3/3.4).

**Upload** (Slice 3.3) ordering: validate (extension/MIME, no body read
needed) -> stream-read the body (bounded, computing the checksum as it
goes) -> magic-byte consistency check -> workspace-scoped duplicate check
-> generate a storage key -> StorageProvider.save() -> DB insert -> audit
event -> commit. Storage always succeeds before anything is written to
Postgres — see `_persist_document()` for exactly how a failure after the
storage write is compensated for.

**Processing / text extraction** (Slice 3.4): `process_document()` moves
a document from UPLOADED/PROCESSING/FAILED to PARSED or FAILED, via
`app.ingestion.extraction`. The PROCESSING transition is committed as its
own transaction *before* extraction is attempted — see that function's
docstring for why. Extraction always reads through the existing
StorageProvider (never a raw filesystem path) and operates on the
server-generated storage key, never the client-supplied filename beyond
recovering its (already-validated-at-upload) extension.

No chunking, embedding, or state transition beyond PARSED/FAILED happens
here or anywhere in this slice.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from pathlib import PurePosixPath
from typing import Final

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import AuditEvent
from app.core.audit import record as record_audit_event
from app.ingestion import extraction
from app.ingestion.extraction import ExtractionError
from app.models.document import Document, DocumentStatus
from app.repositories import document_repository
from app.schemas.document import DocumentRead
from app.services.storage_provider import StorageError, StorageProvider

logger = logging.getLogger("app.documents")

_CHUNK_SIZE = 1024 * 1024  # 1 MiB — bounded read granularity.
_SIGNATURE_PEEK_BYTES = 16

# Extension -> acceptable client-supplied MIME values. Deliberately a small,
# named allowlist of real-world browser/client variants, not a wildcard —
# per docs/REQUIREMENTS.md's exact five supported formats. Extension and
# MIME are both client-controlled/spoofable on their own; this mapping is
# one of three independent, weak signals (see the magic-byte check below),
# never treated as proof the file is well-formed.
_ALLOWED_MIME_TYPES: Final[dict[str, frozenset[str]]] = {
    ".pdf": frozenset({"application/pdf"}),
    ".docx": frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ),
    ".txt": frozenset({"text/plain"}),
    # Browsers commonly send .md as text/plain (no dedicated Markdown MIME
    # type is universally implemented); text/x-markdown is a known older
    # variant. Named exceptions only, not arbitrary MIME acceptance.
    ".md": frozenset({"text/markdown", "text/x-markdown", "text/plain"}),
    # Spreadsheet-exported CSV commonly arrives as application/vnd.ms-excel;
    # some browsers send text/plain for CSV too.
    ".csv": frozenset({"text/csv", "application/vnd.ms-excel", "text/plain"}),
}

# Extension -> expected leading bytes, where a real, stable signature
# exists. `None` means "no reliable magic number for this format" (plain
# text formats aren't required to start with anything in particular) --
# the check is skipped for those extensions rather than faked. This is a
# lightweight consistency check only, not a parser: it does not prove the
# file is well-formed, uncorrupted, or safe to parse -- only that its
# first bytes are consistent with the claimed type. DOCX's signature is
# the generic ZIP local-file-header magic number (DOCX is a ZIP
# container), so it also matches any other ZIP-based file; that's an
# accepted limitation of a byte-level heuristic, not a gap this slice
# tries to close (real DOCX validity is Slice 3.4's job).
_SIGNATURES: Final[dict[str, bytes | None]] = {
    ".pdf": b"%PDF-",
    ".docx": b"PK\x03\x04",
    ".txt": None,
    ".md": None,
    ".csv": None,
}


def _normalize_extension(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    # Only the extension is ever derived from the client-supplied filename
    # -- never a path, never used to build a storage location. rsplit
    # avoids any directory-separator interpretation entirely (this is a
    # pure string suffix, not a filesystem path operation).
    _, _, suffix = filename.rpartition(".")
    if not suffix:
        return None
    return f".{suffix.lower()}"


def _is_allowed_extension(extension: str) -> bool:
    return extension in _ALLOWED_MIME_TYPES


def _is_allowed_mime(extension: str, mime_type: str | None) -> bool:
    allowed = _ALLOWED_MIME_TYPES.get(extension)
    if allowed is None:
        return False
    return mime_type in allowed


def _matches_signature(extension: str, header: bytes) -> bool:
    expected = _SIGNATURES.get(extension)
    if expected is None:
        return True  # No reliable signature for this format -- not checked.
    return header.startswith(expected)


def _unsupported_file_type_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "unsupported_file_type",
            "message": "This file type is not supported.",
        },
    )


async def _read_and_validate_size(file: UploadFile, *, max_size_bytes: int) -> tuple[bytes, str]:
    """Streams the upload in bounded chunks, computing the SHA-256 digest
    as it goes. Aborts as soon as the running total exceeds
    `max_size_bytes` -- never buffers an arbitrarily large payload first
    and checks its length afterward."""
    hasher = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "file_too_large",
                    "message": "The uploaded file exceeds the maximum allowed size.",
                },
            )
        hasher.update(chunk)
        chunks.append(chunk)
    return b"".join(chunks), hasher.hexdigest()


def _generate_storage_key(
    *, workspace_id: uuid.UUID, document_id: uuid.UUID, extension: str
) -> str:
    """Built only from trusted, server-generated identifiers -- the
    validated (allowlisted, normalized) extension and two UUIDs. The
    client-supplied filename never contributes to this key, so a
    malicious filename (e.g. `../../etc/passwd.pdf`) has nothing to
    influence here; StorageProvider's own traversal guard (Slice 3.2) is
    defense-in-depth on top of this, not the only thing stopping it."""
    return f"{workspace_id}/{document_id}{extension}"


def _cleanup_orphaned_storage_object(storage: StorageProvider, *, storage_key: str) -> None:
    """Best-effort compensating delete after a storage write succeeded but
    the database insert did not commit. Never raises -- a cleanup failure
    must not mask the original error being propagated to the caller; it's
    logged (identifiers only, no filesystem path) so an operator can find
    and remove the orphan later.

    Catches `Exception`, not just `StorageError`: `StorageProvider` is a
    `Protocol`, not an enforced base class, so nothing guarantees a given
    implementation's `delete()` only ever raises `StorageError` (today's
    `LocalStorage` does, by its own Slice 3.2 contract, but this function
    must not depend on every future implementation honoring that). A
    narrower catch here would let a cleanup-time failure of any other
    type propagate and silently replace the real error this whole
    function exists to avoid masking.
    """
    try:
        storage.delete(key=storage_key)
    except Exception:
        logger.warning(
            "document_upload_storage_cleanup_failed",
            extra={"storage_key": storage_key},
        )


def _to_document_read(document: Document) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        filename=document.filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        checksum_sha256=document.checksum_sha256,
        status=document.status,
        page_count=document.page_count,
        failure_reason=document.failure_reason,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _duplicate_document_error(existing: Document) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "duplicate_document",
            "message": f"A document with this content already exists (id: {existing.id}).",
        },
    )


def _persist_document(
    db: Session,
    *,
    document_id: uuid.UUID,
    storage: StorageProvider,
    storage_key: str,
    workspace_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    filename: str,
    mime_type: str,
    size_bytes: int,
    checksum_sha256: str,
    ip_address: str | None,
) -> Document:
    """Runs after `storage.save()` has already succeeded. Any failure here
    (a race-lost unique-constraint insert, or any other DB error) rolls
    back the aborted transaction and attempts to remove the just-written
    storage object -- the document row must never end up committed if the
    storage write didn't durably succeed first, and the storage object
    must never be left silently unreferenced without at least an attempt
    to clean it up and a log line if that attempt itself fails.
    """
    try:
        document = document_repository.create(
            db,
            id=document_id,
            workspace_id=workspace_id,
            uploaded_by=uploaded_by,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            storage_key=storage_key,
        )
        record_audit_event(
            db,
            event_type=AuditEvent.DOCUMENT_UPLOADED,
            user_id=uploaded_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
            metadata={
                "document_id": str(document.id),
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "checksum_sha256": checksum_sha256,
            },
        )
    except IntegrityError:
        db.rollback()
        _cleanup_orphaned_storage_object(storage, storage_key=storage_key)
        # A concurrent request for the same (workspace_id, checksum_sha256)
        # won the race between our own pre-check and this insert -- the
        # unique constraint is the authoritative backstop for exactly this
        # window. Translate to the same documented 409, never a 500.
        existing = document_repository.get_by_workspace_and_checksum(
            db, workspace_id=workspace_id, checksum_sha256=checksum_sha256
        )
        if existing is not None:
            raise _duplicate_document_error(existing) from None
        raise  # Some other integrity error -- let it surface as a 500, not masked.
    except Exception:
        db.rollback()
        _cleanup_orphaned_storage_object(storage, storage_key=storage_key)
        raise

    return document


async def upload_document(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    upload: UploadFile,
    storage: StorageProvider,
    max_size_bytes: int,
    ip_address: str | None = None,
) -> DocumentRead:
    extension = _normalize_extension(upload.filename)
    if extension is None or not _is_allowed_extension(extension):
        raise _unsupported_file_type_error()
    if not _is_allowed_mime(extension, upload.content_type):
        raise _unsupported_file_type_error()

    content, checksum = await _read_and_validate_size(upload, max_size_bytes=max_size_bytes)

    if not _matches_signature(extension, content[:_SIGNATURE_PEEK_BYTES]):
        raise _unsupported_file_type_error()

    existing = document_repository.get_by_workspace_and_checksum(
        db, workspace_id=workspace_id, checksum_sha256=checksum
    )
    if existing is not None:
        raise _duplicate_document_error(existing)

    document_id = uuid.uuid4()
    storage_key = _generate_storage_key(
        workspace_id=workspace_id, document_id=document_id, extension=extension
    )
    storage.save(key=storage_key, content=content)

    document = _persist_document(
        db,
        document_id=document_id,
        storage=storage,
        storage_key=storage_key,
        workspace_id=workspace_id,
        uploaded_by=uploaded_by,
        filename=upload.filename or "untitled",
        mime_type=upload.content_type or "application/octet-stream",
        size_bytes=len(content),
        checksum_sha256=checksum,
        ip_address=ip_address,
    )
    return _to_document_read(document)


# A document can be (re)processed from UPLOADED (first attempt), PROCESSING
# (a prior attempt was interrupted -- e.g. a crash or restart mid-extraction
# -- and never reached PARSED/FAILED, so it's treated as retriable rather
# than stuck forever), or FAILED (explicit retry after a fixable failure).
# PARSED and every later lifecycle state (CLEANED/CHUNKED/EMBEDDED/INDEXED/
# READY) are refused with 409 -- extraction has already happened or the
# document has moved past it.
_REPROCESSABLE_STATUSES: Final = frozenset(
    {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING, DocumentStatus.FAILED}
)


def _document_not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "document_not_found", "message": "Document not found."},
    )


def _document_already_processed_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "document_already_processed",
            "message": "This document has already been processed.",
        },
    )


def _extension_from_storage_key(storage_key: str) -> str:
    """The storage key is server-generated (`_generate_storage_key()`
    above) as `f"{workspace_id}/{document_id}{extension}"`, where
    `extension` is itself drawn from the same validated allowlist
    upload-time extraction dispatch uses -- never the client-supplied
    filename. `PurePosixPath` is used only for its `.suffix` parsing (no
    filesystem access), matching the key's always-forward-slash shape."""
    return PurePosixPath(storage_key).suffix.lower()


def _read_and_extract(
    *, storage: StorageProvider, storage_key: str, extension: str
) -> extraction.ExtractedDocument:
    """Synchronous, potentially CPU- and I/O-bound: the storage read and
    the parser call. Deliberately a single plain function (not a
    coroutine) so it can be run via `asyncio.to_thread()` in
    `process_document()` below -- this project runs one uvicorn process
    with no `--workers` (see `infra/docker/backend.Dockerfile`'s
    entrypoint), so calling this directly inside an `async def` would
    block that single event loop, and with it every other concurrent
    request this process is serving, for the full duration of parsing a
    single document. Confirmed empirically, not just reasoned about: a
    synchronous call here measurably stalled an unrelated concurrent
    request until the slow call finished."""
    content = storage.read(key=storage_key)
    return extraction.extract(extension=extension, content=content)


async def process_document(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    triggered_by: uuid.UUID,
    storage: StorageProvider,
    ip_address: str | None = None,
) -> DocumentRead:
    """Synchronous text extraction, run within the request -- not a
    background job: per this slice's own scope, the minimum execution
    mechanism needed is "call the extractor while handling the request",
    not a new queue/worker infrastructure. The extraction itself (storage
    read + parsing) runs via `asyncio.to_thread()` in a worker thread, not
    directly on the event loop -- see `_read_and_extract()`'s docstring
    for why that distinction matters even without a background job.

    The PROCESSING transition is committed on its own, *before*
    extraction is attempted -- so if this process crashes or is killed
    mid-extraction (a large PDF, a slow parse), the document is left
    honestly at PROCESSING, which `_REPROCESSABLE_STATUSES` above treats
    as retriable, rather than silently vanishing mid-request while still
    claiming (via a stale UPLOADED row) that processing never started.

    A parsing failure is an expected, handled outcome, not a server
    error: it is recorded as FAILED with a generic reason, audited, and
    returned as an ordinary 200 response -- never raised as an
    HTTPException and never left silently unrecorded.
    """
    document = document_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, document_id=document_id
    )
    if document is None:
        raise _document_not_found_error()
    if document.status not in _REPROCESSABLE_STATUSES:
        raise _document_already_processed_error()

    document = document_repository.mark_processing(db, document=document)
    db.commit()

    extracted: extraction.ExtractedDocument | None = None
    reason: str | None = None
    try:
        extension = _extension_from_storage_key(document.storage_key)
        extracted = await asyncio.to_thread(
            _read_and_extract,
            storage=storage,
            storage_key=document.storage_key,
            extension=extension,
        )
    except StorageError:
        # Never include the StorageError's own message here -- it embeds
        # the storage key (see storage_provider.py), which must never
        # reach an API response (docs/SECURITY.md "Upload & document
        # safety").
        reason = "The document's stored file could not be read."
    except ExtractionError as exc:
        # extraction.py's own messages are already short, generic, and
        # storage-safe by construction -- see that module's docstring.
        reason = str(exc)
    except Exception:  # noqa: BLE001 - any other parser failure must not crash the request
        logger.exception(
            "document_processing_unexpected_failure",
            extra={"document_id": str(document.id)},
        )
        reason = "Processing failed due to an unexpected error."

    if extracted is None:
        assert reason is not None
        document = document_repository.mark_failed(db, document=document, reason=reason)
        record_audit_event(
            db,
            event_type=AuditEvent.DOCUMENT_PARSING_FAILED,
            user_id=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
            metadata={"document_id": str(document.id), "reason": reason},
        )
        db.commit()
        return _to_document_read(document)

    document = document_repository.mark_parsed(
        db, document=document, page_count=extracted.page_count
    )
    record_audit_event(
        db,
        event_type=AuditEvent.DOCUMENT_PARSED,
        user_id=triggered_by,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={
            "document_id": str(document.id),
            "page_count": extracted.page_count,
            "section_count": len(extracted.sections),
        },
    )
    db.commit()
    return _to_document_read(document)


__all__ = ["process_document", "upload_document"]
