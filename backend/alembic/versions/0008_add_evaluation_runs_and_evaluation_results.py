"""Add evaluation_runs, evaluation_results.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26

GitHub Issue #7. Extends Issue #4 Slice 4.4's fixture-scale evaluation
hooks into real, persisted, comparable experiment tracking, per
docs/DATA_MODEL.md's "evaluation_runs"/"evaluation_results" entities
(previously PROPOSED-only, no schema).

`evaluation_runs.workspace_id` is nullable with `ON DELETE SET NULL`,
not CASCADE: the evaluation script runs against a dedicated, throwaway
workspace deleted at the end of every run, but an evaluation run's
whole purpose is to be a durable, comparable-over-time record that must
outlive that throwaway workspace -- see `app/models/evaluation_run.py`'s
docstring for the full reasoning (matches `retrieval_events
.conversation_id`'s own precedent).

`evaluation_results` is one row per metric per run (not a wide/sparse
fixed-column table), `ON DELETE CASCADE` from `evaluation_runs`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("chunking_strategy", sa.Text(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=True),
        sa.Column("chunk_overlap", sa.Integer(), nullable=True),
        sa.Column("retrieval_method", sa.Text(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("reranker", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.Text(), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evaluation_runs_workspace_id"), "evaluation_runs", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_runs_created_at"), "evaluation_runs", ["created_at"], unique=False
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("evaluation_run_id", sa.UUID(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evaluation_results_evaluation_run_id"),
        "evaluation_results",
        ["evaluation_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_evaluation_results_evaluation_run_id"), table_name="evaluation_results"
    )
    op.drop_table("evaluation_results")

    op.drop_index(op.f("ix_evaluation_runs_created_at"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_workspace_id"), table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
