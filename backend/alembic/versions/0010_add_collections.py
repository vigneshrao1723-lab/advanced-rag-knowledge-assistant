"""Add collections and collection_documents.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-23

GitHub Issue #41 (feature-completion sprint): `collections` (a logical
grouping of documents within a workspace) and `collection_documents` (the
many-to-many link to the documents it groups) — both specified as
`PROPOSED` in docs/DATA_MODEL.md since the original design pass, built out
here. Follows the exact table-pair pattern migration `0004`
(`documents`/`document_chunks`) established: the owning table first, then
its child/link table, both with a surrogate UUID primary key and a
denormalized `workspace_id` for scoped queries without an extra join.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_collections_workspace_id"), "collections", ["workspace_id"], unique=False
    )

    op.create_table(
        "collection_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("collection_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "document_id", name="uq_collection_document"),
    )
    op.create_index(
        op.f("ix_collection_documents_collection_id"),
        "collection_documents",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_documents_document_id"),
        "collection_documents",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_collection_documents_workspace_id"),
        "collection_documents",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_collection_documents_workspace_id"), table_name="collection_documents")
    op.drop_index(op.f("ix_collection_documents_document_id"), table_name="collection_documents")
    op.drop_index(op.f("ix_collection_documents_collection_id"), table_name="collection_documents")
    op.drop_table("collection_documents")

    op.drop_index(op.f("ix_collections_workspace_id"), table_name="collections")
    op.drop_table("collections")
