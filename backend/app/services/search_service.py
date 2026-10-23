"""Standalone search (GitHub Issue #41, feature-completion sprint
priority 2): a retrieval-only entry point, distinct from chat, per
docs/REQUIREMENTS.md "Search" -- "A separate search mode (distinct from
chat) showing snippets, evidence, ranking/scores, retrieval method used,
and source information." Deliberately does not call `app.generation` at
all -- this returns ranked evidence, never a generated answer.

Reuses `app.retrieval.service.hybrid_search()` exactly as the chat flow
does, just without a conversation/message to attach the resulting
`RetrievalEvent` to -- `conversation_id`/`message_id` are nullable on
that table specifically for this case (see
`app/models/retrieval_event.py`'s docstring).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.ingestion.embedding import EmbeddingProvider
from app.repositories import document_repository
from app.retrieval.reranker import Reranker
from app.retrieval.service import hybrid_search
from app.schemas.search import SearchResponse, SearchResultRead


def search(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
) -> SearchResponse:
    candidates = hybrid_search(
        db,
        workspace_id=workspace_id,
        query_text=query_text,
        embedding_provider=embedding_provider,
        reranker=reranker,
    )

    document_ids = list({candidate.document_id for candidate in candidates})
    documents = document_repository.list_by_ids_for_workspace(
        db, workspace_id=workspace_id, document_ids=document_ids
    )
    filename_by_document_id = {document.id: document.filename for document in documents}

    results = [
        SearchResultRead(
            rank=rank,
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            document_filename=filename_by_document_id.get(candidate.document_id, "Unknown"),
            page=candidate.page,
            section=candidate.section,
            content=candidate.content,
            score=candidate.score,
        )
        for rank, candidate in enumerate(candidates)
    ]

    db.commit()
    return SearchResponse(query=query_text, method="hybrid", results=results)


__all__ = ["search"]
