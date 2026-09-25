# RAG Design

**Status:** PARTIALLY IMPLEMENTED — describes the intended retrieval-
augmented generation pipeline. The ingestion pipeline (parsing through
embeddings/indexing, GitHub Issue #3) is implemented; retrieval,
reranking, generation, and citations (Issue #4 onward) are not yet. See
[`PROJECT_STATE.md`](../PROJECT_STATE.md) for exact status.

## Core flow

```
USER
 ├── TEXT
 └── VOICE → STT
          ↓
   Query Understanding
          ↓
   Query Processing / Rewrite
          ↓
   Dense Retrieval + BM25
          ↓
   Result Fusion
          ↓
     Reranker
          ↓
   Metadata Filtering
          ↓
    Top-K Evidence
          ↓
    Context Builder
          ↓
        LLM
          ↓
 Answer + Citations
 ├── TEXT
 └── VOICE → TTS
```

**Build order: text RAG first.** Voice (STT/TTS) is integrated into Chat
once the text pipeline above works end-to-end — it is not a separate
application or a parallel track.

## Ingestion pipeline

State machine per document:

```
UPLOADED → PROCESSING → PARSED → CLEANED → CHUNKED → EMBEDDED → INDEXED → READY / FAILED
```

- **Parsing** is structure-aware: headings, sections, paragraphs, pages, and
  tables (where practical) are extracted along with metadata, not just raw
  text.
- **Chunk metadata** carries at minimum: `document_id`, `page`, `section`,
  `chunk_index`, `content`.
- **Chunking strategies**: fixed-size, recursive, and structure-aware, each
  with configurable chunk size, overlap, and minimum/maximum limits.
  Strategies are meant to be measurably compared (see
  [`docs/EVALUATION.md`](EVALUATION.md)) rather than chosen by intuition
  alone.
- **Embeddings** go through a provider abstraction (`EmbeddingProvider`)
  with batching, retry handling, rate-limit awareness, and tracking of
  which model/version/dimension produced each embedding — this matters
  because changing the embedding model invalidates prior vectors.
  **IMPLEMENTED** (GitHub Issue #3, Slice 3.7,
  `backend/app/ingestion/embedding.py`): the shipped implementation,
  `LocalHashingEmbeddingProvider`, is deterministic and offline (no
  commercial vendor selected yet — see "Provider abstractions" below),
  so the whole ingestion pipeline is testable/demoable without a paid
  external API.

## Retrieval

**IMPLEMENTED** (GitHub Issue #4, Slice 4.2, `backend/app/retrieval/`) —
not yet wired to any API endpoint (a later Issue #4 slice).

- **Dense retrieval**: vector similarity search over `document_chunks`
  embeddings (pgvector) — `dense.py`'s `dense_search()`, using
  `Vector.cosine_distance()` backed by the HNSW index (migration `0005`).
- **BM25 / lexical retrieval**: keyword-based search, complementary to
  dense retrieval for exact-term matches (IDs, names, acronyms) that
  embeddings can miss — `lexical.py`'s `lexical_search()`, Postgres
  full-text search (`to_tsvector`/`plainto_tsquery`/`ts_rank_cd`) backed
  by a GIN functional index (migration `0007`); no second search engine,
  per ADR 0002's own stated consequence.
- **Hybrid retrieval**: combines dense + BM25 results —
  `service.py`'s `hybrid_search()`, the single orchestrating entry point.
- **Result fusion**: merges ranked lists from multiple retrieval methods
  via Reciprocal Rank Fusion (RRF) — `fusion.py`'s
  `reciprocal_rank_fusion()` (`k=60`, deduplicates by `chunk_id`).
- **Reranking**: a `Reranker` provider re-scores fused candidates against
  the query for higher precision at the top of the list —
  `reranker.py`'s `Reranker` protocol + `LexicalOverlapReranker`
  (deterministic, offline Jaccard token-overlap scoring; no commercial
  vendor selected yet, matching `EmbeddingProvider`'s own precedent so
  the pipeline stays testable/demoable without a paid API).
- **Metadata filtering**: narrows results by document (`document_id`,
  supported today) — collection-based filtering is deferred until the
  `collections` entity exists (still PROPOSED).
- Every query is workspace-scoped at the SQL level and requires the
  owning document be `READY`, so a document still mid-ingestion-pipeline
  never surfaces partial results. `hybrid_search()` records a
  `RetrievalEvent` row per call (query, method, ranked results, latency)
  for observability/evaluation.

## Query handling

- **Query understanding**: interpret intent, not just raw text matching.
- **Conversational query handling**: use prior conversation turns as
  context for follow-up questions.
- **Query rewriting**: transform the query for better retrieval (e.g.,
  resolving pronouns from context) while **preserving the original query**
  so users and evaluators can see what was actually asked vs. what was
  searched.

## Generation

- **Context builder**: assembles the top-K evidence into a prompt context —
  ranking evidence, removing duplicates, and respecting a token budget.
- **Grounded generation**: the LLM is instructed to answer from the
  provided evidence, not from unconstrained prior knowledge.
- **Citation generation**: each claim in the answer is tied back to the
  specific evidence chunk(s) that support it.

Retrieved content is untrusted input to this stage — see
[`docs/SECURITY.md`](SECURITY.md) §"Prompt injection defense" for the
non-negotiable rule that instruction-like text inside a retrieved chunk must
never override system instructions.

## Citations

- Each citation references document, page, and section.
- Citations are clickable in the UI and link to the exact location in a
  document viewer.

## Collections

Documents can be grouped into collections; retrieval and filtering can be
scoped to a collection (in addition to the always-enforced workspace scope).

## Provider abstractions

The pipeline depends on these interfaces (see
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §"Provider abstractions"), none
of which have a selected commercial implementation yet:

- `EmbeddingProvider`
- `Reranker`
- `LLMProvider`
- `SpeechToTextProvider`
- `TextToSpeechProvider`
- `StorageProvider`

## Observability

Per pipeline run, the design calls for tracking: request IDs, retrieval
latency, embedding latency, reranker latency, generation latency, token
usage, errors, ingestion failures, and retrieval events (query, method,
ranked results, scores) — feeding both debugging and
[`docs/EVALUATION.md`](EVALUATION.md).

## Related documents

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — module layout implementing
  this design (`ingestion/`, `retrieval/`, `generation/`, `voice/`).
- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — entities this pipeline reads and
  writes (`document_chunks`, `retrieval_events`, `citations`).
- [`docs/EVALUATION.md`](EVALUATION.md) — how pipeline quality is measured.
- [`docs/SECURITY.md`](SECURITY.md) — untrusted-content handling rules.
