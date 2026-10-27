"""Document upload and processing endpoints (Issue #3, Slices 3.3–3.7).

Upload is schema-only through UPLOADED. Process drives a document through
the full pipeline (extraction -> cleaning -> chunking -> embedding ->
indexing) to READY or FAILED. See app/services/document_service.py for
both orchestration strategies.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import quote

import redis
from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
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
from app.models.document import DocumentStatus
from app.models.workspace_member import WorkspaceRole
from app.schemas.document import DocumentChunkRead, DocumentRead, DocumentRename
from app.services import document_service
from app.services.storage_provider import StorageProvider, get_storage_provider

router = APIRouter(prefix="/workspaces", tags=["documents"])


@router.get(
    "/{workspace_id}/documents",
    response_model=list[DocumentRead],
)
async def list_documents(
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=255),
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    return document_service.list_documents(
        db, workspace_id=ctx.workspace.id, status_filter=status_filter, filename_query=q
    )


@router.get(
    "/{workspace_id}/documents/{document_id}",
    response_model=DocumentRead,
)
async def get_document(
    request: Request,
    document_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> DocumentRead:
    return document_service.get_document(
        db,
        workspace_id=ctx.workspace.id,
        document_id=document_id,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


@router.get(
    "/{workspace_id}/documents/{document_id}/chunks",
    response_model=list[DocumentChunkRead],
)
async def list_document_chunks(
    request: Request,
    document_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> list[DocumentChunkRead]:
    """The full document viewer (Issue #41): every chunk of a document,
    in order, distinct from the single-chunk source-inspection endpoint
    below."""
    return document_service.list_document_chunks(
        db,
        workspace_id=ctx.workspace.id,
        document_id=document_id,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


@router.get(
    "/{workspace_id}/documents/{document_id}/chunks/{chunk_id}",
    response_model=DocumentChunkRead,
)
async def get_document_chunk(
    request: Request,
    document_id: uuid.UUID,
    chunk_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> DocumentChunkRead:
    """Source inspection: the exact evidence text a citation (see
    `CitationRead.chunk_id` in app/schemas/conversation.py) was grounded
    in, so a user can verify an answer against its actual source."""
    return document_service.get_document_chunk(
        db,
        workspace_id=ctx.workspace.id,
        document_id=document_id,
        chunk_id=chunk_id,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
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


@router.patch(
    "/{workspace_id}/documents/{document_id}",
    response_model=DocumentRead,
)
async def rename_document(
    request: Request,
    document_id: uuid.UUID,
    body: DocumentRename,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
) -> DocumentRead:
    return document_service.rename_document(
        db,
        workspace_id=ctx.workspace.id,
        document_id=document_id,
        filename=body.filename,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


@router.delete(
    "/{workspace_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    request: Request,
    document_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage_provider),
) -> None:
    await document_service.delete_document(
        db,
        workspace_id=ctx.workspace.id,
        document_id=document_id,
        storage=storage,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


# CR/LF and every other ASCII control character (header/response-splitting),
# the double quote and the backslash (which would let a crafted filename
# break out of, or escape the closing quote of, the quoted `filename="..."`
# parameter).
_UNSAFE_HEADER_CHARS = re.compile(r'[\x00-\x1f\x7f"\\]')


def _content_disposition(filename: str) -> str:
    """Builds a safe `Content-Disposition: attachment` value for a
    user-supplied filename (docs/SECURITY.md "Upload & document safety":
    never used as a storage path, but it is echoed into a header here).

    HTTP header values are latin-1 encoded by the ASGI layer, so a
    filename with any character outside latin-1 (CJK, emoji, ...) used
    verbatim raised `UnicodeEncodeError` -> 500. An ASCII-only name keeps
    the plain `filename="..."` form unchanged; otherwise an ASCII
    fallback (`_` for each non-ASCII character) is emitted alongside the
    RFC 6266 / RFC 5987 `filename*=UTF-8''<percent-encoded>` form, which
    every current browser prefers.
    """
    sanitized = _UNSAFE_HEADER_CHARS.sub("", filename) or "download"
    if sanitized.isascii():
        return f'attachment; filename="{sanitized}"'
    fallback = "".join(char if char.isascii() else "_" for char in sanitized)
    # `errors="replace"` keeps a lone surrogate (valid in a Python str,
    # not in UTF-8) from raising here.
    encoded = quote(sanitized, safe="", encoding="utf-8", errors="replace")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


@router.get(
    "/{workspace_id}/documents/{document_id}/download",
)
async def download_document(
    request: Request,
    document_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage_provider),
) -> Response:
    document, content = document_service.download_document(
        db,
        workspace_id=ctx.workspace.id,
        document_id=document_id,
        storage=storage,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )
    return Response(
        content=content,
        media_type=document.mime_type,
        headers={"Content-Disposition": _content_disposition(document.filename)},
    )
