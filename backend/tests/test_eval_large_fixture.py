"""Guards the larger evaluation fixture (`eval/datasets/
retrieval_fixture_large.py`) against silently losing the properties it
exists to test. Pure functions over the real chunkers -- no database.

Like `tests/test_config.py`'s `.env.example` regression test, this needs
a full repository checkout: the Docker image deliberately contains only
`backend/`, so it skips there rather than failing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from app.ingestion import chunking
from app.ingestion.chunking import ChunkingStrategy
from app.ingestion.cleaning import clean
from app.ingestion.extraction import ExtractedDocument, ExtractedSection

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "eval" / "datasets" / "retrieval_fixture_large.py"
)
if not _FIXTURE_PATH.exists():
    pytest.skip(
        "requires a full repository checkout (eval/ is not in the image)",
        allow_module_level=True,
    )


def _load_fixture() -> Any:
    # Loaded by file path (not `import eval.datasets...`): `eval/` lives
    # at the repository root, outside the backend package mypy/pytest see.
    spec = importlib.util.spec_from_file_location("retrieval_fixture_large", _FIXTURE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


_fixture = _load_fixture()
DOCUMENTS: tuple[Any, ...] = _fixture.DOCUMENTS
QUERIES: tuple[Any, ...] = _fixture.QUERIES
RETENTION_SENTENCE: str = _fixture.RETENTION_SENTENCE
PROCUREMENT_SENTENCE: str = _fixture.PROCUREMENT_SENTENCE
TRAVEL_SENTENCE: str = _fixture.TRAVEL_SENTENCE


def _chunk_texts(document: Any, chunker: ChunkingStrategy) -> list[str]:
    extracted = ExtractedDocument(
        sections=[
            ExtractedSection(text=text, page=None, heading=heading)
            for heading, text in document.sections
        ],
        page_count=None,
    )
    return [chunk.content for chunk in chunker.chunk(clean(extracted))]


def _all_chunk_texts(chunker: ChunkingStrategy) -> list[str]:
    return [text for document in DOCUMENTS for text in _chunk_texts(document, chunker)]


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


_CHUNKERS: dict[str, ChunkingStrategy] = {
    "structure_aware": chunking.StructureAwareChunker(),
    "fixed_size": chunking.FixedSizeChunker(),
    "recursive": chunking.RecursiveChunker(),
}


def test_fixture_has_unique_keys_and_all_query_categories() -> None:
    keys = [document.key for document in DOCUMENTS]
    assert len(keys) == len(set(keys))
    categories = {query.category for query in QUERIES}
    assert categories == {"direct", "distractor", "multi_fact", "boundary", "unanswerable"}


def test_documents_are_actually_multi_chunk() -> None:
    # The whole point versus the small fixture (one chunk per document).
    for document in DOCUMENTS:
        assert len(_chunk_texts(document, _CHUNKERS["structure_aware"])) >= 2, document.key


@pytest.mark.parametrize("strategy", ["structure_aware", "recursive"])
def test_every_evidence_phrase_survives_structure_respecting_chunkers(strategy: str) -> None:
    haystacks = [_normalize(text) for text in _all_chunk_texts(_CHUNKERS[strategy])]
    for query in QUERIES:
        for phrase in query.evidence_phrases:
            assert any(_normalize(phrase) in h for h in haystacks), (strategy, phrase)


def test_non_boundary_evidence_survives_fixed_size_chunking_too() -> None:
    haystacks = [_normalize(text) for text in _all_chunk_texts(_CHUNKERS["fixed_size"])]
    for query in QUERIES:
        if query.category == "boundary":
            continue
        for phrase in query.evidence_phrases:
            assert any(_normalize(phrase) in h for h in haystacks), phrase


@pytest.mark.parametrize("sentence", [RETENTION_SENTENCE, PROCUREMENT_SENTENCE, TRAVEL_SENTENCE])
def test_boundary_sentences_are_split_by_fixed_size_chunking_only(sentence: str) -> None:
    # If this ever fails, the fixture no longer exercises chunk-boundary
    # behaviour and the chunking-strategy comparison is not meaningful.
    fixed = [_normalize(text) for text in _all_chunk_texts(_CHUNKERS["fixed_size"])]
    assert not any(_normalize(sentence) in h for h in fixed)
    for strategy in ("structure_aware", "recursive"):
        kept = [_normalize(text) for text in _all_chunk_texts(_CHUNKERS[strategy])]
        assert any(_normalize(sentence) in h for h in kept), strategy


def test_unanswerable_queries_have_no_evidence_and_others_do() -> None:
    for query in QUERIES:
        assert bool(query.evidence_phrases) == (query.category != "unanswerable"), query.query


def test_every_evidence_phrase_is_unique_enough_to_be_unambiguous() -> None:
    # Distractor documents must not accidentally also contain the phrase.
    haystacks = [_normalize(text) for text in _all_chunk_texts(_CHUNKERS["structure_aware"])]
    for query in QUERIES:
        if query.category != "distractor":
            continue
        for phrase in query.evidence_phrases:
            assert sum(_normalize(phrase) in h for h in haystacks) == 1, phrase
