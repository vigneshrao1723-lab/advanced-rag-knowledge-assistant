"""Document upload and processing orchestration (Issue #3, Slices 3.3–3.7).

**Upload** (Slice 3.3) ordering: validate (extension/MIME, no body read
needed) -> stream-read the body (bounded, computing the checksum as it
goes) -> magic-byte consistency check -> workspace-scoped duplicate check
-> generate a storage key -> StorageProvider.save() -> DB insert -> audit
event -> commit. Storage always succeeds before anything is written to
Postgres — see `_persist_document()` for exactly how a failure after the
storage write is compensated for.

**Processing** (Slices 3.4–3.7): `process_document()` drives a document
through the full synchronous pipeline -- extraction (Slice 3.4) ->
cleaning (Slice 3.6, `app.ingestion.cleaning`) -> chunking (Slice 3.6,
`app.ingestion.chunking`) -> embedding + indexing (Slice 3.7,
`app.ingestion.embedding`) -- committing a durable checkpoint after each
stage *before* the next stage's work begins, so a crash at any point
leaves the document honestly at its last completed stage, never falsely
further along. See that function's own docstring for the exact ordering.

There is deliberately no persistence of extracted/cleaned *text* between
stages -- resuming a document from `PARSED`/`CLEANED` re-runs
extraction/cleaning from scratch (idempotent, deterministic) rather than
attempting to skip them, since nothing but the status itself is durable
between requests. `document_chunks` rows themselves, once persisted at
`CHUNKED`, are real durable state, though -- resuming from
`CHUNKED`/`EMBEDDED`/`INDEXED` does *not* re-run extraction/cleaning/
chunking; it fetches the already-persisted chunks and continues straight
into embedding (idempotent overwrite of any existing vectors, since the
embedding provider is a pure function of chunk content).

Extraction/cleaning/chunking all read/operate only through the existing
StorageProvider and the server-generated storage key, never a raw
filesystem path and never the client-supplied filename beyond recovering
its (already-validated-at-upload) extension. Embedding never leaves this
process either -- `LocalHashingEmbeddingProvider` (Slice 3.7) is
deterministic and offline, no external network call, no API key.
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
from app.ingestion import chunking, extraction
from app.ingestion.chunking import Chunk, ChunkingError
from app.ingestion.cleaning import clean as clean_extracted_document
from app.ingestion.embedding import EmbeddingError, EmbeddingProvider, embed_with_retry
from app.ingestion.extraction import ExtractedDocument, ExtractionError
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.repositories import document_chunk_repository, document_repository
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


def list_documents(db: Session, *, workspace_id: uuid.UUID) -> list[DocumentRead]:
    documents = document_repository.list_for_workspace(db, workspace_id=workspace_id)
    return [_to_document_read(document) for document in documents]


def get_document(db: Session, *, workspace_id: uuid.UUID, document_id: uuid.UUID) -> DocumentRead:
    document = document_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, document_id=document_id
    )
    if document is None:
        raise _document_not_found_error()
    return _to_document_read(document)


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


# A document can be (re)processed from UPLOADED (first attempt),
# PROCESSING/PARSED/CLEANED/CHUNKED/EMBEDDED/INDEXED (a prior attempt was
# interrupted -- e.g. a crash or restart -- partway through the pipeline
# and never reached READY/FAILED, so it's treated as retriable rather
# than stuck forever), or FAILED (explicit retry after a fixable
# failure). Only READY is refused with 409 -- the full pipeline is
# terminal there.
#
# Resuming from PARSED or CLEANED does not skip the stages already
# passed: nothing but the document's own `status` is durable between
# requests for *extracted/cleaned text* (deliberately -- see the module
# docstring), so process_document() below always restarts from
# extraction regardless of which of these statuses it found. This is
# safe because extraction/cleaning/chunking are all pure, deterministic
# functions of the same stored bytes -- re-running an already-passed
# stage produces the identical result, at the cost of some redundant CPU
# work on a retry, never incorrect output.
#
# Resuming from CHUNKED/EMBEDDED/INDEXED is different: `document_chunks`
# rows ARE real durable state once persisted, so process_document() skips
# extraction/cleaning/chunking entirely for these three statuses and
# fetches the already-persisted chunks, continuing straight into
# embedding. This is also safe to always redo from scratch (never
# partial-completion-aware) because the embedding provider is a pure,
# deterministic function of chunk content -- re-embedding an
# already-embedded document just overwrites each vector with the
# identical value, never incorrect or inconsistent output.
_REPROCESSABLE_STATUSES: Final = frozenset(
    {
        DocumentStatus.UPLOADED,
        DocumentStatus.PROCESSING,
        DocumentStatus.PARSED,
        DocumentStatus.CLEANED,
        DocumentStatus.CHUNKED,
        DocumentStatus.EMBEDDED,
        DocumentStatus.INDEXED,
        DocumentStatus.FAILED,
    }
)

# Statuses for which document_chunks rows already exist -- process_document()
# skips extraction/cleaning/chunking for these and jumps straight to the
# embedding phase using the already-persisted chunks.
_ALREADY_CHUNKED_STATUSES: Final = frozenset(
    {
        DocumentStatus.CHUNKED,
        DocumentStatus.EMBEDDED,
        DocumentStatus.INDEXED,
    }
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


def _embed_chunks(
    provider: EmbeddingProvider, chunks: list[DocumentChunk], *, batch_size: int
) -> list[list[float]]:
    """Synchronous, CPU-bound (and, for a future networked provider,
    I/O-bound too) -- deliberately a single plain function, matching
    `_read_and_extract()`'s own shape, so it can be run via
    `asyncio.to_thread()` in `process_document()` below. Batches chunk
    content into groups of at most `batch_size` texts per
    `embed_with_retry()` call -- bounds a single provider call's size,
    which matters for a future networked provider with its own
    request-size limits even though `LocalHashingEmbeddingProvider` has
    none; this way the batching behavior is already exercised and correct
    once a real provider is plugged in, not left untested until then.
    Returns one embedding per input chunk, same order.
    """
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings.extend(embed_with_retry(provider, [chunk.content for chunk in batch]))
    return embeddings


def _mark_failed_and_audit(
    db: Session,
    *,
    document: Document,
    reason: str,
    event_type: str,
    triggered_by: uuid.UUID,
    workspace_id: uuid.UUID,
    ip_address: str | None,
) -> Document:
    document = document_repository.mark_failed(db, document=document, reason=reason)
    record_audit_event(
        db,
        event_type=event_type,
        user_id=triggered_by,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={"document_id": str(document.id), "reason": reason},
    )
    db.commit()
    return document


async def process_document(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    triggered_by: uuid.UUID,
    storage: StorageProvider,
    embedding_provider: EmbeddingProvider,
    embedding_batch_size: int = 64,
    ip_address: str | None = None,
) -> DocumentRead:
    """Drives a document through the full synchronous pipeline -- run
    within the request, not a background job: per this slice's own
    scope, the minimum execution mechanism needed is "call each stage
    while handling the request", not a new queue/worker infrastructure.
    Every CPU-bound stage (extraction, cleaning, chunking, embedding)
    runs via `asyncio.to_thread()` in a worker thread, never directly on
    the event loop -- see `_read_and_extract()`'s docstring for why that
    distinction matters even without a background job; the same
    reasoning applies identically to cleaning, chunking, and embedding.

    Each stage's success is committed as its own transaction, *before*
    the next stage's work begins -- PROCESSING before extraction, PARSED
    before cleaning, CLEANED before chunking, CHUNKED together with its
    `document_chunks` rows in one atomic commit, EMBEDDED together with
    every chunk's embedding vector in one atomic commit, then INDEXED,
    then READY. A crash or kill at any point leaves the document honestly
    at its last completed stage (which `_REPROCESSABLE_STATUSES` above
    treats as retriable) rather than silently vanishing mid-request while
    claiming a stage it never reached.

    A document already at CHUNKED, EMBEDDED, or INDEXED skips extraction/
    cleaning/chunking entirely (its `document_chunks` rows already exist
    -- see `_ALREADY_CHUNKED_STATUSES` above) and goes straight to the
    embedding phase using those already-persisted rows.

    A failure at any stage is an expected, handled outcome, not a server
    error: it is recorded as FAILED with a short, generic, storage-safe
    reason, audited with a stage-specific event type, and returned as an
    ordinary 200 response -- never raised as an HTTPException and never
    left silently unrecorded. There is no separate `DOCUMENT_CLEANED` or
    `DOCUMENT_INDEXED` success audit event: cleaning and indexing are
    both internal checkpoints with nothing distinct to report on their
    own (indexing in particular does no separate work -- see
    `document_repository.mark_indexed()`) -- auditing them separately
    would only add noise, not information; a *failure* during embedding
    is still audited explicitly below, and the pipeline's overall success
    is audited once, at `DOCUMENT_READY`.
    """
    document = document_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, document_id=document_id
    )
    if document is None:
        raise _document_not_found_error()
    if document.status not in _REPROCESSABLE_STATUSES:
        raise _document_already_processed_error()

    already_chunked = document.status in _ALREADY_CHUNKED_STATUSES

    document = document_repository.mark_processing(db, document=document)
    db.commit()

    if already_chunked:
        persisted_chunks = document_chunk_repository.get_by_document(
            db, document_id=document.id
        )
    else:
        persisted_chunks, failed_read = await _extract_clean_and_chunk(
            db,
            document=document,
            storage=storage,
            triggered_by=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
        )
        if failed_read is not None:
            return failed_read
        document = document_repository.get_by_id_for_workspace(
            db, workspace_id=workspace_id, document_id=document.id
        )
        assert document is not None

    if not persisted_chunks:
        # A real, reachable outcome, not a bug: chunking.py's own
        # `_chunk_section()` returns no chunks for an empty/whitespace-
        # only section, so a document with no extractable text (an empty
        # file, or e.g. a scanned, text-layer-less PDF) legitimately
        # chunks to zero rows -- chunking itself did not fail. Such a
        # document has nothing to embed and can never be meaningfully
        # retrieved, so it is reported as a clear, honest failure here
        # rather than silently marked READY with zero chunks (which
        # would look successful while being permanently unretrievable).
        document = _mark_failed_and_audit(
            db,
            document=document,
            reason="The document contains no extractable text content to process.",
            event_type=AuditEvent.DOCUMENT_EMBEDDING_FAILED,
            triggered_by=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
        )
        return _to_document_read(document)

    embeddings: list[list[float]] | None = None
    reason: str | None = None
    try:
        embeddings = await asyncio.to_thread(
            _embed_chunks,
            embedding_provider,
            persisted_chunks,
            batch_size=embedding_batch_size,
        )
    except EmbeddingError as exc:
        # embedding.py's own messages are already short and generic by
        # construction -- see that module's docstring.
        reason = str(exc)
    except Exception:  # noqa: BLE001 - any other provider failure must not crash the request
        logger.exception(
            "document_processing_unexpected_failure",
            extra={"document_id": str(document.id), "stage": "embedding"},
        )
        reason = "Processing failed due to an unexpected error."

    if embeddings is None:
        assert reason is not None
        document = _mark_failed_and_audit(
            db,
            document=document,
            reason=reason,
            event_type=AuditEvent.DOCUMENT_EMBEDDING_FAILED,
            triggered_by=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
        )
        return _to_document_read(document)

    document_chunk_repository.set_embeddings(
        db,
        chunks=persisted_chunks,
        embeddings=embeddings,
        model=embedding_provider.model_name,
        dimension=embedding_provider.dimension,
    )
    document = document_repository.mark_embedded(db, document=document)
    db.commit()

    document = document_repository.mark_indexed(db, document=document)
    db.commit()

    document = document_repository.mark_ready(db, document=document)
    record_audit_event(
        db,
        event_type=AuditEvent.DOCUMENT_READY,
        user_id=triggered_by,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={
            "document_id": str(document.id),
            "chunk_count": len(persisted_chunks),
            "embedding_model": embedding_provider.model_name,
            "embedding_dimension": embedding_provider.dimension,
        },
    )
    db.commit()

    return _to_document_read(document)


async def _extract_clean_and_chunk(
    db: Session,
    *,
    document: Document,
    storage: StorageProvider,
    triggered_by: uuid.UUID,
    workspace_id: uuid.UUID,
    ip_address: str | None,
) -> tuple[list[DocumentChunk], DocumentRead | None]:
    """The extraction -> cleaning -> chunking portion of the pipeline,
    factored out of `process_document()` so that function's own control
    flow (branch on already-chunked, then converge on the shared
    embedding phase) stays readable. Returns `(chunks, None)` on success,
    or `([], failure_response)` when a stage failed -- the caller returns
    `failure_response` immediately in that case, matching every other
    stage's "return a 200 with FAILED status" contract.
    """
    extracted: ExtractedDocument | None = None
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
            extra={"document_id": str(document.id), "stage": "extraction"},
        )
        reason = "Processing failed due to an unexpected error."

    if extracted is None:
        assert reason is not None
        document = _mark_failed_and_audit(
            db,
            document=document,
            reason=reason,
            event_type=AuditEvent.DOCUMENT_PARSING_FAILED,
            triggered_by=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
        )
        return [], _to_document_read(document)

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

    cleaned: ExtractedDocument | None = None
    try:
        cleaned = await asyncio.to_thread(clean_extracted_document, extracted)
    except Exception:  # noqa: BLE001 - cleaning is total by design; still never crash the request
        logger.exception(
            "document_processing_unexpected_failure",
            extra={"document_id": str(document.id), "stage": "cleaning"},
        )
        document = _mark_failed_and_audit(
            db,
            document=document,
            reason="Processing failed due to an unexpected error.",
            event_type=AuditEvent.DOCUMENT_CLEANING_FAILED,
            triggered_by=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
        )
        return [], _to_document_read(document)

    document = document_repository.mark_cleaned(db, document=document)
    db.commit()

    chunks: list[Chunk] | None = None
    try:
        chunks = await asyncio.to_thread(chunking.StructureAwareChunker().chunk, cleaned)
    except ChunkingError as exc:
        # chunking.py's own messages are already short and generic by
        # construction -- see that module's docstring.
        reason = str(exc)
    except Exception:  # noqa: BLE001 - any other chunker failure must not crash the request
        logger.exception(
            "document_processing_unexpected_failure",
            extra={"document_id": str(document.id), "stage": "chunking"},
        )
        reason = "Processing failed due to an unexpected error."

    if chunks is None:
        assert reason is not None
        document = _mark_failed_and_audit(
            db,
            document=document,
            reason=reason,
            event_type=AuditEvent.DOCUMENT_CHUNKING_FAILED,
            triggered_by=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
        )
        return [], _to_document_read(document)

    try:
        document_chunk_repository.bulk_create(
            db, document_id=document.id, workspace_id=workspace_id, chunks=chunks
        )
        document = document_repository.mark_chunked(db, document=document)
        record_audit_event(
            db,
            event_type=AuditEvent.DOCUMENT_CHUNKED,
            user_id=triggered_by,
            workspace_id=workspace_id,
            ip_address=ip_address,
            metadata={"document_id": str(document.id), "chunk_count": len(chunks)},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent request for the same document won the race to
        # persist chunks first -- document_chunks' own
        # UNIQUE(document_id, chunk_index) constraint is the
        # authoritative backstop for exactly this window, the same
        # pattern already used for documents' own duplicate-checksum
        # race (see _persist_document above). Both requests compute the
        # identical, deterministic chunk set from the same stored bytes,
        # so returning the winner's now-committed state is correct, not
        # a stale/wrong result -- never a raised error for this case.

    # Always re-fetch the authoritative, now-committed rows from the
    # database rather than trusting the local `chunks` (dataclass) list or
    # this request's own `bulk_create()` return value -- in the
    # IntegrityError-recovery path above, those reflect this request's
    # own (uncommitted, rolled-back) attempt, not the concurrent winner's
    # actually-persisted rows.
    persisted_chunks = document_chunk_repository.get_by_document(db, document_id=document.id)
    return persisted_chunks, None


__all__ = ["get_document", "list_documents", "process_document", "upload_document"]
