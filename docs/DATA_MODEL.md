# Data Model

**Status:** PARTIALLY IMPLEMENTED — `users`, `workspaces`,
`workspace_members`, `sessions` (migration `0002`), and
`password_reset_tokens`/`audit_logs` (migration `0003`) exist as real
tables (GitHub Issue #2 — Authentication & Workspaces). `documents` and
`document_chunks` (migration `0004`) also exist as real tables, but as
**schema only** (GitHub Issue #3, Slice 3.1) — no upload API, storage,
extraction, chunking, or embedding code exists yet, and
`document_chunks` deliberately has no embedding column (see below). Every
other entity below remains PROPOSED. This document records the intended
core entities so future implementation stays consistent; entities not
marked implemented below are not evidence that they exist. See
[`PROJECT_STATE.md`](../PROJECT_STATE.md) for current status.

## Core entities

| Entity | Purpose | Status |
|---|---|---|
| `users` | Account identity and credentials | IMPLEMENTED |
| `workspaces` | Isolation boundary for a user or team's data | IMPLEMENTED |
| `workspace_members` | Membership + role (`OWNER`/`ADMIN`/`MEMBER`/`VIEWER`) linking users to workspaces | IMPLEMENTED |
| `sessions` | Server-tracked login/device session backing refresh-token issuance, listing, and revocation (see [ADR 0003](DECISIONS/0003-authentication-session-architecture.md)) | IMPLEMENTED |
| `password_reset_tokens` | Hashed, expiring, single-use password-reset tokens (raw value never persisted — see [ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md) and `docs/SECURITY.md`) | IMPLEMENTED |
| `documents` | Uploaded source files and their processing status | IMPLEMENTED (schema only — migration `0004`; upload/storage/processing code lands in later Issue #3 slices) |
| `document_chunks` | Chunked units of a document, used for retrieval once Issue #4 exists | IMPLEMENTED (schema only — migration `0004`; **no embedding column yet**, see below) |
| `collections` | Logical grouping of documents within a workspace | PROPOSED |
| `collection_documents` | Many-to-many link between collections and documents | PROPOSED |
| `conversations` | A chat session within a workspace | PROPOSED |
| `messages` | Individual messages within a conversation (user + assistant) | PROPOSED |
| `citations` | Links between a generated answer/message and the evidence (chunks) it cites | PROPOSED |
| `retrieval_events` | Record of a retrieval operation (query, method, results, scores) for observability/evaluation | PROPOSED |
| `evaluation_runs` | A configured evaluation experiment (embedding model, chunking strategy, retrieval method, etc.) | PROPOSED |
| `evaluation_results` | Computed metrics for an `evaluation_run` | PROPOSED |
| `audit_logs` | Security-relevant action log (see [`docs/SECURITY.md`](SECURITY.md)) | IMPLEMENTED (auth/workspace event types; document-related events land with Issue #3) |

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
users ──< password_reset_tokens
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

- `document_id` — IMPLEMENTED (migration `0004`)
- `workspace_id` — IMPLEMENTED (migration `0004`; denormalized from
  `document_id` for workspace-scoped query safety, not in the original
  list above, added during Slice 3.1's schema design)
- `page` — IMPLEMENTED (migration `0004`)
- `section` — IMPLEMENTED (migration `0004`)
- `chunk_index` — IMPLEMENTED (migration `0004`)
- `content` — IMPLEMENTED (migration `0004`)
- embedding vector (pgvector column) — **PROPOSED, deliberately not yet
  added.** Choosing a `VECTOR(n)` column now would lock the schema to an
  embedding model/dimension before the `EmbeddingProvider` abstraction is
  designed; adding it is planned as a small additive migration in a later
  Issue #3 slice, once that choice is actually made.
- embedding model/version metadata — PROPOSED, same reason as above (see
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
