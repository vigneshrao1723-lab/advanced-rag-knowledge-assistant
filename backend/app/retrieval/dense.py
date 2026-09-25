"""Dense (vector) retrieval over `document_chunks.embedding` (pgvector).

Uses `Vector.cosine_distance()` (the `<=>` operator), backed by the
`ix_document_chunks_embedding_hnsw` HNSW index (migration `0005`) — no
separate index-build step is needed here; the index is already
maintained transactionally as chunks are embedded (Issue #3, Slice 3.7).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.retrieval.types import RetrievalCandidate


def dense_search(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    document_id: uuid.UUID | None = None,
) -> list[RetrievalCandidate]:
    """Workspace-scoped at the SQL level (never filtered after the fact —
    see the package docstring). Only chunks belonging to a `READY`
    document, with a non-null embedding, are candidates: a document
    still mid-pipeline (e.g. `CHUNKED` but not yet `EMBEDDED`) never
    surfaces partial results.
    """
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.workspace_id,
            DocumentChunk.content,
            DocumentChunk.page,
            DocumentChunk.section,
            distance.label("distance"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.workspace_id == workspace_id,
            DocumentChunk.embedding.is_not(None),
            Document.status == DocumentStatus.READY,
        )
    )
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    stmt = stmt.order_by(distance).limit(top_k)

    rows = db.execute(stmt).all()
    return [
        RetrievalCandidate(
            chunk_id=row.id,
            document_id=row.document_id,
            workspace_id=row.workspace_id,
            content=row.content,
            page=row.page,
            section=row.section,
            # Cosine distance is in [0, 2] for pgvector; similarity =
            # 1 - distance keeps "higher is better" consistent with
            # every other stage in this package (see RetrievalCandidate's
            # own docstring).
            score=1.0 - row.distance,
        )
        for row in rows
    ]


__all__ = ["dense_search"]
