# 0007. Local, deterministic providers for embedding, reranking, and generation (no commercial vendor yet)

**Status:** Accepted
**Date:** 2026-09-25

## Context

GitHub Issue #4's Definition of Done requires "Vendor ADR(s) for LLM/
embedding/reranker are merged." Three provider-abstraction seams exist
in the pipeline — `EmbeddingProvider` (Issue #3, Slice 3.7),
`Reranker` (Issue #4, Slice 4.2), and `LLMProvider` (Issue #4,
Slice 4.3) — and each has exactly one implementation today, in every
case a deterministic, offline, dependency-free local implementation:
`LocalHashingEmbeddingProvider`, `LexicalOverlapReranker`, and
`LocalGroundedExtractiveProvider`. This ADR records that as a real,
deliberate decision for this phase of the project, not an oversight —
the alternative (a real hosted LLM/embedding/reranker vendor) was
considered and explicitly deferred, for the reasons below.

The project's own execution constraints matter here directly: the
ingestion, retrieval, and generation pipeline must be fully buildable,
testable (including in CI, which has no network egress to a paid API
and no API key provisioned), and demoable without depending on a paid
external service or a provisioned secret. A commercial vendor choice
also has real cost, quota, latency-variance, and data-handling
implications (sending workspace document content to a third party) that
deserve a deliberate evaluation, not a default reached for convenience
mid-slice.

## Decision

**For this phase of the project, `EmbeddingProvider`, `Reranker`, and
`LLMProvider` all use local, deterministic, offline implementations —
no commercial LLM/embedding/reranker vendor is selected.** Each
provider's shape is deliberately generic (a `Protocol` plus a
settings-driven factory, e.g. `get_embedding_provider()`/
`get_reranker()`/`get_llm_provider()`) so a real hosted provider can be
added later as an additive change (implement the protocol, add a branch
to the factory) without touching any caller — this ADR does not close
that door, it documents why it isn't taken yet.

- `EmbeddingProvider` → `LocalHashingEmbeddingProvider`
  (`backend/app/ingestion/embedding.py`): a deterministic hashed-bag-of-
  words vector (the "hashing trick"), 384 dimensions, L2-normalized.
- `Reranker` → `LexicalOverlapReranker` (`backend/app/retrieval/reranker.py`):
  deterministic Jaccard token-overlap scoring between the query and each
  candidate.
- `LLMProvider` → `LocalGroundedExtractiveProvider`
  (`backend/app/generation/llm_provider.py`): deterministic extractive
  "generation" — it returns the ranked, citation-marked evidence itself
  rather than paraphrasing it, which is grounded by construction (it
  cannot state anything the evidence doesn't already contain) and immune
  to prompt injection by construction (it never interprets retrieved
  content as instructions, only as text to quote).

## Alternatives considered

- **A real hosted LLM provider (e.g. an OpenAI/Anthropic-compatible
  chat completions API) for `LLMProvider`** — rejected for this phase:
  requires provisioning and securing a paid API key (this project has
  no such secret configured, and CI has no network egress to reach one
  even if it did), introduces real per-call cost and latency variance
  that would need to be budgeted and rate-limited deliberately, and
  would make the full pipeline's tests/CI/demo depend on an external
  service being reachable and correctly configured. Not ruled out
  permanently — the `LLMProvider` protocol and `get_llm_provider()`
  factory exist specifically so this can be added later behind a
  config flag, once a vendor and its cost/latency/data-handling
  trade-offs are deliberately evaluated (a natural trigger for a future,
  narrower ADR revisiting just this one provider).
- **A real hosted embedding API (e.g. a commercial text-embedding
  model) for `EmbeddingProvider`** — rejected for the same reasons; also
  already recorded as a deliberate choice in
  `app/ingestion/embedding.py`'s own module docstring when Slice 3.7
  implemented it — this ADR formalizes that same reasoning for the
  record, per Issue #4's explicit requirement, rather than introducing
  a new decision.
- **A real trained cross-encoder/reranking model for `Reranker`** —
  rejected for this phase: meaningfully better reranking quality than
  Jaccard overlap requires either a hosted API (same cost/dependency
  concerns as above) or a locally-run model (a new, heavier runtime
  dependency — model weights, an inference library, meaningfully more
  memory/CPU — disproportionate to this project's current
  modular-monolith, no-premature-infrastructure stance, ADR 0001).
- **Leaving the Definition-of-Done requirement unmet / skipping this
  ADR** — rejected: the requirement exists precisely so a "no vendor
  chosen yet" state is a recorded, deliberate decision rather than an
  implicit gap nobody signed off on.

## Consequences

- The pipeline is fully self-contained: no paid API key required to
  build, test (including in CI), or demo the complete
  ingest → retrieve → generate → cite flow end-to-end.
- Generation quality is bounded by what extractive quoting of the
  top-ranked evidence can express — there is no paraphrasing,
  summarization across multiple sources into fluent prose, or
  multi-step reasoning. This is an accepted, documented limitation of
  this phase, not a defect to be silently worked around; it is visible
  directly in every generated answer's own shape (quoted, citation-
  marked evidence, not synthesized prose).
- Retrieval/reranking quality is bounded by lexical/hashed signals — no
  semantic reranking beyond what dense cosine similarity (over the
  hashed embeddings) and lexical overlap already provide.
- **What would trigger revisiting this decision**: a demonstrated need
  for fluent, synthesized answers (not just quoted evidence), a
  measured retrieval/reranking quality gap once real evaluation numbers
  exist (`docs/EVALUATION.md`, Issue #4's evaluation-hooks deliverable
  and Issue #7's fuller evaluation harness), or an explicit product
  decision to accept the cost/dependency trade-off of a commercial
  vendor. Any such change should land as its own focused ADR
  (superseding the relevant part of this one), not a silent swap.
