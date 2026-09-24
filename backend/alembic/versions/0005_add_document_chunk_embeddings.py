"""Add embedding columns and vector index to document_chunks.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-24

GitHub Issue #3, Slice 3.7. `document_chunks` (migration 0004) deliberately
shipped without an embedding column — see `app/models/document_chunk.py`'s
docstring: "adding a pgvector column later is a small additive migration
once the embedding provider/model/dimension is actually chosen." This is
that migration.

`embedding` is a fixed-dimension pgvector column (`Vector(384)`) — the
dimension of `app.ingestion.embedding.LocalHashingEmbeddingProvider`
(Slice 3.7's shipped provider), chosen to match common small real
embedding models (e.g. all-MiniLM-L6-v2/BGE-small) so swapping to one of
those later needs no migration; swapping to a different-dimension model
would. `embedding_model`/`embedding_dimension` are per-row provenance
columns (docs/RAG_DESIGN.md: "tracking of which model/version/dimension
produced each embedding — this matters because changing the embedding
model invalidates prior vectors") — a future model swap can identify and
re-embed only the rows produced by the old model, rather than guessing
from the column's fixed width alone.

An HNSW index (cosine distance) is created directly against the column —
unlike IVFFlat, HNSW needs no separate training/list-count step and stays
correct as rows are inserted/updated, which matches this project's
synchronous, incremental (not bulk-loaded) ingestion pattern. All three
columns are nullable: existing `CHUNKED`-status documents predate this
migration and have no embedding yet, and get one the next time they're
processed (Slice 3.7's `process_document()` treats `CHUNKED` as
resumable).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_EMBEDDING_DIMENSION = 384


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSION), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_model", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding_dimension")
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
