"""Standalone search endpoint (GitHub Issue #41): retrieval-only, no
generation -- see app/services/search_service.py for why, and
docs/REQUIREMENTS.md "Search."
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.dependencies import WorkspaceContext, require_workspace_role
from app.core.rate_limit import enforce_search_rate_limit
from app.core.redis_client import get_redis_client
from app.ingestion.embedding import EmbeddingProvider, get_embedding_provider
from app.models.workspace_member import WorkspaceRole
from app.retrieval.reranker import Reranker, get_reranker
from app.schemas.search import SearchResponse
from app.services import search_service

router = APIRouter(prefix="/workspaces", tags=["search"])


@router.get(
    "/{workspace_id}/search",
    response_model=SearchResponse,
)
async def search(
    request: Request,
    q: str = Query(min_length=1, max_length=4000),
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    reranker: Reranker = Depends(get_reranker),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> SearchResponse:
    enforce_search_rate_limit(request, user_id=ctx.user.id, redis_client=redis_client)
    return search_service.search(
        db,
        workspace_id=ctx.workspace.id,
        query_text=q,
        embedding_provider=embedding_provider,
        reranker=reranker,
    )
