"""Add full-text-search GIN index to document_chunks.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-25

GitHub Issue #4, Slice 4.2. Lexical/BM25-style retrieval
(`app/retrieval/lexical.py`) queries `to_tsvector('english', content) @@
plainto_tsquery('english', :query)` — a functional (expression) GIN index
on that exact expression lets Postgres use the index instead of a
sequential scan as `document_chunks` grows, per ADR 0002's own consequence
("BM25/lexical search will also need a PostgreSQL-native approach, e.g.
full-text search, to avoid introducing a separate search engine"). No new
column: `to_tsvector('english', content)` is computed at query/index time,
not stored.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_document_chunks_content_fts ON document_chunks "
        "USING GIN (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_document_chunks_content_fts")
