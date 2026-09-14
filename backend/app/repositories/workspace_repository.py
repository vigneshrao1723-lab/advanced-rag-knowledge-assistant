from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.workspace import Workspace


def get_by_id(db: Session, workspace_id: uuid.UUID) -> Workspace | None:
    return db.get(Workspace, workspace_id)


def create(db: Session, *, name: str) -> Workspace:
    workspace = Workspace(name=name)
    db.add(workspace)
    db.flush()
    db.refresh(workspace)
    return workspace


def update_name(db: Session, workspace: Workspace, *, name: str) -> Workspace:
    workspace.name = name
    db.flush()
    db.refresh(workspace)
    return workspace


def delete(db: Session, workspace: Workspace) -> None:
    db.delete(workspace)
    db.flush()
