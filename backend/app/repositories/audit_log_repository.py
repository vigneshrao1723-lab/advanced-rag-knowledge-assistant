from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def create(
    db: Session,
    *,
    event_type: str,
    user_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    ip_address: str | None,
    metadata: dict[str, Any] | None,
) -> AuditLog:
    """Commits immediately, unlike other repositories (which only flush and
    let the caller's service function commit once at the end of its unit
    of work). An audit trail must survive even when the surrounding
    request goes on to fail/reject — e.g. an authorization-denied event
    recorded right before raising the 403/404 that denies it."""
    entry = AuditLog(
        event_type=event_type,
        user_id=user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        event_metadata=metadata,
    )
    db.add(entry)
    db.commit()
    return entry
