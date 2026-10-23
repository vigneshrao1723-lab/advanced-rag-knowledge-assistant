"""Collection endpoints (GitHub Issue #41): logical grouping of documents
within a workspace. See app/services/collection_service.py for the CRUD
and document-association orchestration.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.dependencies import WorkspaceContext, require_workspace_role
from app.core.rate_limit import client_ip
from app.models.workspace_member import WorkspaceRole
from app.schemas.collection import (
    CollectionCreate,
    CollectionDocumentAdd,
    CollectionRead,
    CollectionUpdate,
    CollectionWithDocumentsRead,
)
from app.schemas.document import DocumentRead
from app.services import collection_service

router = APIRouter(prefix="/workspaces", tags=["collections"])


@router.get(
    "/{workspace_id}/collections",
    response_model=list[CollectionRead],
)
async def list_collections(
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> list[CollectionRead]:
    return collection_service.list_collections(db, workspace_id=ctx.workspace.id)


@router.post(
    "/{workspace_id}/collections",
    response_model=CollectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_collection(
    request: Request,
    body: CollectionCreate,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
) -> CollectionRead:
    return collection_service.create_collection(
        db,
        workspace_id=ctx.workspace.id,
        created_by=ctx.user.id,
        name=body.name,
        description=body.description,
        ip_address=client_ip(request),
    )


@router.get(
    "/{workspace_id}/collections/{collection_id}",
    response_model=CollectionWithDocumentsRead,
)
async def get_collection(
    request: Request,
    collection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.VIEWER)),
    db: Session = Depends(get_db),
) -> CollectionWithDocumentsRead:
    return collection_service.get_collection(
        db,
        workspace_id=ctx.workspace.id,
        collection_id=collection_id,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


@router.patch(
    "/{workspace_id}/collections/{collection_id}",
    response_model=CollectionRead,
)
async def update_collection(
    request: Request,
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
) -> CollectionRead:
    return collection_service.update_collection(
        db,
        workspace_id=ctx.workspace.id,
        collection_id=collection_id,
        name=body.name,
        description=body.description,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


@router.delete(
    "/{workspace_id}/collections/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_collection(
    request: Request,
    collection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
) -> None:
    collection_service.delete_collection(
        db,
        workspace_id=ctx.workspace.id,
        collection_id=collection_id,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


@router.post(
    "/{workspace_id}/collections/{collection_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_document_to_collection(
    request: Request,
    collection_id: uuid.UUID,
    body: CollectionDocumentAdd,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
) -> DocumentRead:
    return collection_service.add_document_to_collection(
        db,
        workspace_id=ctx.workspace.id,
        collection_id=collection_id,
        document_id=body.document_id,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )


@router.delete(
    "/{workspace_id}/collections/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_document_from_collection(
    request: Request,
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role(WorkspaceRole.MEMBER)),
    db: Session = Depends(get_db),
) -> None:
    collection_service.remove_document_from_collection(
        db,
        workspace_id=ctx.workspace.id,
        collection_id=collection_id,
        document_id=document_id,
        user_id=ctx.user.id,
        ip_address=client_ip(request),
    )
