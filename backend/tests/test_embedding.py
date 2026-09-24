"""Unit tests for `app.ingestion.embedding` (Issue #3, Slice 3.7). Pure
`str -> list[float]` transformation -- no database, HTTP, or filesystem.
"""

from __future__ import annotations

import math

import pytest

from app.ingestion.embedding import (
    EmbeddingTransientError,
    LocalHashingEmbeddingProvider,
    embed_with_retry,
)


def test_embedding_has_the_declared_dimension() -> None:
    provider = LocalHashingEmbeddingProvider()
    [vector] = provider.embed_batch(["hello world"])
    assert len(vector) == provider.dimension


def test_embedding_is_deterministic_across_instances() -> None:
    first = LocalHashingEmbeddingProvider().embed_batch(["The quick brown fox."])
    second = LocalHashingEmbeddingProvider().embed_batch(["The quick brown fox."])
    assert first == second


def test_different_text_produces_different_embeddings() -> None:
    [a] = LocalHashingEmbeddingProvider().embed_batch(["alpha beta gamma"])
    [b] = LocalHashingEmbeddingProvider().embed_batch(["completely different content"])
    assert a != b


def test_embedding_is_l2_normalized_for_non_empty_text() -> None:
    [vector] = LocalHashingEmbeddingProvider().embed_batch(["some real content here"])
    magnitude = math.sqrt(sum(component * component for component in vector))
    assert magnitude == pytest.approx(1.0, abs=1e-9)


def test_empty_text_produces_the_zero_vector_not_an_error() -> None:
    provider = LocalHashingEmbeddingProvider()
    [vector] = provider.embed_batch([""])
    assert vector == [0.0] * provider.dimension


def test_whitespace_only_text_produces_the_zero_vector() -> None:
    provider = LocalHashingEmbeddingProvider()
    [vector] = provider.embed_batch(["   \n\t  "])
    assert vector == [0.0] * provider.dimension


def test_unicode_text_embeds_without_error() -> None:
    provider = LocalHashingEmbeddingProvider()
    [vector] = provider.embed_batch(["தமிழ் ಕನ್ನಡ हिन्दी 😀"])
    assert len(vector) == provider.dimension
    assert any(component != 0.0 for component in vector)


def test_batch_order_matches_input_order() -> None:
    provider = LocalHashingEmbeddingProvider()
    texts = ["first text", "second text", "third text"]
    batch = provider.embed_batch(texts)
    individually = [provider.embed_batch([text])[0] for text in texts]
    assert batch == individually


def test_case_insensitive_tokens_hash_the_same() -> None:
    provider = LocalHashingEmbeddingProvider()
    [lower] = provider.embed_batch(["hello world"])
    [upper] = provider.embed_batch(["HELLO WORLD"])
    assert lower == upper


def test_provider_declares_model_name_and_version() -> None:
    provider = LocalHashingEmbeddingProvider()
    assert provider.model_name == "local-hashing"
    assert provider.model_version == "v1"


# --- embed_with_retry() ------------------------------------------------------


def test_embed_with_retry_returns_provider_result_on_first_success() -> None:
    provider = LocalHashingEmbeddingProvider()
    result = embed_with_retry(provider, ["a", "b"])
    assert len(result) == 2


class _FlakyProvider:
    model_name = "flaky"
    model_version = "v1"
    dimension = 4

    def __init__(self, *, fail_times: int) -> None:
        self._fail_times = fail_times
        self.call_count = 0

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise EmbeddingTransientError("simulated transient failure")
        return [[0.0, 0.0, 0.0, 0.0] for _ in texts]


def test_embed_with_retry_retries_transient_errors_and_eventually_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.ingestion.embedding.time.sleep", lambda _seconds: None)
    provider = _FlakyProvider(fail_times=2)
    result = embed_with_retry(provider, ["x"], max_attempts=3)
    assert result == [[0.0, 0.0, 0.0, 0.0]]
    assert provider.call_count == 3


def test_embed_with_retry_gives_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.ingestion.embedding.time.sleep", lambda _seconds: None)
    provider = _FlakyProvider(fail_times=5)
    with pytest.raises(EmbeddingTransientError):
        embed_with_retry(provider, ["x"], max_attempts=2)
    assert provider.call_count == 2


class _AlwaysRaisesNonTransient:
    model_name = "broken"
    model_version = "v1"
    dimension = 4

    def __init__(self) -> None:
        self.call_count = 0

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        raise ValueError("a permanent, non-retriable failure")


def test_embed_with_retry_does_not_retry_non_transient_errors() -> None:
    provider = _AlwaysRaisesNonTransient()
    with pytest.raises(ValueError, match="permanent"):
        embed_with_retry(provider, ["x"], max_attempts=5)
    assert provider.call_count == 1
