# Data Model

**Status:** PARTIALLY IMPLEMENTED — `users`, `workspaces`,
`workspace_members`, and `sessions` exist as real tables (migration `0002`,
GitHub Issue #2 — Authentication & Workspaces); every other entity below
remains PROPOSED. This document records the intended core entities so
future implementation stays consistent; entities not marked implemented
below are not evidence that they exist. See
[`PROJECT_STATE.md`](../PROJECT_STATE.md) for current status.

## Core entities

| Entity | Purpose | Status |
|---|---|---|
| `users` | Account identity and credentials | IMPLEMENTED |
| `workspaces` | Isolation boundary for a user or team's data | IMPLEMENTED |
| `workspace_members` | Membership + role (`OWNER`/`ADMIN`/`MEMBER`/`VIEWER`) linking users to workspaces | IMPLEMENTED |
| `sessions` | Server-tracked login/device session backing refresh-token issuance, listing, and revocation (see [ADR 0003](DECISIONS/0003-authentication-session-architecture.md)) | IMPLEMENTED |
| `documents` | Uploaded source files and their processing status | PROPOSED |
| `document_chunks` | Chunked, embedded units of a document, used for retrieval | PROPOSED |
| `collections` | Logical grouping of documents within a workspace | PROPOSED |
| `collection_documents` | Many-to-many link between collections and documents | PROPOSED |
| `conversations` | A chat session within a workspace | PROPOSED |
| `messages` | Individual messages within a conversation (user + assistant) | PROPOSED |
| `citations` | Links between a generated answer/message and the evidence (chunks) it cites | PROPOSED |
| `retrieval_events` | Record of a retrieval operation (query, method, results, scores) for observability/evaluation | PROPOSED |
| `evaluation_runs` | A configured evaluation experiment (embedding model, chunking strategy, retrieval method, etc.) | PROPOSED |
| `evaluation_results` | Computed metrics for an `evaluation_run` | PROPOSED |
| `audit_logs` | Security-relevant action log (see [`docs/SECURITY.md`](SECURITY.md)) | PROPOSED |

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
