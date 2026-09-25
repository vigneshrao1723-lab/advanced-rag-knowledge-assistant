"""Conversation endpoints (Issue #4, Slice 4.3): create a conversation,
post a question and get a grounded answer with citations back, list a
conversation's messages. See app/services/conversation_service.py for
the retrieval -> generation -> citation orchestration.
"""

from __future__ import annotations

import uuid

import redis
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.dependencies import WorkspaceContext, require_workspace_role
from app.core.rate_limit import enforce_conversation_message_rate_limit
from app.core.redis_client import get_redis_client
from app.generation.llm_provider import LLMProvider, get_llm_provider
from app.ingestion.embedding import EmbeddingProvider, get_embedding_provider
from app.models.workspace_member import WorkspaceRole
from app.retrieval.reranker import Reranker, get_reranker
from app.schemas.conversation import ConversationRead, MessageCreate, MessageRead
from app.services import conversation_service

router = APIRouter(prefix="/workspaces", tags=["conversations"])


@router.get(
    "/{workspace_id}/conversations",
    response_model=list[ConversationRead],
)
async def list_conversations(
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> list[ConversationRead]:
    return conversation_service.list_conversations(db, workspace_id=ctx.workspace.id)


@router.post(
    "/{workspace_id}/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
) -> ConversationRead:
    return conversation_service.create_conversation(
        db, workspace_id=ctx.workspace.id, created_by=ctx.user.id
    )


@router.post(
    "/{workspace_id}/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    request: Request,
    conversation_id: uuid.UUID,
    body: MessageCreate,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    reranker: Reranker = Depends(get_reranker),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> MessageRead:
    enforce_conversation_message_rate_limit(
        request, user_id=ctx.user.id, redis_client=redis_client
    )
    return await conversation_service.post_message(
        db,
        workspace_id=ctx.workspace.id,
        conversation_id=conversation_id,
        content=body.content,
        embedding_provider=embedding_provider,
        reranker=reranker,
        llm_provider=llm_provider,
    )


@router.get(
    "/{workspace_id}/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
)
async def list_messages(
    conversation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> list[MessageRead]:
    return conversation_service.list_messages(
        db, workspace_id=ctx.workspace.id, conversation_id=conversation_id
    )
