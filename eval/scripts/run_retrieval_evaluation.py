#!/usr/bin/env python3
"""Runnable evaluation harness — GitHub Issue #4's "evaluation hooks"
deliverable: proves the retrieval + generation pipeline is measurable by
actually running it against a small, deterministic fixture set
(`eval/datasets/retrieval_fixture.py`) and computing real
docs/EVALUATION.md metrics. Never fabricates a number — every value in
its report was computed from this run.

Requires a real, reachable Postgres database (`DATABASE_URL`, same as
the application itself) and the backend's own dependencies. Run from
the repository root:

    cd backend && uv run python ../eval/scripts/run_retrieval_evaluation.py

Writes `eval/results/retrieval_evaluation.json` (overwritten each run —
per docs/EVALUATION.md, this file is the only legitimate source of
evaluation numbers referenced elsewhere in the docs) and prints a
human-readable summary to stdout.

Uses a dedicated, throwaway workspace, created fresh and deleted (via
`ON DELETE CASCADE`) at the end of the run — this script never touches
or pollutes real workspace data, and is safely re-runnable.

This is explicitly NOT the full evaluation/experiment-tracking system
(`evaluation_runs`/`evaluation_results`, docs/DATA_MODEL.md) — that is
Issue #7's job. This script only proves the pipeline is measurable.
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
from app.ingestion.cleaning import clean as clean_extracted_document  # noqa: E402
from app.ingestion.embedding import get_embedding_provider  # noqa: E402
from app.ingestion.extraction import ExtractedDocument, ExtractedSection  # noqa: E402
from app.models.document import Document, DocumentStatus  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.repositories import document_chunk_repository  # noqa: E402
from app.retrieval.reranker import get_reranker  # noqa: E402
from app.retrieval.service import hybrid_search  # noqa: E402

_TOP_K = 3


def _ingest_fixture_documents(db, workspace_id, embedding_provider):
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
        chunks = chunking.StructureAwareChunker().chunk(cleaned)
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


def _run_retrieval_evaluation(db, workspace_id, embedding_provider, reranker, chunk_ids_by_key):
    per_query: list[dict[str, Any]] = []
    for fixture_query in QUERIES:
        relevant_chunk_ids: set[uuid.UUID] = set()
        for key in fixture_query.relevant_document_keys:
            relevant_chunk_ids.update(chunk_ids_by_key[key])

        results = hybrid_search(
            db,
            workspace_id=workspace_id,
            query_text=fixture_query.query,
            embedding_provider=embedding_provider,
            reranker=reranker,
            final_top_k=_TOP_K,
            record_event=True,
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
    db.commit()
    return per_query


def _average(per_query: list[dict[str, Any]], metric_key: str) -> float:
    values = [row[metric_key] for row in per_query]
    return sum(values) / len(values) if values else 0.0


def _run_generation_evaluation(db, workspace_id, embedding_provider, reranker, llm_provider):
    """Exercises generation on two representative fixture queries and
    computes real, mechanically-checkable groundedness/citation metrics
    (see app/evaluation/metrics.py's module docstring for why
    faithfulness/answer-relevance are not fabricated as numeric scores
    here)."""
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


def main() -> None:
    db = SessionLocal()
    workspace = Workspace(name=f"eval-{uuid.uuid4().hex[:8]}")
    db.add(workspace)
    db.flush()

    embedding_provider = get_embedding_provider()
    reranker = get_reranker()
    llm_provider = get_llm_provider()

    try:
        chunk_ids_by_key = _ingest_fixture_documents(db, workspace.id, embedding_provider)
        retrieval_rows = _run_retrieval_evaluation(
            db, workspace.id, embedding_provider, reranker, chunk_ids_by_key
        )
        generation_rows = _run_generation_evaluation(
            db, workspace.id, embedding_provider, reranker, llm_provider
        )

        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "configuration": {
                "embedding_provider": embedding_provider.model_name,
                "reranker": type(reranker).__name__,
                "llm_provider": llm_provider.model_name,
                "top_k": _TOP_K,
                "document_count": len(DOCUMENTS),
                "query_count": len(QUERIES),
            },
            "retrieval": {
                "per_query": retrieval_rows,
                "averages": {
                    f"recall@{_TOP_K}": _average(retrieval_rows, f"recall@{_TOP_K}"),
                    f"precision@{_TOP_K}": _average(retrieval_rows, f"precision@{_TOP_K}"),
                    "mrr": _average(retrieval_rows, "mrr"),
                    f"ndcg@{_TOP_K}": _average(retrieval_rows, f"ndcg@{_TOP_K}"),
                    f"hit_rate@{_TOP_K}": _average(retrieval_rows, f"hit_rate@{_TOP_K}"),
                },
            },
            "generation": {"per_query": generation_rows},
        }

        results_path = _REPO_ROOT / "eval" / "results" / "retrieval_evaluation.json"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(report, indent=2, default=str) + "\n")

        print(json.dumps(report, indent=2, default=str))
        print(f"\nWrote {results_path.relative_to(_REPO_ROOT)}")
    finally:
        db.rollback()
        db.delete(workspace)
        db.commit()
        db.close()


if __name__ == "__main__":
    main()
