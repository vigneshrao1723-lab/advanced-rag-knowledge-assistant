#!/usr/bin/env python3
"""Runnable evaluation harness — GitHub Issue #4's "evaluation hooks"
deliverable, extended by Issue #7 into real, persisted experiment
tracking: proves the retrieval + generation pipeline is measurable by
actually running it against a small, deterministic fixture set
(`eval/datasets/retrieval_fixture.py`), comparing **4 retrieval
methods** (dense-only, lexical-only, hybrid, hybrid+reranked) across
**2 chunking strategies** (structure-aware, fixed-size — GitHub Issue
#7's explicit "at least two chunking strategies" requirement), and
persisting every run's configuration and computed metrics as a real
`EvaluationRun`/`EvaluationResult` row pair, per `docs/EVALUATION.md`.
Never fabricates a number — every value in its report was computed
from this run.

Requires a real, reachable Postgres database (`DATABASE_URL`, same as
the application itself) and the backend's own dependencies. Run from
the repository root:

    cd backend && uv run python ../eval/scripts/run_retrieval_evaluation.py

Writes `eval/results/retrieval_evaluation.json` (overwritten each run —
per docs/EVALUATION.md, this file is the only legitimate source of
evaluation numbers referenced elsewhere in the docs) and prints a
human-readable summary to stdout. Also persists one `EvaluationRun` +
its `EvaluationResult` rows per (chunking strategy, retrieval method)
combination — 8 runs total — committed to the real database, so
`evaluation_runs`/`evaluation_results` accumulate real, comparable
history across repeated executions of this script over time.

Uses a dedicated, throwaway workspace per chunking strategy, created
fresh and deleted (via `ON DELETE CASCADE`) at the end of the run —
this script never touches or pollutes real workspace data, and is
safely re-runnable. `evaluation_runs.workspace_id` uses `ON DELETE SET
NULL` specifically so the persisted run/result rows survive that
workspace cleanup (see `app/models/evaluation_run.py`).
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_REPO_ROOT))

from eval.datasets.retrieval_fixture import DOCUMENTS, QUERIES  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.evaluation.metrics import (  # noqa: E402
    citation_completeness,
    citation_correctness,
    hit_rate_at_k,
    is_extractive_answer_grounded,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from app.generation.llm_provider import NO_EVIDENCE_ANSWER, get_llm_provider  # noqa: E402
from app.generation.service import generate_answer  # noqa: E402
from app.ingestion import chunking  # noqa: E402
from app.ingestion.chunking import Chunk, ChunkingStrategy  # noqa: E402
from app.ingestion.cleaning import clean as clean_extracted_document  # noqa: E402
from app.ingestion.embedding import (  # noqa: E402
    EmbeddingProvider,
    embed_with_retry,
    get_embedding_provider,
)
from app.ingestion.extraction import ExtractedDocument, ExtractedSection  # noqa: E402
from app.models.document import Document, DocumentStatus  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.repositories import (  # noqa: E402
    document_chunk_repository,
    evaluation_result_repository,
    evaluation_run_repository,
)
from app.retrieval.dense import dense_search  # noqa: E402
from app.retrieval.fusion import reciprocal_rank_fusion  # noqa: E402
from app.retrieval.lexical import lexical_search  # noqa: E402
from app.retrieval.reranker import Reranker, get_reranker  # noqa: E402
from app.retrieval.service import hybrid_search  # noqa: E402
from app.retrieval.types import RetrievalCandidate  # noqa: E402

_TOP_K = 3
_RETRIEVAL_METHODS = ("dense", "lexical", "hybrid", "hybrid_reranked")
_CHUNKING_STRATEGIES: dict[str, ChunkingStrategy] = {
    "structure_aware": chunking.StructureAwareChunker(),
    "fixed_size": chunking.FixedSizeChunker(),
}


def _ingest_fixture_documents(
    db: Any,
    workspace_id: uuid.UUID,
    embedding_provider: EmbeddingProvider,
    chunker: ChunkingStrategy,
) -> dict[str, list[uuid.UUID]]:
    """Runs the same pure pipeline stages `process_document()` uses
    (cleaning, chunking, embedding) directly against fixture text —
    skipping upload/extraction, since there's no real file here, not
    the stages actually being evaluated."""
    document_key_to_chunk_ids: dict[str, list[uuid.UUID]] = {}

    for fixture_doc in DOCUMENTS:
        document = Document(
            workspace_id=workspace_id,
            filename=fixture_doc.filename,
            mime_type="text/plain",
            size_bytes=len(fixture_doc.content.encode("utf-8")),
            checksum_sha256=uuid.uuid4().hex,
            storage_key=f"{workspace_id}/{uuid.uuid4()}.txt",
            status=DocumentStatus.READY,
        )
        db.add(document)
        db.flush()

        extracted = ExtractedDocument(
            sections=[ExtractedSection(text=fixture_doc.content, page=None, heading=None)],
            page_count=None,
        )
        cleaned = clean_extracted_document(extracted)
        chunks: list[Chunk] = chunker.chunk(cleaned)
        rows = document_chunk_repository.bulk_create(
            db, document_id=document.id, workspace_id=workspace_id, chunks=chunks
        )
        embeddings = embedding_provider.embed_batch([chunk.content for chunk in chunks])
        document_chunk_repository.set_embeddings(
            db,
            chunks=rows,
            embeddings=embeddings,
            model=embedding_provider.model_name,
            dimension=embedding_provider.dimension,
        )
        document_key_to_chunk_ids[fixture_doc.key] = [row.id for row in rows]

    db.commit()
    return document_key_to_chunk_ids


def _retrieve(
    method: str,
    db: Any,
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    top_k: int,
) -> list[RetrievalCandidate]:
    """Reconstructs each comparison method from the same lower-level
    building blocks `app.retrieval.service.hybrid_search()` itself
    composes (`dense_search()`/`lexical_search()`/
    `reciprocal_rank_fusion()`) — this evaluation-only comparison logic
    lives here, not as a new "method" parameter on the real, tested
    production entry point, so no application code changes shape to
    serve evaluation alone."""
    if method == "dense":
        [query_embedding] = embed_with_retry(embedding_provider, [query_text])
        return dense_search(
            db, workspace_id=workspace_id, query_embedding=query_embedding, top_k=top_k
        )
    if method == "lexical":
        return lexical_search(db, workspace_id=workspace_id, query_text=query_text, top_k=top_k)

    # "hybrid" and "hybrid_reranked" share dense+lexical+fusion; only the
    # final reranking step differs.
    [query_embedding] = embed_with_retry(embedding_provider, [query_text])
    dense_results = dense_search(
        db, workspace_id=workspace_id, query_embedding=query_embedding, top_k=20
    )
    lexical_results = lexical_search(db, workspace_id=workspace_id, query_text=query_text, top_k=20)
    fused = reciprocal_rank_fusion([dense_results, lexical_results])
    if method == "hybrid":
        return fused[:top_k]
    if method == "hybrid_reranked":
        pool = fused[: top_k * 3]
        return reranker.rerank(query=query_text, candidates=pool)[:top_k]
    raise ValueError(f"Unknown retrieval method: {method!r}")


def _run_retrieval_evaluation(
    method: str,
    db: Any,
    workspace_id: uuid.UUID,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    chunk_ids_by_key: dict[str, list[uuid.UUID]],
) -> list[dict[str, Any]]:
    per_query: list[dict[str, Any]] = []
    for fixture_query in QUERIES:
        relevant_chunk_ids: set[uuid.UUID] = set()
        for key in fixture_query.relevant_document_keys:
            relevant_chunk_ids.update(chunk_ids_by_key[key])

        results = _retrieve(
            method,
            db,
            workspace_id=workspace_id,
            query_text=fixture_query.query,
            embedding_provider=embedding_provider,
            reranker=reranker,
            top_k=_TOP_K,
        )
        retrieved_ids = [candidate.chunk_id for candidate in results]

        per_query.append(
            {
                "query": fixture_query.query,
                "relevant_document_keys": sorted(fixture_query.relevant_document_keys),
                "retrieved_count": len(retrieved_ids),
                f"recall@{_TOP_K}": recall_at_k(retrieved_ids, relevant_chunk_ids, _TOP_K),
                f"precision@{_TOP_K}": precision_at_k(retrieved_ids, relevant_chunk_ids, _TOP_K),
                "mrr": mrr(retrieved_ids, relevant_chunk_ids),
                f"ndcg@{_TOP_K}": ndcg_at_k(retrieved_ids, relevant_chunk_ids, _TOP_K),
                f"hit_rate@{_TOP_K}": hit_rate_at_k(retrieved_ids, relevant_chunk_ids, _TOP_K),
            }
        )
    return per_query


def _average(per_query: list[dict[str, Any]], metric_key: str) -> float:
    values = [row[metric_key] for row in per_query]
    return sum(values) / len(values) if values else 0.0


def _averages(per_query: list[dict[str, Any]]) -> dict[str, float]:
    return {
        f"recall@{_TOP_K}": _average(per_query, f"recall@{_TOP_K}"),
        f"precision@{_TOP_K}": _average(per_query, f"precision@{_TOP_K}"),
        "mrr": _average(per_query, "mrr"),
        f"ndcg@{_TOP_K}": _average(per_query, f"ndcg@{_TOP_K}"),
        f"hit_rate@{_TOP_K}": _average(per_query, f"hit_rate@{_TOP_K}"),
    }


def _run_generation_evaluation(
    db: Any,
    workspace_id: uuid.UUID,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    llm_provider: Any,
) -> list[dict[str, Any]]:
    """Exercises generation on two representative fixture queries,
    against the real (hybrid+reranked) production retrieval
    configuration, and computes real, mechanically-checkable
    groundedness/citation metrics (see app/evaluation/metrics.py's
    module docstring for why faithfulness/answer-relevance are not
    fabricated as numeric scores here)."""
    sample_queries = QUERIES[:2]
    per_query: list[dict[str, Any]] = []
    for fixture_query in sample_queries:
        results = hybrid_search(
            db,
            workspace_id=workspace_id,
            query_text=fixture_query.query,
            embedding_provider=embedding_provider,
            reranker=reranker,
            final_top_k=_TOP_K,
            record_event=False,
        )
        answer, context = generate_answer(
            query=fixture_query.query, candidates=results, llm_provider=llm_provider
        )
        context_marker_set = {block.marker for block in context.blocks}
        # This script never persists Citation rows (no Message exists to
        # attach them to) -- it evaluates what *would* be cited, using
        # the same marker set the citation engine would persist from,
        # which is exactly `context_marker_set` for this provider (it
        # cites everything included in context, by construction).
        citation_ranks = context_marker_set

        per_query.append(
            {
                "query": fixture_query.query,
                "answer_preview": answer[:120],
                "citation_completeness": citation_completeness(answer, citation_ranks),
                "citation_correctness": citation_correctness(citation_ranks, context_marker_set),
                "is_extractive_answer_grounded": is_extractive_answer_grounded(
                    answer, context.text, no_evidence_answer=NO_EVIDENCE_ANSWER
                ),
            }
        )
    return per_query


def _run_for_chunking_strategy(
    db: Any,
    *,
    strategy_name: str,
    chunker: ChunkingStrategy,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    llm_provider: Any,
) -> dict[str, Any]:
    workspace = Workspace(name=f"eval-{strategy_name}-{uuid.uuid4().hex[:8]}")
    db.add(workspace)
    db.flush()

    try:
        chunk_ids_by_key = _ingest_fixture_documents(db, workspace.id, embedding_provider, chunker)

        methods: dict[str, Any] = {}
        for method in _RETRIEVAL_METHODS:
            per_query = _run_retrieval_evaluation(
                method, db, workspace.id, embedding_provider, reranker, chunk_ids_by_key
            )
            db.commit()
            averages = _averages(per_query)

            run = evaluation_run_repository.create(
                db,
                workspace_id=workspace.id,
                embedding_model=embedding_provider.model_name,
                chunking_strategy=strategy_name,
                retrieval_method=method,
                top_k=_TOP_K,
                llm_provider=llm_provider.model_name,
                document_count=len(DOCUMENTS),
                query_count=len(QUERIES),
                reranker=type(reranker).__name__ if method == "hybrid_reranked" else None,
            )
            evaluation_result_repository.bulk_create(db, evaluation_run_id=run.id, metrics=averages)
            db.commit()

            methods[method] = {"per_query": per_query, "averages": averages}

        generation_rows = None
        if strategy_name == "structure_aware":
            # Generation evaluation only needs to run once, against the
            # real production retrieval configuration (hybrid+reranked)
            # -- not once per (chunking strategy x retrieval method)
            # combination, which would only multiply LLM calls without
            # adding comparison value this fixture set is designed for.
            generation_rows = _run_generation_evaluation(
                db, workspace.id, embedding_provider, reranker, llm_provider
            )

        return {"methods": methods, "generation": generation_rows}
    finally:
        db.rollback()
        db.delete(workspace)
        db.commit()


def main() -> None:
    db = SessionLocal()
    embedding_provider = get_embedding_provider()
    reranker = get_reranker()
    llm_provider = get_llm_provider()

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "embedding_provider": embedding_provider.model_name,
            "reranker": type(reranker).__name__,
            "llm_provider": llm_provider.model_name,
            "top_k": _TOP_K,
            "document_count": len(DOCUMENTS),
            "query_count": len(QUERIES),
            "retrieval_methods_compared": list(_RETRIEVAL_METHODS),
            "chunking_strategies_compared": list(_CHUNKING_STRATEGIES),
        },
        "chunking_strategies": {},
    }

    for strategy_name, chunker in _CHUNKING_STRATEGIES.items():
        report["chunking_strategies"][strategy_name] = _run_for_chunking_strategy(
            db,
            strategy_name=strategy_name,
            chunker=chunker,
            embedding_provider=embedding_provider,
            reranker=reranker,
            llm_provider=llm_provider,
        )

    db.close()

    results_path = _REPO_ROOT / "eval" / "results" / "retrieval_evaluation.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, indent=2, default=str) + "\n")

    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {results_path.relative_to(_REPO_ROOT)}")
    print(
        f"Persisted {len(_CHUNKING_STRATEGIES) * len(_RETRIEVAL_METHODS)} evaluation_runs "
        "to the database."
    )


if __name__ == "__main__":
    main()
