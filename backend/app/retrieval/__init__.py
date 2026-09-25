"""Retrieval pipeline (docs/ARCHITECTURE.md "Module layout", GitHub
Issue #4): dense (pgvector) retrieval, lexical (Postgres full-text
search) retrieval, Reciprocal Rank Fusion, workspace/document metadata
filtering, and a `Reranker` abstraction. `hybrid_search()`
(`app.retrieval.service`) is the single entry point everything else in
this package composes into.

Every query in this package is workspace-scoped at the SQL level (a
`WHERE workspace_id = ...` clause, never a filter applied after the
fact) — retrieved content must never cross a workspace boundary, per
docs/SECURITY.md's multi-tenancy requirements. Every query also joins
`documents` and requires `status = READY`, so a document's chunks only
become retrievable once the full ingestion pipeline (Issue #3) has
actually finished for it — a document still mid-pipeline never appears
in partial/inconsistent search results.
"""

from __future__ import annotations

from app.retrieval.types import RetrievalCandidate

__all__ = ["RetrievalCandidate"]
