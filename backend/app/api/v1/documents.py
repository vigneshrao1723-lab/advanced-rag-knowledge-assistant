"""Document upload endpoint (Issue #3, Slice 3.3).

Schema-only through UPLOADED — no extraction, chunking, embedding, or any
later lifecycle state. See app/services/document_service.py for the
storage/database consistency strategy.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.dependencies import WorkspaceContext, require_workspace_role
from app.core.rate_limit import client_ip, enforce_document_upload_rate_limit
from app.core.redis_client import get_redis_client
from app.models.workspace_member import WorkspaceRole
from app.schemas.document import DocumentRead
from app.services import document_service
from app.services.storage_provider import StorageProvider, get_storage_provider

router = APIRouter(prefix="/workspaces", tags=["documents"])


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
