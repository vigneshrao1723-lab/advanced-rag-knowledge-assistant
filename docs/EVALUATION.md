# Evaluation

**Status:** PROPOSED — describes the intended evaluation methodology. **No
evaluation has been run. No numbers, scores, or benchmark results exist in
this repository, and none may be fabricated** — see `AGENTS.md` §10.

## Purpose

Retrieval and generation quality must be measurable, not asserted. This
document defines the metrics and comparisons the system is designed to
support once an ingestion + retrieval + generation pipeline actually exists
to evaluate.

## Retrieval metrics

- **Recall@K** — fraction of relevant chunks found within the top-K results.
- **Precision@K** — fraction of the top-K results that are relevant.
- **MRR** (Mean Reciprocal Rank) — position of the first relevant result.
- **nDCG** (normalized Discounted Cumulative Gain) — rank-aware relevance
  quality.
- **Hit Rate** — fraction of queries with at least one relevant result in
  the top-K.

## Generation metrics

- **Faithfulness** — does the answer only claim what's supported by the
  retrieved evidence?
- **Answer relevance** — does the answer actually address the question?
- **Context relevance** — was the retrieved context relevant to the
  question?
- **Citation correctness** — do citations point to evidence that actually
  supports the claim they're attached to?
- **Citation completeness** — are all supportable claims in the answer
  actually cited?

## Configuration comparison

The evaluation harness is intended to compare, on the same query set:

- Dense retrieval only
- BM25 only
- Hybrid (dense + BM25 + fusion)
- Hybrid + Reranker

Independently of retrieval-method comparisons, **chunking strategy
comparisons are also part of this framework**: the same query set and
retrieval configuration can be re-run against corpora chunked with
different strategies (fixed-size, recursive, structure-aware) and
parameters (size, overlap) to measure their effect on the retrieval
metrics above. Chunking strategy is already tracked per run — see
"Experiment tracking" below.

## Experiment tracking

Each evaluation run should record the configuration that produced its
results, so results are reproducible and comparable:

- Embedding model
- Chunking strategy and chunk size
- Retrieval method (dense / BM25 / hybrid / hybrid+rerank)
- Top-K
- Reranker (if used)
- LLM used for generation
- The resulting metric values

This maps to the `evaluation_runs` / `evaluation_results` entities in
[`docs/DATA_MODEL.md`](DATA_MODEL.md).

## Rule: never fabricate results

This is restated here deliberately, because evaluation is the area most
tempting to "fill in" with plausible-looking numbers:

- No retrieval or generation metric may be written into any document, PR
  description, or commit message unless it was actually computed by running
  the evaluation harness against real data in this repository.
- `eval/results/` (once it exists) is the only legitimate source of
  evaluation numbers referenced elsewhere in the docs.
- If asked to report evaluation results before the harness and dataset
  exist, the correct answer is "not yet measured," not an invented number.

## Related documents

- [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) — the pipeline being evaluated.
- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — `evaluation_runs`,
  `evaluation_results` entities.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — `backend/app/evaluation/`
  module and `eval/` directory (both PLANNED).
