"""`hybrid_search()` — the single entry point the rest of this package
composes into: embed the query -> dense + lexical retrieval -> RRF
fusion -> rerank -> (optionally) record a `RetrievalEvent`.

Query rewriting (docs/REQUIREMENTS.md "Query handling") is deliberately
NOT implemented here: a meaningful rewrite (e.g. resolving "it"/"that"
from a prior turn) needs conversation history, which doesn't exist until
a conversation-aware caller has it (Issue #4's generation/context-builder
work). `rewritten_query_text` is accepted as an optional, already-computed
value so a future caller can pass one through without this function
needing to know how it was produced -- `query_text` (the original) is
always what actually drives retrieval, never the rewrite, and both are
recorded distinctly on the `RetrievalEvent` row per that same requirement
("preserving the original user query for transparency/debugging").
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.orm import Session

from app.ingestion.embedding import EmbeddingProvider, embed_with_retry
from app.repositories import retrieval_event_repository
from app.retrieval.dense import dense_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.lexical import lexical_search
from app.retrieval.reranker import Reranker
from app.retrieval.types import RetrievalCandidate

_DEFAULT_DENSE_TOP_K = 20
_DEFAULT_LEXICAL_TOP_K = 20
_DEFAULT_FINAL_TOP_K = 10
# The reranker sees a wider pool than final_top_k -- fusion casts a net,
# reranking narrows it -- matching the standard hybrid-pipeline shape.
_RERANK_POOL_MULTIPLIER = 3


def hybrid_search(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    document_id: uuid.UUID | None = None,
    dense_top_k: int = _DEFAULT_DENSE_TOP_K,
    lexical_top_k: int = _DEFAULT_LEXICAL_TOP_K,
    final_top_k: int = _DEFAULT_FINAL_TOP_K,
    rewritten_query_text: str | None = None,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    record_event: bool = True,
) -> list[RetrievalCandidate]:
    """Workspace isolation is enforced inside `dense_search()`/
    `lexical_search()` themselves (a `WHERE workspace_id = ...` clause on
    every query, never a filter applied after the fact) -- this function
    adds no separate check, since there is nothing left to filter by the
    time results reach here.

    Does not commit -- the caller controls the transaction boundary, same
    as every other service/repository function in this codebase. If
    `record_event` is True (the default), the `RetrievalEvent` row is
    `db.add()`-ed and flushed (visible within the same transaction) but
    left for the caller to commit alongside whatever else that request
    is doing (e.g. persisting the generated message).
    """
    started = time.monotonic()

    search_text = rewritten_query_text or query_text
    [query_embedding] = embed_with_retry(embedding_provider, [search_text])

    dense_results = dense_search(
        db,
        workspace_id=workspace_id,
        query_embedding=query_embedding,
        top_k=dense_top_k,
        document_id=document_id,
    )
    lexical_results = lexical_search(
        db,
        workspace_id=workspace_id,
        query_text=search_text,
        top_k=lexical_top_k,
        document_id=document_id,
    )
    fused = reciprocal_rank_fusion([dense_results, lexical_results])
    pool = fused[: final_top_k * _RERANK_POOL_MULTIPLIER]
    reranked = reranker.rerank(query=search_text, candidates=pool)[:final_top_k]

    latency_ms = int((time.monotonic() - started) * 1000)

    if record_event:
        retrieval_event_repository.create(
            db,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            query_text=query_text,
            rewritten_query_text=rewritten_query_text,
            method="hybrid",
            results=[
                {
                    "chunk_id": str(candidate.chunk_id),
                    "document_id": str(candidate.document_id),
                    "score": candidate.score,
                    "rank": rank,
                }
                for rank, candidate in enumerate(reranked)
            ],
            latency_ms=latency_ms,
        )

    return reranked


__all__ = ["hybrid_search"]
