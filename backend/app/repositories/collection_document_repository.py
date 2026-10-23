from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collection_document import CollectionDocument


def get(
    db: Session, *, collection_id: uuid.UUID, document_id: uuid.UUID
) -> CollectionDocument | None:
    return db.execute(
        select(CollectionDocument).where(
            CollectionDocument.collection_id == collection_id,
            CollectionDocument.document_id == document_id,
        )
    ).scalar_one_or_none()


def add(
    db: Session, *, collection_id: uuid.UUID, document_id: uuid.UUID, workspace_id: uuid.UUID
) -> CollectionDocument:
    link = CollectionDocument(
        collection_id=collection_id, document_id=document_id, workspace_id=workspace_id
    )
    db.add(link)
    db.flush()
    db.refresh(link)
    return link


def remove(db: Session, *, link: CollectionDocument) -> None:
    db.delete(link)
    db.flush()


def list_document_ids_for_collection(db: Session, *, collection_id: uuid.UUID) -> list[uuid.UUID]:
    """Ordered by when each document was added to the collection --
    matches `document_repository.list_for_workspace()`'s own
    newest-first-is-most-useful precedent for a UI listing."""
    return list(
        db.execute(
            select(CollectionDocument.document_id)
            .where(CollectionDocument.collection_id == collection_id)
            .order_by(CollectionDocument.created_at.desc())
        ).scalars()
    )


__all__ = ["add", "get", "list_document_ids_for_collection", "remove"]
