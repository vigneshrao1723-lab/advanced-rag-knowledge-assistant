from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.chunking import Chunk
from app.models.document_chunk import DocumentChunk


def bulk_create(
    db: Session,
    *,
    document_id: uuid.UUID,
    workspace_id: uuid.UUID,
    chunks: list[Chunk],
) -> list[DocumentChunk]:
    """Inserts every chunk in one batch. Follows the existing add/flush/
    no-commit convention (`document_repository.py`) -- the caller commits
    this together with the document's own `CHUNKED` status transition in
    one transaction, so a crash or a failed commit can never leave a
    `CHUNKED` document without its chunks (or vice versa): either both
    are durably persisted together, or neither is.

    `chunk_index` values come directly from `Chunk.chunk_index`
    (`chunking.py`'s own zero-based, gapless ordering) -- never
    regenerated here, so a race against a concurrent identical insert
    (two simultaneous `/process` calls chunking the same document) is
    caught by `document_chunks`' own `UNIQUE(document_id, chunk_index)`
    constraint, the same authoritative-backstop pattern already used for
    `documents`' own duplicate-checksum race (see
    `document_service._persist_document`).
    """
    rows = [
        DocumentChunk(
            document_id=document_id,
            workspace_id=workspace_id,
            chunk_index=chunk.chunk_index,
            page=chunk.page,
            section=chunk.section,
            content=chunk.content,
        )
        for chunk in chunks
    ]
    db.add_all(rows)
    db.flush()
    for row in rows:
        db.refresh(row)
    return rows


def get_by_document(db: Session, *, document_id: uuid.UUID) -> list[DocumentChunk]:
    """Ordered by `chunk_index` -- the caller-facing, deterministic
    ordering `chunking.py` itself guarantees, not insertion order."""
    return list(
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ).scalars()
    )
