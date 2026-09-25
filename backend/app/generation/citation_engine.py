"""Citation engine — turns a `BuiltContext`'s evidence blocks into
persisted `Citation` rows, tied to the specific message and the exact
chunks the answer actually drew from (docs/REQUIREMENTS.md "Citation
generation tied to specific evidence chunks").
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.generation.context_builder import BuiltContext
from app.models.citation import Citation
from app.repositories import citation_repository


def create_citations(
    db: Session, *, message_id: uuid.UUID, workspace_id: uuid.UUID, context: BuiltContext
) -> list[Citation]:
    """Does not commit -- the caller (the conversation service) persists
    this together with the assistant `Message` row it belongs to, in one
    transaction, matching the "commit at a real stage boundary" pattern
    already established across this codebase (e.g. chunk rows +
    `CHUNKED` status, Issue #3)."""
    if not context.blocks:
        return []
    return citation_repository.bulk_create(
        db,
        message_id=message_id,
        workspace_id=workspace_id,
        candidates=[(block.marker, block.candidate) for block in context.blocks],
    )


__all__ = ["create_citations"]
