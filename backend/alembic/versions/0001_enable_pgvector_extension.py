"""Enable the pgvector extension.

Revision ID: 0001
Revises:
Create Date: 2026-09-11

Per ADR 0002, PostgreSQL + pgvector is the single datastore for both
relational data and vector search — this migration enables the extension
that later issues' `document_chunks` embedding column depends on.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
