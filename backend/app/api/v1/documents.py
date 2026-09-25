"""Document upload and processing endpoints (Issue #3, Slices 3.3–3.7).

Upload is schema-only through UPLOADED. Process drives a document through
the full pipeline (extraction -> cleaning -> chunking -> embedding ->
indexing) to READY or FAILED. See app/services/document_service.py for
both orchestration strategies.
"""

from __future__ import annotations

import uuid

import redis
from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.dependencies import WorkspaceContext, require_workspace_role
from app.core.rate_limit import (
    client_ip,
    enforce_document_process_rate_limit,
    enforce_document_upload_rate_limit,
)
from app.core.redis_client import get_redis_client
from app.ingestion.embedding import EmbeddingProvider, get_embedding_provider
from app.models.workspace_member import WorkspaceRole
from app.schemas.document import DocumentRead
from app.services import document_service
from app.services.storage_provider import StorageProvider, get_storage_provider

router = APIRouter(prefix="/workspaces", tags=["documents"])


@router.get(
    "/{workspace_id}/documents",
    response_model=list[DocumentRead],
)
async def list_documents(
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    return document_service.list_documents(db, workspace_id=ctx.workspace.id)


@router.get(
    "/{workspace_id}/documents/{document_id}",
    response_model=DocumentRead,
)
async def get_document(
    document_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> DocumentRead:
    return document_service.get_document(
        db, workspace_id=ctx.workspace.id, document_id=document_id
    )


@router.post(
    "/{workspace_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage_provider),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> DocumentRead:
    enforce_document_upload_rate_limit(request, user_id=ctx.user.id, redis_client=redis_client)

    settings = get_settings()
    return await document_service.upload_document(
        db,
        workspace_id=ctx.workspace.id,
        uploaded_by=ctx.user.id,
        upload=file,
        storage=storage,
        max_size_bytes=settings.max_upload_size_bytes,
        ip_address=client_ip(request),
    )


@router.post(
    "/{workspace_id}/documents/{document_id}/process",
    response_model=DocumentRead,
    status_code=status.HTTP_200_OK,
)
async def process_document(
    request: Request,
    document_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> DocumentRead:
    enforce_document_process_rate_limit(request, user_id=ctx.user.id, redis_client=redis_client)
    settings = get_settings()
    return await document_service.process_document(
        db,
        workspace_id=ctx.workspace.id,
        document_id=document_id,
        triggered_by=ctx.user.id,
        storage=storage,
        embedding_provider=embedding_provider,
        embedding_batch_size=settings.embedding_batch_size,
        ip_address=client_ip(request),
    )
