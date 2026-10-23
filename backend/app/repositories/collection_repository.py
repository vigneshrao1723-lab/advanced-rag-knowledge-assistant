from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.collection_document import CollectionDocument


def create(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID | None,
    name: str,
    description: str | None,
) -> Collection:
    collection = Collection(
        workspace_id=workspace_id, created_by=created_by, name=name, description=description
    )
    db.add(collection)
    db.flush()
    db.refresh(collection)
    return collection


def get_by_id_for_workspace(
    db: Session, *, workspace_id: uuid.UUID, collection_id: uuid.UUID
) -> Collection | None:
    """Scoped to `workspace_id` in the query itself -- the same
    IDOR-defense shape as every other workspace-scoped lookup in this
    codebase (`document_repository.get_by_id_for_workspace()`,
    `conversation_repository.get_by_id_for_workspace()`)."""
    return db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()


def list_for_workspace_with_counts(
    db: Session, *, workspace_id: uuid.UUID
) -> list[tuple[Collection, int]]:
    """Newest first, each paired with its document count via one
    aggregate query -- avoids an N+1 count-per-collection query when
    listing a workspace's collections."""
    rows = db.execute(
        select(Collection, func.count(CollectionDocument.id))
        .outerjoin(CollectionDocument, CollectionDocument.collection_id == Collection.id)
        .where(Collection.workspace_id == workspace_id)
        .group_by(Collection.id)
        .order_by(Collection.created_at.desc())
    ).all()
    return [(collection, count) for collection, count in rows]


def count_documents(db: Session, *, collection_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count(CollectionDocument.id)).where(
            CollectionDocument.collection_id == collection_id
        )
    ).scalar_one()


def update(
    db: Session, *, collection: Collection, name: str, description: str | None
) -> Collection:
    collection.name = name
    collection.description = description
    db.add(collection)
    db.flush()
    db.refresh(collection)
    return collection


def delete(db: Session, *, collection: Collection) -> None:
    db.delete(collection)
    db.flush()


__all__ = [
    "count_documents",
    "create",
    "delete",
    "get_by_id_for_workspace",
    "list_for_workspace_with_counts",
    "update",
]
