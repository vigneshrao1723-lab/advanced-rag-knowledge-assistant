from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.evaluation_run import EvaluationRun


def create(
    db: Session,
    *,
    workspace_id: uuid.UUID | None,
    embedding_model: str,
    chunking_strategy: str,
    retrieval_method: str,
    top_k: int,
    llm_provider: str,
    document_count: int,
    query_count: int,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    reranker: str | None = None,
) -> EvaluationRun:
    """Follows the existing add/flush/no-commit convention -- the caller
    controls the transaction boundary, same as every other repository in
    this codebase."""
    run = EvaluationRun(
        workspace_id=workspace_id,
        embedding_model=embedding_model,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        retrieval_method=retrieval_method,
        top_k=top_k,
        reranker=reranker,
        llm_provider=llm_provider,
        document_count=document_count,
        query_count=query_count,
    )
    db.add(run)
    db.flush()
    db.refresh(run)
    return run


__all__ = ["create"]
