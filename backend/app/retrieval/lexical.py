"""Lexical (keyword) retrieval over `document_chunks.content` via
Postgres full-text search (`to_tsvector`/`plainto_tsquery`/`ts_rank_cd`) —
the BM25-shaped complement to dense retrieval (ADR 0002's own stated
consequence: a PostgreSQL-native approach, not a second search engine).

`plainto_tsquery` (not `to_tsquery`) is used deliberately: it takes a
plain user query string and never interprets `&`/`|`/`!`/`:*` operator
syntax a user might accidentally type, so a query like "cost & benefit"
searches for the literal words, never a malformed or unexpectedly
narrowed boolean expression.

The `to_tsvector('english', content)` expression here must match the
one `ix_document_chunks_content_fts` (migration `0007`) was built on
exactly, or Postgres falls back to a sequential scan instead of using
the index — both live only in this module.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.retrieval.types import RetrievalCandidate

_LANGUAGE = "english"


def lexical_search(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    top_k: int,
    document_id: uuid.UUID | None = None,
) -> list[RetrievalCandidate]:
    """Workspace-scoped at the SQL level; only `READY`-document chunks
    are candidates (see `dense_search()`'s docstring for why). A query
    that matches no chunk's tokens (or is empty/whitespace-only) simply
    returns an empty list -- `@@` against an empty `tsquery` matches
    nothing, never every row.
    """
    tsvector = func.to_tsvector(_LANGUAGE, DocumentChunk.content)
    tsquery = func.plainto_tsquery(_LANGUAGE, query_text)
    rank = func.ts_rank_cd(tsvector, tsquery).label("rank")

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.workspace_id,
            DocumentChunk.content,
            DocumentChunk.page,
            DocumentChunk.section,
            rank,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.workspace_id == workspace_id,
            tsvector.op("@@")(tsquery),
            Document.status == DocumentStatus.READY,
        )
    )
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    stmt = stmt.order_by(rank.desc()).limit(top_k)

    rows = db.execute(stmt).all()
    return [
        RetrievalCandidate(
            chunk_id=row.id,
            document_id=row.document_id,
            workspace_id=row.workspace_id,
            content=row.content,
            page=row.page,
            section=row.section,
            score=float(row.rank),
        )
        for row in rows
    ]


__all__ = ["lexical_search"]
