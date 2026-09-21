"""Document upload orchestration (Issue #3, Slice 3.3).

Ordering, deliberately: validate (extension/MIME, no body read needed) ->
stream-read the body (bounded, computing the checksum as it goes) ->
magic-byte consistency check -> workspace-scoped duplicate check ->
generate a storage key -> StorageProvider.save() -> DB insert -> audit
event -> commit. Storage always succeeds before anything is written to
Postgres — see `_persist_document()` for exactly how a failure after the
storage write is compensated for.

This is schema/upload only. No extraction, chunking, embedding, or state
transition beyond UPLOADED happens here or anywhere in this slice.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Final

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import AuditEvent
from app.core.audit import record as record_audit_event
from app.models.document import Document
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
    and remove the orphan later."""
    try:
        storage.delete(key=storage_key)
    except StorageError:
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


__all__ = ["upload_document"]
