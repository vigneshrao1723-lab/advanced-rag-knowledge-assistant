"""Lexical (keyword) retrieval over `document_chunks.content` via
Postgres full-text search (`to_tsvector`/`plainto_tsquery`/`ts_rank_cd`) —
the BM25-shaped complement to dense retrieval (ADR 0002's own stated
consequence: a PostgreSQL-native approach, not a second search engine).

`plainto_tsquery` (not `to_tsquery`) is used deliberately: it takes a
plain user query string and never interprets `&`/`|`/`!`/`:*` operator
syntax a user might accidentally type, so a query like "cost & benefit"
searches for the literal words, never a malformed expression. Its `&`
joins are then rewritten to `|` (see `lexical_search`) so a passage need
only contain *some* of the question's words to be a candidate.

The `to_tsvector('english', content)` expression here must match the
one `ix_document_chunks_content_fts` (migration `0007`) was built on
exactly, or Postgres falls back to a sequential scan instead of using
the index — both live only in this module.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Text, cast, func, select
from sqlalchemy.dialects.postgresql import TSQUERY
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
    # `plainto_tsquery` ANDs every non-stop word, so one word of a natural
    # question that the passage lacks ("how MANY days...", "...RECEIVE") made
    # the whole query match nothing (measured: 0 results for 14 of 16
    # questions). OR the terms instead and let `ts_rank_cd` rank by how many
    # match. Stop-word removal and stemming still happen inside Postgres.
    tsquery = cast(
        func.replace(cast(func.plainto_tsquery(_LANGUAGE, query_text), Text), " & ", " | "),
        TSQUERY,
    )
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
    # Ties are common with OR matching; without a tie-break Postgres returns
    # tied rows in arbitrary order, so the same question could be answered
    # from differently-ordered evidence on two runs.
    stmt = stmt.order_by(rank.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
    stmt = stmt.limit(top_k)

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
