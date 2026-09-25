"""Tests for the retrieval pipeline (Issue #4, Slice 4.2): dense
(pgvector), lexical (Postgres full-text search), RRF fusion, the
`LexicalOverlapReranker`, and the `hybrid_search()` orchestrator. Real
Postgres, no mocks, matching this project's established convention.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.ingestion.embedding import LocalHashingEmbeddingProvider
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.message import Message, MessageRole
from app.models.retrieval_event import RetrievalEvent
from app.models.workspace import Workspace
from app.retrieval.dense import dense_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.lexical import lexical_search
from app.retrieval.reranker import LexicalOverlapReranker
from app.retrieval.service import hybrid_search
from app.retrieval.types import RetrievalCandidate

_PROVIDER = LocalHashingEmbeddingProvider()


def _make_workspace(db_session: DbSession, name: str = "Test workspace") -> Workspace:
    workspace = Workspace(name=name)
    db_session.add(workspace)
    db_session.flush()
    return workspace


def _make_document(
    db_session: DbSession, *, workspace: Workspace, status: DocumentStatus = DocumentStatus.READY
) -> Document:
    document = Document(
        workspace_id=workspace.id,
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256=uuid.uuid4().hex,
        storage_key=f"{workspace.id}/{uuid.uuid4()}.pdf",
        status=status,
    )
    db_session.add(document)
    db_session.flush()
    return document


def _make_chunk(
    db_session: DbSession,
    *,
    workspace: Workspace,
    document: Document,
    chunk_index: int,
    content: str,
    embed: bool = True,
) -> DocumentChunk:
    chunk = DocumentChunk(
        document_id=document.id,
        workspace_id=workspace.id,
        chunk_index=chunk_index,
        content=content,
    )
    if embed:
        [vector] = _PROVIDER.embed_batch([content])
        chunk.embedding = vector
        chunk.embedding_model = _PROVIDER.model_name
        chunk.embedding_dimension = _PROVIDER.dimension
    db_session.add(chunk)
    db_session.flush()
    return chunk


# --- dense_search -------------------------------------------------------


def test_dense_search_ranks_the_most_similar_chunk_first(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=0,
        content="Our refund policy allows returns within thirty days of purchase.",
    )
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=1,
        content="Photosynthesis converts sunlight into chemical energy within plant cells.",
    )

    # Deliberately no shared tokens (not even stopwords) between the
    # query and the second chunk -- LocalHashingEmbeddingProvider has no
    # IDF weighting, so a query sharing only common stopwords with an
    # otherwise-unrelated sentence can coincidentally tie a query that
    # shares real content words with another sentence (both contribute
    # equally in this simple scheme). Zero token overlap guarantees a
    # deterministic, unambiguous score difference here.
    [query_embedding] = _PROVIDER.embed_batch(["What is the refund policy for returns?"])
    results = dense_search(
        db_session, workspace_id=workspace.id, query_embedding=query_embedding, top_k=10
    )

    assert len(results) == 2
    assert "refund policy" in results[0].content
    assert results[0].score > results[1].score


def test_dense_search_excludes_chunks_without_an_embedding(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=0,
        content="Not yet embedded.",
        embed=False,
    )

    [query_embedding] = _PROVIDER.embed_batch(["anything"])
    results = dense_search(
        db_session, workspace_id=workspace.id, query_embedding=query_embedding, top_k=10
    )
    assert results == []


def test_dense_search_excludes_non_ready_documents(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace, status=DocumentStatus.EMBEDDED)
    _make_chunk(
        db_session, workspace=workspace, document=document, chunk_index=0, content="Not ready yet."
    )

    [query_embedding] = _PROVIDER.embed_batch(["anything"])
    results = dense_search(
        db_session, workspace_id=workspace.id, query_embedding=query_embedding, top_k=10
    )
    assert results == []


def test_dense_search_is_workspace_scoped(db_session: DbSession) -> None:
    workspace_a = _make_workspace(db_session, name="A")
    workspace_b = _make_workspace(db_session, name="B")
    document_b = _make_document(db_session, workspace=workspace_b)
    _make_chunk(
        db_session,
        workspace=workspace_b,
        document=document_b,
        chunk_index=0,
        content="Secret content belonging to workspace B only.",
    )

    [query_embedding] = _PROVIDER.embed_batch(["Secret content belonging to workspace B only."])
    results = dense_search(
        db_session, workspace_id=workspace_a.id, query_embedding=query_embedding, top_k=10
    )
    assert results == []


def test_dense_search_respects_document_id_filter(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document_a = _make_document(db_session, workspace=workspace)
    document_b = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session, workspace=workspace, document=document_a, chunk_index=0, content="From A."
    )
    _make_chunk(
        db_session, workspace=workspace, document=document_b, chunk_index=0, content="From B."
    )

    [query_embedding] = _PROVIDER.embed_batch(["From"])
    results = dense_search(
        db_session,
        workspace_id=workspace.id,
        query_embedding=query_embedding,
        top_k=10,
        document_id=document_a.id,
    )
    assert len(results) == 1
    assert results[0].document_id == document_a.id


def test_dense_search_respects_top_k(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    for i in range(5):
        _make_chunk(
            db_session, workspace=workspace, document=document, chunk_index=i, content=f"Chunk {i}."
        )

    [query_embedding] = _PROVIDER.embed_batch(["Chunk"])
    results = dense_search(
        db_session, workspace_id=workspace.id, query_embedding=query_embedding, top_k=2
    )
    assert len(results) == 2


# --- lexical_search -------------------------------------------------------


def test_lexical_search_finds_matching_chunk(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=0,
        content="Our refund policy allows returns within thirty days.",
        embed=False,
    )
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=1,
        content="The office is closed on public holidays.",
        embed=False,
    )

    results = lexical_search(
        db_session, workspace_id=workspace.id, query_text="refund policy", top_k=10
    )
    assert len(results) == 1
    assert "refund" in results[0].content


def test_lexical_search_no_match_returns_empty(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=0,
        content="Completely unrelated content.",
        embed=False,
    )

    results = lexical_search(
        db_session, workspace_id=workspace.id, query_text="refund policy", top_k=10
    )
    assert results == []


def test_lexical_search_is_workspace_scoped(db_session: DbSession) -> None:
    workspace_a = _make_workspace(db_session, name="A")
    workspace_b = _make_workspace(db_session, name="B")
    document_b = _make_document(db_session, workspace=workspace_b)
    _make_chunk(
        db_session,
        workspace=workspace_b,
        document=document_b,
        chunk_index=0,
        content="Refund policy for workspace B.",
        embed=False,
    )

    results = lexical_search(
        db_session, workspace_id=workspace_a.id, query_text="refund policy", top_k=10
    )
    assert results == []


def test_lexical_search_excludes_non_ready_documents(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace, status=DocumentStatus.CHUNKED)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=0,
        content="Refund policy details.",
        embed=False,
    )

    results = lexical_search(
        db_session, workspace_id=workspace.id, query_text="refund policy", top_k=10
    )
    assert results == []


def test_lexical_search_respects_document_id_filter(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document_a = _make_document(db_session, workspace=workspace)
    document_b = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document_a,
        chunk_index=0,
        content="Refund policy A.",
        embed=False,
    )
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document_b,
        chunk_index=0,
        content="Refund policy B.",
        embed=False,
    )

    results = lexical_search(
        db_session,
        workspace_id=workspace.id,
        query_text="refund policy",
        top_k=10,
        document_id=document_a.id,
    )
    assert len(results) == 1
    assert results[0].document_id == document_a.id


# --- reciprocal_rank_fusion -------------------------------------------------


def _candidate(chunk_id: uuid.UUID, score: float = 0.0) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        content="x",
        page=None,
        section=None,
        score=score,
    )


def test_rrf_ranks_a_candidate_in_both_lists_above_one_in_only_one() -> None:
    shared = uuid.uuid4()
    only_dense = uuid.uuid4()
    only_lexical = uuid.uuid4()

    dense_ranking = [_candidate(shared), _candidate(only_dense)]
    lexical_ranking = [_candidate(shared), _candidate(only_lexical)]

    fused = reciprocal_rank_fusion([dense_ranking, lexical_ranking])

    assert fused[0].chunk_id == shared
    fused_ids = {c.chunk_id for c in fused}
    assert fused_ids == {shared, only_dense, only_lexical}


def test_rrf_deduplicates_by_chunk_id() -> None:
    shared = uuid.uuid4()
    fused = reciprocal_rank_fusion([[_candidate(shared)], [_candidate(shared)]])
    assert len(fused) == 1


def test_rrf_empty_rankings_returns_empty() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


# --- LexicalOverlapReranker --------------------------------------------------


def test_reranker_ranks_exact_token_match_above_unrelated_content() -> None:
    reranker = LexicalOverlapReranker()
    exact = replace(_candidate(uuid.uuid4()), content="refund policy details")
    unrelated = replace(_candidate(uuid.uuid4()), content="completely different text")

    result = reranker.rerank(query="refund policy", candidates=[unrelated, exact])
    assert result[0].content == "refund policy details"


def test_reranker_empty_query_returns_candidates_unchanged() -> None:
    reranker = LexicalOverlapReranker()
    candidates = [_candidate(uuid.uuid4()), _candidate(uuid.uuid4())]
    result = reranker.rerank(query="   ", candidates=candidates)
    assert result == candidates


def test_reranker_never_drops_or_adds_candidates() -> None:
    reranker = LexicalOverlapReranker()
    candidates = [_candidate(uuid.uuid4()) for _ in range(5)]
    result = reranker.rerank(query="something", candidates=candidates)
    assert {c.chunk_id for c in result} == {c.chunk_id for c in candidates}


# --- hybrid_search (end-to-end) ----------------------------------------------


def test_hybrid_search_returns_results_and_records_a_retrieval_event(
    db_session: DbSession,
) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=0,
        content="Our refund policy allows returns within thirty days of purchase.",
    )

    results = hybrid_search(
        db_session,
        workspace_id=workspace.id,
        query_text="What is the refund policy?",
        embedding_provider=_PROVIDER,
        reranker=LexicalOverlapReranker(),
    )
    assert len(results) == 1
    assert "refund policy" in results[0].content

    event = db_session.execute(
        select(RetrievalEvent).where(RetrievalEvent.workspace_id == workspace.id)
    ).scalar_one()
    assert event.query_text == "What is the refund policy?"
    assert event.method == "hybrid"
    assert len(event.results) == 1
    assert event.results[0]["chunk_id"] == str(results[0].chunk_id)
    assert event.latency_ms is not None
    assert event.rewritten_query_text is None


def test_hybrid_search_record_event_false_skips_persisting_an_event(
    db_session: DbSession,
) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session, workspace=workspace, document=document, chunk_index=0, content="Some content."
    )

    hybrid_search(
        db_session,
        workspace_id=workspace.id,
        query_text="Some content.",
        embedding_provider=_PROVIDER,
        reranker=LexicalOverlapReranker(),
        record_event=False,
    )

    count = db_session.execute(
        select(RetrievalEvent).where(RetrievalEvent.workspace_id == workspace.id)
    ).scalars().all()
    assert count == []


def test_hybrid_search_is_workspace_scoped(db_session: DbSession) -> None:
    workspace_a = _make_workspace(db_session, name="A")
    workspace_b = _make_workspace(db_session, name="B")
    document_b = _make_document(db_session, workspace=workspace_b)
    _make_chunk(
        db_session,
        workspace=workspace_b,
        document=document_b,
        chunk_index=0,
        content="Confidential workspace B content.",
    )

    results = hybrid_search(
        db_session,
        workspace_id=workspace_a.id,
        query_text="Confidential workspace B content.",
        embedding_provider=_PROVIDER,
        reranker=LexicalOverlapReranker(),
    )
    assert results == []


def test_hybrid_search_preserves_original_query_alongside_a_rewrite(
    db_session: DbSession,
) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document,
        chunk_index=0,
        content="The refund policy allows returns within thirty days.",
    )

    hybrid_search(
        db_session,
        workspace_id=workspace.id,
        query_text="it",
        rewritten_query_text="What is the refund policy?",
        embedding_provider=_PROVIDER,
        reranker=LexicalOverlapReranker(),
    )

    event = db_session.execute(
        select(RetrievalEvent).where(RetrievalEvent.workspace_id == workspace.id)
    ).scalar_one()
    assert event.query_text == "it"
    assert event.rewritten_query_text == "What is the refund policy?"


def test_hybrid_search_respects_document_id_filter(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document_a = _make_document(db_session, workspace=workspace)
    document_b = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document_a,
        chunk_index=0,
        content="Refund policy in document A.",
    )
    _make_chunk(
        db_session,
        workspace=workspace,
        document=document_b,
        chunk_index=0,
        content="Refund policy in document B.",
    )

    results = hybrid_search(
        db_session,
        workspace_id=workspace.id,
        query_text="refund policy",
        embedding_provider=_PROVIDER,
        reranker=LexicalOverlapReranker(),
        document_id=document_a.id,
    )
    assert all(candidate.document_id == document_a.id for candidate in results)


def test_hybrid_search_links_conversation_and_message_ids(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    _make_chunk(
        db_session, workspace=workspace, document=document, chunk_index=0, content="Some content."
    )
    conversation = Conversation(workspace_id=workspace.id)
    db_session.add(conversation)
    db_session.flush()
    message = Message(
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        role=MessageRole.USER,
        content="Tell me about it.",
    )
    db_session.add(message)
    db_session.flush()

    hybrid_search(
        db_session,
        workspace_id=workspace.id,
        query_text="Some content.",
        embedding_provider=_PROVIDER,
        reranker=LexicalOverlapReranker(),
        conversation_id=conversation.id,
        message_id=message.id,
    )

    event = db_session.execute(
        select(RetrievalEvent).where(RetrievalEvent.workspace_id == workspace.id)
    ).scalar_one()
    assert event.conversation_id == conversation.id
    assert event.message_id == message.id
