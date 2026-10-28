"""Turns a user's question into the evidence to answer it (or a direct
reply), before any model is involved.

Order of resolution (each step only when it applies):

1. Which document(s) does the question name ("my PC lab PDF")? Several
   equally good matches -> ask which.
2. Does it name an item ("Program 5", "the first program")? Resolve it to the
   item's whole span, or answer deterministically that it does not exist /
   which documents hold it.
3. Is it a follow-up ("explain that line by line")? Re-use the item/document
   focus of the recent questions and the chunks the previous answer cited.
4. Otherwise ordinary hybrid retrieval, optionally scoped to the named
   document, with a relevance gate so an off-topic question finds no
   evidence instead of the "nearest" unrelated text.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingestion.embedding import EmbeddingProvider
from app.models.document import DocumentStatus
from app.repositories import document_repository
from app.retrieval.outline import Found, Reply, resolve_locator
from app.retrieval.references import (
    Locator,
    is_followup,
    match_documents,
    parse_locator,
    shares_content_terms,
)
from app.retrieval.reranker import Reranker
from app.retrieval.service import hybrid_search
from app.retrieval.types import RetrievalCandidate

_FOCUS_LOOKBACK = 4


@dataclass
class Resolution:
    candidates: list[RetrievalCandidate] = field(default_factory=list)
    # Set when the answer is decided without a model (missing item, which
    # document?). `candidates` is then empty.
    direct_reply: str | None = None
    # The evidence is one resolved unit (a whole program): cite all of it.
    cite_all: bool = False
    note: str = ""


def _gate_applies(embedding_provider: EmbeddingProvider) -> bool:
    # A real semantic embedder finds meaning-level matches that share no
    # words with the question; only the hashing embedder needs the guard.
    return getattr(embedding_provider, "semantic", False) is False


def resolve_question(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query: str,
    previous_user_questions: Sequence[str],
    prior_cited_chunks: Sequence[RetrievalCandidate],
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    conversation_id: uuid.UUID | None,
    user_message_id: uuid.UUID | None,
) -> Resolution:
    settings = get_settings()
    documents = document_repository.list_for_workspace(
        db, workspace_id=workspace_id, status=DocumentStatus.READY
    )
    names = {document.id: document.filename for document in documents}
    pairs = [(document.id, document.filename) for document in documents]

    locator: Locator | None = parse_locator(query)
    named = match_documents(query, pairs)
    followup = is_followup(query)

    if not locator and not named and followup:
        for previous in reversed(list(previous_user_questions)[-_FOCUS_LOOKBACK:]):
            earlier_locator = parse_locator(previous)
            earlier_named = match_documents(previous, pairs)
            if earlier_locator or earlier_named:
                locator, named = earlier_locator, earlier_named
                break

    if len(named) > 1:
        listing = ", ".join(names[d] for d in named)
        return Resolution(
            direct_reply=f"Which document do you mean? I found several that match: {listing}."
        )
    scope = named[:1] or None

    if locator:
        outcome = resolve_locator(
            db,
            workspace_id=workspace_id,
            locator=locator,
            document_names=names,
            scope=scope,
            max_chars=settings.llm_context_max_chars,
        )
        if isinstance(outcome, Reply):
            return Resolution(direct_reply=outcome.message)
        if isinstance(outcome, Found):
            return Resolution(
                candidates=outcome.candidates, cite_all=True, note=f"resolved {outcome.label}"
            )

    candidates = hybrid_search(
        db,
        workspace_id=workspace_id,
        query_text=query,
        embedding_provider=embedding_provider,
        reranker=reranker,
        document_id=scope[0] if scope else None,
        conversation_id=conversation_id,
        message_id=user_message_id,
    )

    if followup and prior_cited_chunks:
        seen = {c.chunk_id for c in prior_cited_chunks}
        merged = list(prior_cited_chunks) + [c for c in candidates if c.chunk_id not in seen]
        return Resolution(candidates=merged, note="follow-up: previous evidence first")

    if _gate_applies(embedding_provider) and not scope:
        relevant = [c for c in candidates if shares_content_terms(query, c.content)]
        if not relevant:
            return Resolution(note="no passage shares a content word with the question")
        candidates = relevant
    return Resolution(candidates=candidates, note="scoped" if scope else "")


__all__ = ["Resolution", "resolve_question"]
