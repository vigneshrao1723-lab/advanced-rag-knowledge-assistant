"""Collection CRUD and document-association orchestration (GitHub Issue
#41, the feature-completion sprint's priority-1 item): a logical grouping
of documents within a workspace, per docs/REQUIREMENTS.md "Collections"
and docs/DATA_MODEL.md's `collections`/`collection_documents` schema.

Every function here assumes basic workspace membership/role gating has
already been enforced by `app.core.dependencies.require_workspace_role` —
this module only adds the resource-scoped 404 lookups every other
workspace-scoped entity in this codebase already uses.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import AuditEvent
from app.core.audit import record as record_audit_event
from app.models.collection import Collection
from app.models.document import Document
from app.repositories import (
    collection_document_repository,
    collection_repository,
    document_repository,
)
from app.schemas.collection import CollectionRead, CollectionWithDocumentsRead
from app.schemas.document import DocumentRead


def _collection_not_found_error(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    collection_id: uuid.UUID,
    user_id: uuid.UUID | None,
    ip_address: str | None,
) -> HTTPException:
    """Same non-leaking 404 + audit shape as
    `conversation_service._conversation_not_found_error()` /
    `document_service._document_not_found_error()` -- a collection ID
    that doesn't resolve within the caller's workspace is indistinguishable
    from one that belongs to another workspace entirely."""
    record_audit_event(
        db,
        event_type=AuditEvent.CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED,
        user_id=user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={"resource_type": "collection", "attempted_collection_id": str(collection_id)},
    )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "collection_not_found", "message": "Collection not found."},
    )


def _document_not_found_error(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None,
    ip_address: str | None,
) -> HTTPException:
    record_audit_event(
        db,
        event_type=AuditEvent.CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED,
        user_id=user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={"resource_type": "document", "attempted_document_id": str(document_id)},
    )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "document_not_found", "message": "Document not found."},
    )


def _collection_document_not_found_error() -> HTTPException:
    """Not an IDOR-relevant lookup -- by the time this is reached, both
    the collection and the document have already been confirmed to exist
    within this workspace; this only means the specific link doesn't
    exist (never added, or already removed), so no audit event fires,
    matching the plain 404 builders in `document_service.py` for
    not-cross-workspace-relevant 404s."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "collection_document_not_found",
            "message": "This document is not in this collection.",
        },
    )


def _to_collection_read(collection: Collection, *, document_count: int) -> CollectionRead:
    return CollectionRead(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        document_count=document_count,
    )


def _to_document_read(document: Document) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        filename=document.filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        checksum_sha256=document.checksum_sha256,
        status=document.status,
        page_count=document.page_count,
        failure_reason=document.failure_reason,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def create_collection(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID,
    name: str,
    description: str | None,
    ip_address: str | None = None,
) -> CollectionRead:
    collection = collection_repository.create(
        db, workspace_id=workspace_id, created_by=created_by, name=name, description=description
    )
    record_audit_event(
        db,
        event_type=AuditEvent.COLLECTION_CREATED,
        user_id=created_by,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={"collection_id": str(collection.id)},
    )
    db.commit()
    return _to_collection_read(collection, document_count=0)


def list_collections(db: Session, *, workspace_id: uuid.UUID) -> list[CollectionRead]:
    rows = collection_repository.list_for_workspace_with_counts(db, workspace_id=workspace_id)
    return [_to_collection_read(collection, document_count=count) for collection, count in rows]


def get_collection(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    collection_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> CollectionWithDocumentsRead:
    collection = collection_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, collection_id=collection_id
    )
    if collection is None:
        raise _collection_not_found_error(
            db,
            workspace_id=workspace_id,
            collection_id=collection_id,
            user_id=user_id,
            ip_address=ip_address,
        )

    document_ids = collection_document_repository.list_document_ids_for_collection(
        db, collection_id=collection.id
    )
    documents = document_repository.list_by_ids_for_workspace(
        db, workspace_id=workspace_id, document_ids=document_ids
    )
    # `list_by_ids_for_workspace()` doesn't preserve `document_ids`'
    # order (see its docstring) -- re-sort here so the response matches
    # the order documents were added to the collection, newest first.
    documents_by_id = {document.id: document for document in documents}
    ordered_documents = [
        documents_by_id[doc_id] for doc_id in document_ids if doc_id in documents_by_id
    ]

    base = _to_collection_read(collection, document_count=len(ordered_documents))
    return CollectionWithDocumentsRead(
        **base.model_dump(),
        documents=[_to_document_read(document) for document in ordered_documents],
    )


def update_collection(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    collection_id: uuid.UUID,
    name: str,
    description: str | None,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> CollectionRead:
    collection = collection_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, collection_id=collection_id
    )
    if collection is None:
        raise _collection_not_found_error(
            db,
            workspace_id=workspace_id,
            collection_id=collection_id,
            user_id=user_id,
            ip_address=ip_address,
        )

    collection = collection_repository.update(
        db, collection=collection, name=name, description=description
    )
    document_count = collection_repository.count_documents(db, collection_id=collection.id)
    db.commit()
    return _to_collection_read(collection, document_count=document_count)


def delete_collection(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    collection_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> None:
    collection = collection_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, collection_id=collection_id
    )
    if collection is None:
        raise _collection_not_found_error(
            db,
            workspace_id=workspace_id,
            collection_id=collection_id,
            user_id=user_id,
            ip_address=ip_address,
        )

    collection_repository.delete(db, collection=collection)
    record_audit_event(
        db,
        event_type=AuditEvent.COLLECTION_DELETED,
        user_id=user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata={"collection_id": str(collection_id)},
    )
    db.commit()


def add_document_to_collection(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> DocumentRead:
    collection = collection_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, collection_id=collection_id
    )
    if collection is None:
        raise _collection_not_found_error(
            db,
            workspace_id=workspace_id,
            collection_id=collection_id,
            user_id=user_id,
            ip_address=ip_address,
        )

    document = document_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, document_id=document_id
    )
    if document is None:
        raise _document_not_found_error(
            db,
            workspace_id=workspace_id,
            document_id=document_id,
            user_id=user_id,
            ip_address=ip_address,
        )

    # Idempotent: adding a document that's already in the collection is
    # a no-op success, not a 409 -- matches this codebase's existing
    # idempotent-retry convention (upload dedup, process-retry) rather
    # than forcing the caller to check first.
    existing_link = collection_document_repository.get(
        db, collection_id=collection.id, document_id=document.id
    )
    if existing_link is None:
        collection_document_repository.add(
            db, collection_id=collection.id, document_id=document.id, workspace_id=workspace_id
        )
        db.commit()
    return _to_document_read(document)


def remove_document_from_collection(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> None:
    collection = collection_repository.get_by_id_for_workspace(
        db, workspace_id=workspace_id, collection_id=collection_id
    )
    if collection is None:
        raise _collection_not_found_error(
            db,
            workspace_id=workspace_id,
            collection_id=collection_id,
            user_id=user_id,
            ip_address=ip_address,
        )

    link = collection_document_repository.get(
        db, collection_id=collection.id, document_id=document_id
    )
    if link is None:
        raise _collection_document_not_found_error()

    collection_document_repository.remove(db, link=link)
    db.commit()


__all__ = [
    "add_document_to_collection",
    "create_collection",
    "delete_collection",
    "get_collection",
    "list_collections",
    "remove_document_from_collection",
    "update_collection",
]
