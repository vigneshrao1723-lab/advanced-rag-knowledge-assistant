# Data Model

**Status:** PARTIALLY IMPLEMENTED — `users`, `workspaces`,
`workspace_members`, `sessions` (migration `0002`), and
`password_reset_tokens`/`audit_logs` (migration `0003`) exist as real
tables (GitHub Issue #2 — Authentication & Workspaces). `documents` and
`document_chunks` (migration `0004`, extended by migration `0005`) also
exist as real tables (GitHub Issue #3, Slice 3.1); as of Slice 3.7,
`documents` rows are populated end-to-end through the full documented
ingestion lifecycle (`UPLOADED → ... → READY`), and `document_chunks`
rows — including their `pgvector` embedding column, populated by
`LocalHashingEmbeddingProvider` — are persisted by that same pipeline.
`conversations`/`messages`/`citations`/`retrieval_events` (migration
`0006`, GitHub Issue #4 Slice 4.1) also exist as real tables, schema
only — no retrieval/generation code reads or writes them yet. Every
other entity below remains PROPOSED. This document
records the intended core entities so future implementation stays
consistent; entities not marked implemented below are not evidence that
they exist. See [`PROJECT_STATE.md`](../PROJECT_STATE.md) for current
status.

## Core entities

| Entity | Purpose | Status |
|---|---|---|
| `users` | Account identity and credentials | IMPLEMENTED |
| `workspaces` | Isolation boundary for a user or team's data | IMPLEMENTED |
| `workspace_members` | Membership + role (`OWNER`/`ADMIN`/`MEMBER`/`VIEWER`) linking users to workspaces | IMPLEMENTED |
| `sessions` | Server-tracked login/device session backing refresh-token issuance, listing, and revocation (see [ADR 0003](DECISIONS/0003-authentication-session-architecture.md)) | IMPLEMENTED |
| `password_reset_tokens` | Hashed, expiring, single-use password-reset tokens (raw value never persisted — see [ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md) and `docs/SECURITY.md`) | IMPLEMENTED |
| `documents` | Uploaded source files and their processing status | IMPLEMENTED (migration `0004`; the full ingestion pipeline — upload through embedding/indexing, Slices 3.3–3.7 — populates real rows all the way to `READY`) |
| `document_chunks` | Chunked units of a document, used for retrieval once Issue #4 exists | IMPLEMENTED (migration `0004` + `0005`; populated by Slice 3.6's chunk-persistence step and Slice 3.7's embedding step, including the `pgvector` `embedding` column) |
| `collections` | Logical grouping of documents within a workspace | PROPOSED |
| `collection_documents` | Many-to-many link between collections and documents | PROPOSED |
| `conversations` | A chat session within a workspace | IMPLEMENTED (migration `0006`, GitHub Issue #4 Slice 4.1 — schema only, no retrieval/generation code reads/writes it yet) |
| `messages` | Individual messages within a conversation (user + assistant) | IMPLEMENTED (migration `0006`; native `message_role` enum, `USER`/`ASSISTANT`) |
| `citations` | Links between a generated answer/message and the evidence (chunks) it cites | IMPLEMENTED (migration `0006`; denormalizes `document_id`/`page`/`section` from the cited chunk at write time) |
| `retrieval_events` | Record of a retrieval operation (query, method, results, scores) for observability/evaluation | IMPLEMENTED (migration `0006`; `results` is `JSONB`, `rewritten_query_text` kept separate from `query_text` so the original query is always preserved) |
| `evaluation_runs` | A configured evaluation experiment (embedding model, chunking strategy, retrieval method, etc.) | PROPOSED |
| `evaluation_results` | Computed metrics for an `evaluation_run` | PROPOSED |
| `audit_logs` | Security-relevant action log (see [`docs/SECURITY.md`](SECURITY.md)) | IMPLEMENTED (auth/workspace event types; document-related events land with Issue #3) |

## Potential entities (subject to architectural validation)

These are plausible additions identified during design but not yet
committed to — each needs validation against real implementation needs
before being added to the core list above:

- ~~`document_processing_jobs`~~ — **evaluated during Issue #3, Slice
  3.6 and confirmed not needed.** The ingestion pipeline (upload →
  extraction → cleaning → chunking) now exists end-to-end, and the
  existing `documents.status` field plus the client-triggered,
  idempotent-on-retry `POST .../documents/{document_id}/process`
  endpoint together already provide everything this project's
  synchronous, single-process architecture uses: resumability (a
  document at any non-terminal status can be safely reprocessed),
  retry after `FAILED`, and observability (via the existing
  `AuditEvent.DOCUMENT_*` events). A separate durable job-tracking table
  would duplicate that state without adding a capability this
  architecture actually exercises. This entity is not removed from this
  list — a future slice that introduces genuinely asynchronous/queued
  processing (which this project deliberately does not have — see
  [ADR 0001](DECISIONS/0001-modular-monolith-over-microservices.md) on
  the modular-monolith, no-premature-infrastructure rule) could still
  revisit this decision.
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
- `embedding` (pgvector `Vector(384)`, nullable) — **IMPLEMENTED**
  (migration `0005`, GitHub Issue #3 Slice 3.7): populated once a
  document reaches `EMBEDDED`. 384 is `LocalHashingEmbeddingProvider`'s
  dimension (`backend/app/ingestion/embedding.py`) — chosen to match
  common small real embedding models (e.g. all-MiniLM-L6-v2/BGE-small)
  so a future swap to one of those needs no further migration; a
  different-dimension model would. An HNSW index (`vector_cosine_ops`)
  covers this column — chosen over IVFFlat since it needs no separate
  training/list-count step and stays correct under this project's
  incremental (not bulk-loaded) ingestion.
- `embedding_model`/`embedding_dimension` (Text/Integer, nullable) —
  **IMPLEMENTED** (migration `0005`), per-row provenance (see
  [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) §"Embeddings" — "tracking of
  which model/version/dimension produced each embedding — this matters
  because changing the embedding model invalidates prior vectors"): a
  future model swap can identify exactly which rows an old model
  produced, rather than guessing from the column's fixed width alone.

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
