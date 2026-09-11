# Data Model

**Status:** PROPOSED — no database schema or migrations exist yet. This
document records the intended core entities so future implementation stays
consistent; it is not evidence of an implemented schema.

## Core entities (proposed)

| Entity | Purpose |
|---|---|
| `users` | Account identity and credentials |
| `workspaces` | Isolation boundary for a user or team's data |
| `workspace_members` | Membership + role (`OWNER`/`ADMIN`/`MEMBER`/`VIEWER`) linking users to workspaces |
| `sessions` | Server-tracked login/device session backing refresh-token issuance, listing, and revocation (see [ADR 0003](DECISIONS/0003-authentication-session-architecture.md)) |
| `documents` | Uploaded source files and their processing status |
| `document_chunks` | Chunked, embedded units of a document, used for retrieval |
| `collections` | Logical grouping of documents within a workspace |
| `collection_documents` | Many-to-many link between collections and documents |
| `conversations` | A chat session within a workspace |
| `messages` | Individual messages within a conversation (user + assistant) |
| `citations` | Links between a generated answer/message and the evidence (chunks) it cites |
| `retrieval_events` | Record of a retrieval operation (query, method, results, scores) for observability/evaluation |
| `evaluation_runs` | A configured evaluation experiment (embedding model, chunking strategy, retrieval method, etc.) |
| `evaluation_results` | Computed metrics for an `evaluation_run` |
| `audit_logs` | Security-relevant action log (see [`docs/SECURITY.md`](SECURITY.md)) |

## Potential entities (subject to architectural validation)

These are plausible additions identified during design but not yet
committed to — each needs validation against real implementation needs
before being added to the core list above:

- `document_processing_jobs` — if ingestion pipeline stages need durable,
  queryable job records beyond the `documents` status field.
- `voice_sessions` — if voice interactions need state beyond what
  `conversations`/`messages` already capture.
- `feedback` — for user feedback on generated answers, if it needs to be
  more structured than a field on `messages`.

## Relationships (indicative, not final)

```
users ──< workspace_members >── workspaces
users ──< sessions
workspaces ──< documents
workspaces ──< collections ──< collection_documents >── documents
documents ──< document_chunks
workspaces ──< conversations ──< messages
messages ──< citations >── document_chunks
workspaces ──< evaluation_runs ──< evaluation_results
* ──< audit_logs
* ──< retrieval_events
```

Cardinality, indexes, and constraints are intentionally not specified here —
those are implementation decisions to be made (and documented, likely via an
ADR for anything non-obvious, e.g. pgvector index type/parameters) when the
schema is actually built.

## Chunk metadata (from `docs/REQUIREMENTS.md`)

`document_chunks` rows are expected to carry at least:

- `document_id`
- `page`
- `section`
- `chunk_index`
- `content`
- embedding vector (pgvector column)
- embedding model/version metadata (see
  [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) §"Embeddings")

## Related documents

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — where `models/` and
  `repositories/` live in the module layout.
- [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) — how chunks, retrieval events, and
  citations are produced.
- [`docs/EVALUATION.md`](EVALUATION.md) — how `evaluation_runs` /
  `evaluation_results` are used.
- [`docs/DECISIONS/0002-postgresql-pgvector-initial-vector-store.md`](DECISIONS/0002-postgresql-pgvector-initial-vector-store.md)
  — why pgvector rather than a dedicated vector database.
- [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  — why `sessions` is a core entity.
