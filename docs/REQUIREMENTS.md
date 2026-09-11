# Requirements

**Status:** PROPOSED — target functional scope. Nothing in this document is
implemented yet; see [`PROJECT_STATE.md`](../PROJECT_STATE.md) for the
current, real status of each area.

This document enumerates the target functional scope. It intentionally does
not prescribe UI/API detail — see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md),
[`docs/API_CONTRACT.md`](API_CONTRACT.md), and
[`docs/DATA_MODEL.md`](DATA_MODEL.md) for those.

## Authentication

- Registration, login, logout.
- Secure password hashing (never plaintext or reversible storage).
- Session/token-based auth with a refresh mechanism.
- Profile/settings management.
- Session/device management (view and revoke active sessions).
- Input validation on all auth endpoints.
- Rate limiting / brute-force protection on login and registration.

## Workspaces

- Create, rename, delete, and switch between workspaces.
- Workspace-level settings.
- Member management with roles: `OWNER`, `ADMIN`, `MEMBER`, `VIEWER`.
- **Strict workspace isolation** — no cross-workspace data access, enforced
  server-side and covered by tests (see [`docs/SECURITY.md`](SECURITY.md)).

## Documents

- Supported formats: PDF, DOCX, TXT, Markdown, CSV.
- Upload, list, search, filter, sort, rename, delete.
- Re-index and retry for failed processing.
- Download original file.
- Metadata display and processing-status visibility.

## Ingestion pipeline

State machine per document:

```
UPLOADED → PROCESSING → PARSED → CLEANED → CHUNKED → EMBEDDED → INDEXED → READY / FAILED
```

- Structure-aware parsing: headings, sections, paragraphs, pages, tables
  where practical, and metadata extraction.
- Chunk metadata concepts: `document_id`, `page`, `section`, `chunk_index`,
  `content`.
- Chunking strategies: fixed-size, recursive, and structure-aware, with
  configurable size, overlap, and minimum/maximum limits, and a way to
  measurably compare strategies (see [`docs/EVALUATION.md`](EVALUATION.md)).
- Embeddings: provider abstraction, batching, retries, rate-limit handling,
  and tracking of model/version/dimension per embedding.

## Retrieval

- Dense (vector) retrieval.
- BM25 / lexical retrieval.
- Hybrid retrieval combining both.
- Result fusion (e.g., Reciprocal Rank Fusion).
- Reranking of fused results.
- Metadata filtering (e.g., by collection, document, date).

## Query handling

- Query understanding.
- Conversational query handling (using prior turns for context).
- Query rewriting, while preserving the original user query for
  transparency/debugging.

## Generation

- Context builder: evidence ranking, duplicate removal, token-budget
  management.
- Grounded generation — answers must be derived from retrieved evidence.
- Citation generation tied to specific evidence chunks.

## Citations

- Each citation references document, page, and section.
- Citations are clickable and link to the exact context in a document
  viewer.

## Chat

- Persistent conversations and messages.
- Rename, delete, search conversations.
- Regenerate/retry a response.
- User feedback on responses.
- Follow-up questions use conversational context.

## Search

- A separate search mode (distinct from chat) showing snippets, evidence,
  ranking/scores, retrieval method used, and source information.

## Voice

- Speech-to-text (STT) input, text-to-speech (TTS) output.
- Transcript display and audio playback.
- Conversation-aware voice (uses the same context as text chat).
- Interruption handling and streaming where the provider supports it.
- Citations remain visible while audio is playing.
- **Voice is integrated into Chat, not a separate application surface**, and
  is built only after text RAG works end-to-end.

## Collections

- Logical grouping of documents.
- Filtering and retrieval scoped to a collection.

## Observability

- Request IDs propagated through the pipeline.
- Latency tracking per stage: retrieval, embedding, reranking, generation.
- Token usage tracking.
- Error and ingestion-failure tracking.
- Retrieval event logging (what was retrieved, how it was ranked).

## Evaluation

See [`docs/EVALUATION.md`](EVALUATION.md) for full detail. Summary:

- Retrieval metrics: Recall@K, Precision@K, MRR, nDCG, Hit Rate.
- Generation metrics: faithfulness, answer relevance, context relevance,
  citation correctness, citation completeness.
- Comparison across Dense / BM25 / Hybrid / Hybrid+Reranker configurations.
- Experiment configuration tracking (embedding model, chunking strategy,
  chunk size, retrieval method, top-K, reranker, LLM, results).
- **No evaluation numbers exist yet and none may be fabricated** — see
  `AGENTS.md` §10.

## Security

See [`docs/SECURITY.md`](SECURITY.md) for the full model. Summary of
requirements: authentication, authorization, workspace isolation, upload
validation (MIME/extension/size), path-traversal protection, safe storage,
malformed-document handling, resource/time limits, rate limiting, secret
management, prompt-injection defense, audit logging, and testing against
malicious documents and cross-workspace access attempts.
