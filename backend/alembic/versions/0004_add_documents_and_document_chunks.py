"""Add documents and document_chunks.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-20

GitHub Issue #3, Slice 3.1 (schema only). Per docs/DATA_MODEL.md and
docs/RAG_DESIGN.md: `documents` (an uploaded source file and its processing
status within a workspace) and `document_chunks` (its chunked content,
prepared for retrieval once Issue #4 exists).

`document_status` is a native Postgres enum matching the documented
lifecycle exactly (docs/REQUIREMENTS.md / docs/RAG_DESIGN.md) —
`UPLOADED, PROCESSING, PARSED, CLEANED, CHUNKED, EMBEDDED, INDEXED, READY,
FAILED`. Unlike `audit_logs.event_type` (a deliberately open-ended plain
string, since that taxonomy keeps growing), this lifecycle is a fixed,
closed set defined once by the project specification, so it follows
`workspace_role`'s native-enum convention instead.

`document_chunks` deliberately has no embedding column yet — see
`app/models/document_chunk.py`'s docstring. Adding a pgvector column later
is a small additive migration once the embedding provider/model/dimension
is actually chosen (a later slice), not a breaking change to this one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_DOCUMENT_STATUS_ENUM = sa.Enum(
    "UPLOADED",
    "PROCESSING",
    "PARSED",
    "CLEANED",
    "CHUNKED",
    "EMBEDDED",
    "INDEXED",
    "READY",
    "FAILED",
    name="document_status",
)


def upgrade() -> None:
    # `create_table` below creates the `document_status` enum type itself
    # (via the column's Enum type before-create hook), matching how
    # migration 0002 creates `workspace_role` — no separate `.create()`
    # call here, or Postgres raises DuplicateObject.
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column(
            "status",
            _DOCUMENT_STATUS_ENUM,
            nullable=False,
            server_default="UPLOADED",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_document_storage_key"),
        sa.UniqueConstraint(
            "workspace_id", "checksum_sha256", name="uq_document_workspace_checksum"
        ),
    )
    op.create_index(op.f("ix_documents_workspace_id"), "documents", ["workspace_id"], unique=False)

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_chunks_workspace_id"), "document_chunks", ["workspace_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_chunks_workspace_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index(op.f("ix_documents_workspace_id"), table_name="documents")
    op.drop_table("documents")
    _DOCUMENT_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
