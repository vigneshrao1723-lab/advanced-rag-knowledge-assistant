"""The `documents` entity (docs/DATA_MODEL.md) — an uploaded source file and
its processing status within a workspace.

Slice 3.1 (GitHub Issue #3) adds only the persistence representation of the
document lifecycle described in docs/RAG_DESIGN.md/docs/REQUIREMENTS.md:

    UPLOADED -> PROCESSING -> PARSED -> CLEANED -> CHUNKED -> EMBEDDED
             -> INDEXED -> READY / FAILED

`status` uses a native Postgres enum (`DocumentStatus`), not a plain string
like `AuditLog.event_type`: unlike the audit-event taxonomy (which is
deliberately open-ended and grows across unrelated future issues), this
lifecycle is a fixed, closed set of states defined once by the project
specification, so it follows `WorkspaceMember.role`'s convention
(`workspace_role` native enum) rather than `audit_logs`'s. No state-machine
transition logic is implemented in this slice — this column only records
state, and no processing pipeline exists yet to change it.

`uploaded_by` uses `ON DELETE SET NULL`, matching `AuditLog.user_id`'s
precedent for the same reason: a document (and its audit trail) should
outlive the account that uploaded it, not disappear or cascade-delete when
a user is removed.

`storage_key` is a server-generated identifier for the future
`StorageProvider` abstraction (not implemented this slice) — never the
user-supplied `filename`, which is display-only and must never be used to
derive a storage path (docs/SECURITY.md "Upload & document safety").
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentStatus(enum.StrEnum):
    """Values match docs/REQUIREMENTS.md / docs/RAG_DESIGN.md's documented
    ingestion lifecycle exactly — not invented for this slice."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PARSED = "PARSED"
    CLEANED = "CLEANED"
    CHUNKED = "CHUNKED"
    EMBEDDED = "EMBEDDED"
    INDEXED = "INDEXED"
    READY = "READY"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "checksum_sha256", name="uq_document_workspace_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=True),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
