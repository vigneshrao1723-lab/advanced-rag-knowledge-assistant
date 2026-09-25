"""Add conversations, messages, citations, retrieval_events.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24

GitHub Issue #4, Slice 4.1. Per docs/DATA_MODEL.md and docs/REQUIREMENTS.md
"Chat"/"Citations"/"Observability": the minimal persistence shape Issue #4
needs to write a generation result (and the retrieval that produced it)
somewhere. The richer conversation-management surface (rename/delete/
search/regenerate/feedback) is Issue #5, built on this schema unchanged.

`message_role` is a native Postgres enum (`USER`/`ASSISTANT`), matching
`workspace_role`'s convention — a fixed, closed set, not an open-ended
taxonomy like `audit_logs.event_type`.

`citations.document_id`/`page`/`section` are denormalized from the cited
`document_chunks` row at citation-creation time (see
`app/models/citation.py`'s docstring) so a citation answers "which
document/page/section" directly, without a join, matching
`document_chunks.workspace_id`'s own denormalization precedent.

`retrieval_events.results` is `JSONB` (a ranked-candidate-list snapshot),
matching `audit_logs.event_metadata`'s existing `JSONB` precedent — no new
column-type pattern introduced.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_MESSAGE_ROLE_ENUM = sa.Enum("USER", "ASSISTANT", name="message_role")


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
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
        op.f("ix_conversations_workspace_id"), "conversations", ["workspace_id"], unique=False
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("role", _MESSAGE_ROLE_ENUM, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False
    )
    op.create_index(op.f("ix_messages_workspace_id"), "messages", ["workspace_id"], unique=False)

    op.create_table(
        "citations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_citations_message_id"), "citations", ["message_id"], unique=False)
    op.create_index(
        op.f("ix_citations_workspace_id"), "citations", ["workspace_id"], unique=False
    )
    op.create_index(op.f("ix_citations_document_id"), "citations", ["document_id"], unique=False)
    op.create_index(op.f("ix_citations_chunk_id"), "citations", ["chunk_id"], unique=False)

    op.create_table(
        "retrieval_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("rewritten_query_text", sa.Text(), nullable=True),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_retrieval_events_workspace_id"), "retrieval_events", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_retrieval_events_conversation_id"),
        "retrieval_events",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_events_created_at"), "retrieval_events", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_retrieval_events_created_at"), table_name="retrieval_events")
    op.drop_index(op.f("ix_retrieval_events_conversation_id"), table_name="retrieval_events")
    op.drop_index(op.f("ix_retrieval_events_workspace_id"), table_name="retrieval_events")
    op.drop_table("retrieval_events")

    op.drop_index(op.f("ix_citations_chunk_id"), table_name="citations")
    op.drop_index(op.f("ix_citations_document_id"), table_name="citations")
    op.drop_index(op.f("ix_citations_workspace_id"), table_name="citations")
    op.drop_index(op.f("ix_citations_message_id"), table_name="citations")
    op.drop_table("citations")

    op.drop_index(op.f("ix_messages_workspace_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")
    _MESSAGE_ROLE_ENUM.drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f("ix_conversations_workspace_id"), table_name="conversations")
    op.drop_table("conversations")
