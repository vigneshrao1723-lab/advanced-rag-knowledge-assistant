# 0002. PostgreSQL + pgvector as the initial vector store

**Status:** Accepted
**Date:** 2026-09-11

## Context

The retrieval pipeline needs dense vector similarity search alongside
lexical (BM25) search, relational data (users, workspaces, documents,
conversations), and metadata filtering. A separate, dedicated vector
database (e.g., Qdrant) is a common choice for the vector-search portion of
a RAG system, but this project has also committed to a modular monolith
with minimal infrastructure (see
[0001](0001-modular-monolith-over-microservices.md)).

## Decision

**PostgreSQL, with the `pgvector` extension, is the single database for
both relational data and vector search** in the initial implementation.
There is no separate vector database and no second database of any kind.

## Alternatives considered

- **Dedicated vector database (e.g., Qdrant)** — rejected for the initial
  implementation. It would introduce a second datastore to operate, keep
  consistent with Postgres (e.g., for workspace-scoped filtering joins), and
  deploy — extra operational surface without a demonstrated need at this
  project's current scale. Not ruled out permanently: if pgvector's
  performance or feature set proves insufficient at a measured scale, this
  decision can be revisited via a new ADR.
- **Managed vector search service** — rejected for the same reason, plus it
  would introduce an external dependency inconsistent with the project's
  current self-hosted, Docker-based local development direction (see
  [`docs/DEPLOYMENT.md`](../DEPLOYMENT.md)).

## Consequences

- One database to run, back up, and reason about transactionally —
  relational joins between `document_chunks` embeddings and workspace/
  document/collection metadata are simple SQL, not a cross-store join.
- pgvector's indexing (e.g., IVFFlat/HNSW) and performance characteristics
  must be understood and tuned as retrieval volume grows; if it becomes a
  measured bottleneck, that evidence is what would justify revisiting this
  decision — not a preference for a "proper" vector database in the
  abstract.
- BM25/lexical search will also need a PostgreSQL-native approach (e.g.,
  full-text search) to avoid introducing a separate search engine, unless a
  future ADR documents otherwise.
