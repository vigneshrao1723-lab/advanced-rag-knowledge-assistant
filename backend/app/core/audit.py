"""Security-relevant audit event recording (docs/SECURITY.md "Audit
logging").

`AuditEvent` is the closed, typed set of event names application code may
emit — `AuditLog.event_type` (app/models/audit_log.py) is a plain indexed
string, not a database enum, precisely so this set can grow over future
issues without a migration; it should still only ever grow through this
class, not ad-hoc strings scattered through the codebase.

Never pass passwords, raw tokens, session secrets, or cookies in
`metadata` — see the module docstring on `app/models/audit_log.py`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import audit_log_repository


class AuditEvent:
    USER_REGISTERED = "user_registered"
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SESSION_REVOKED = "session_revoked"
    REFRESH_TOKEN_REUSE_DETECTED = "refresh_token_reuse_detected"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_SUCCEEDED = "password_reset_succeeded"
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_DELETED = "workspace_deleted"
    WORKSPACE_MEMBER_ADDED = "workspace_member_added"
    WORKSPACE_MEMBER_REMOVED = "workspace_member_removed"
    WORKSPACE_MEMBER_ROLE_CHANGED = "workspace_member_role_changed"
    AUTHORIZATION_DENIED = "authorization_denied"
    # Distinct from AUTHORIZATION_DENIED (which fires at the
    # workspace-membership gate, before a request ever reaches an
    # endpoint's own logic): this fires when an already-workspace-
    # authorized request supplies a resource ID (document/conversation/
    # message) that doesn't resolve within that workspace -- i.e. either
    # a genuinely nonexistent ID, or one belonging to a workspace the
    # caller has no access to. Both cases return the same non-leaking
    # `404`; this audits that the resource-scoped lookup itself was
    # denied, whichever reason produced it (GitHub Issue #7 "cross-
    # workspace access attempts (successful or blocked)").
    CROSS_WORKSPACE_RESOURCE_ACCESS_DENIED = "cross_workspace_resource_access_denied"
    RATE_LIMITED = "rate_limited"
    ABUSE_TEMPORARY_BLOCK_APPLIED = "abuse_temporary_block_applied"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_PARSED = "document_parsed"
    DOCUMENT_PARSING_FAILED = "document_parsing_failed"
    DOCUMENT_CLEANING_FAILED = "document_cleaning_failed"
    DOCUMENT_CHUNKED = "document_chunked"
    DOCUMENT_CHUNKING_FAILED = "document_chunking_failed"
    DOCUMENT_EMBEDDING_FAILED = "document_embedding_failed"
    DOCUMENT_READY = "document_ready"


def record(
    db: Session,
    *,
    event_type: str,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    audit_log_repository.create(
        db,
        event_type=event_type,
        user_id=user_id,
        workspace_id=workspace_id,
        ip_address=ip_address,
        metadata=metadata,
    )
