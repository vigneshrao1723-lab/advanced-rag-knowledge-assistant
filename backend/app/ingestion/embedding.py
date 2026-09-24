"""Embedding generation (docs/ARCHITECTURE.md "Provider abstractions",
GitHub Issue #3, Slice 3.7).

Mirrors `StorageProvider`/`EmailProvider`'s shape: a `Protocol`, one
concrete implementation today, and a settings-driven factory
(`get_embedding_provider()`). No commercial vendor is selected yet
(docs/RAG_DESIGN.md) — `LocalHashingEmbeddingProvider` is a deterministic,
offline, dependency-free provider that lets the whole ingestion pipeline
be built, tested, and demonstrated end-to-end without a paid external API
or network access. It produces a real, well-defined vector (a normalized
hashed bag-of-words, the classic "hashing trick" also used by e.g.
scikit-learn's `HashingVectorizer`) — semantically weaker than a trained
embedding model, but a genuine, consistent similarity signal, not a stub.
Swapping in a real hosted provider later is additive: implement
`EmbeddingProvider`, branch on it in `get_embedding_provider()` (matching
`get_storage_provider()`'s pattern), done — nothing in this module's
callers depends on which concrete provider is selected.

This module is pure: no database, HTTP, or lifecycle dependency, matching
`extraction.py`/`cleaning.py`/`chunking.py`'s own shape. It knows nothing
about `DocumentChunk` rows or documents — `document_service.py` is
responsible for batching chunk content into calls here and persisting the
results.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Protocol

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class EmbeddingError(Exception):
    """Any embedding-generation failure — treated by `document_service.py`
    as an expected, handled document-processing failure (`FAILED`, a
    generic reason), never a raw `500`. Never include provider-internal
    detail in the message (no API response body, no request/response
    headers, no raw exception text) — this can reach the client via the
    same `str(exc)`-is-safe-by-construction convention already used by
    `ChunkingError`/`ExtractionError`."""


class EmbeddingTransientError(EmbeddingError):
    """A transient, retry-worthy failure — a rate limit, timeout, or
    temporary provider outage. `embed_with_retry()` below retries only
    this subclass, with exponential backoff, up to a bounded number of
    attempts. A future networked provider raises this for anything
    retry-worthy; `LocalHashingEmbeddingProvider` never raises it, since
    it has no network call to fail transiently — the retry loop still
    runs correctly for it (one attempt, immediate return), so this path
    is exercised and correct the moment a real provider is plugged in,
    not untested until then.
    """


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str
    dimension: int

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Returns one embedding vector per input text, same order,
        length `dimension`. Raises `EmbeddingTransientError` for a
        retry-worthy failure, `EmbeddingError` for anything else."""
        ...


class LocalHashingEmbeddingProvider:
    """Deterministic, offline: the same text always produces the same
    vector, in this process and every other. Tokenizes on Unicode word
    boundaries (`\\w+`, so this handles non-ASCII scripts, not just
    English), lowercases, and hashes each token via `blake2b` (stable
    across processes/runs — unlike Python's built-in `hash()`, which is
    randomized per-process via `PYTHONHASHSEED` and would make this
    provider non-deterministic across restarts). Each token contributes
    +1/-1 (sign derived from a separate hash byte, the standard
    feature-hashing trick to reduce collision bias — see scikit-learn's
    `HashingVectorizer`) to one of `dimension` buckets; the resulting
    vector is L2-normalized so cosine similarity behaves sensibly. Empty
    or whitespace-only input produces the zero vector (not normalized,
    since there is nothing to normalize) — a defined, non-crashing
    result, not an error.
    """

    model_name = "local-hashing"
    model_version = "v1"
    dimension = 384

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]


def get_embedding_provider() -> EmbeddingProvider:
    """`LocalHashingEmbeddingProvider` is the only implementation today —
    this gains a branch on a future `Settings.embedding_provider` value
    (matching `get_storage_provider()`/`get_email_provider()`'s pattern)
    when a second, real implementation is actually added, not before."""
    return LocalHashingEmbeddingProvider()


def embed_with_retry(
    provider: EmbeddingProvider, texts: list[str], *, max_attempts: int = 3
) -> list[list[float]]:
    """Retries only `EmbeddingTransientError`, with exponential backoff
    (0.5s, 1s, ... capped by `max_attempts`). Any other exception (a
    permanent provider/input error) propagates immediately — retrying it
    would only waste time before failing anyway. Runs synchronously and
    is meant to be called from a worker thread (`asyncio.to_thread()`),
    same as every other CPU/IO-bound ingestion stage in this codebase —
    `time.sleep()` here blocks only that worker thread, never the event
    loop.
    """
    attempt = 0
    while True:
        try:
            return provider.embed_batch(texts)
        except EmbeddingTransientError:
            attempt += 1
            if attempt >= max_attempts:
                raise
            time.sleep(0.5 * (2 ** (attempt - 1)))


__all__ = [
    "EmbeddingError",
    "EmbeddingProvider",
    "EmbeddingTransientError",
    "LocalHashingEmbeddingProvider",
    "embed_with_retry",
    "get_embedding_provider",
]
