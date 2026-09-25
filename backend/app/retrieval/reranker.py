"""Reranker abstraction (docs/ARCHITECTURE.md "Provider abstractions") —
re-scores a fused candidate list against the query for higher precision
at the top of the list, the same role a cross-encoder model plays in a
production RAG pipeline.

Mirrors `EmbeddingProvider`'s shape exactly: a `Protocol`, one concrete
implementation today, and a settings-driven factory. `LexicalOverlapReranker`
is deterministic and offline (Jaccard token overlap between the query and
each candidate's content) — no commercial vendor/model selected yet, so
the whole retrieval pipeline stays testable/demoable without a paid API,
matching `LocalHashingEmbeddingProvider`'s own precedent (Issue #3,
Slice 3.7). It is a real, explainable scoring signal, not a stub — but a
genuinely weaker one than a trained cross-encoder; swapping in a real
model later is additive (implement `Reranker`, branch in
`get_reranker()`), not a rewrite.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Protocol

from app.retrieval.types import RetrievalCandidate

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class Reranker(Protocol):
    def rerank(
        self, *, query: str, candidates: list[RetrievalCandidate]
    ) -> list[RetrievalCandidate]:
        """Returns `candidates` re-scored and re-sorted best-first. Never
        drops or adds a candidate -- same set in, same set out, only the
        order/score changes."""
        ...


class LexicalOverlapReranker:
    """Scores each candidate by the Jaccard similarity of its token set
    against the query's token set — a real, deterministic, explainable
    signal (candidates that literally share more of the query's words
    rank higher), independent of whichever upstream method(s) surfaced
    the candidate. Ties (including the common case of zero overlap)
    preserve the input's own relative order, since Python's sort is
    stable — a sensible fallback to the fused ranking rather than an
    arbitrary reshuffle.
    """

    def rerank(
        self, *, query: str, candidates: list[RetrievalCandidate]
    ) -> list[RetrievalCandidate]:
        query_tokens = set(_TOKEN_RE.findall(query.lower()))
        if not query_tokens:
            return list(candidates)

        rescored = [
            replace(candidate, score=self._jaccard(query_tokens, candidate.content))
            for candidate in candidates
        ]
        rescored.sort(key=lambda candidate: candidate.score, reverse=True)
        return rescored

    @staticmethod
    def _jaccard(query_tokens: set[str], content: str) -> float:
        content_tokens = set(_TOKEN_RE.findall(content.lower()))
        if not content_tokens:
            return 0.0
        overlap = len(query_tokens & content_tokens)
        union = len(query_tokens | content_tokens)
        return overlap / union


def get_reranker() -> Reranker:
    """`LexicalOverlapReranker` is the only implementation today — this
    gains a branch on a future `Settings.reranker_provider` value
    (matching `get_embedding_provider()`'s pattern) when a second, real
    implementation is actually added, not before."""
    return LexicalOverlapReranker()


__all__ = ["LexicalOverlapReranker", "Reranker", "get_reranker"]
