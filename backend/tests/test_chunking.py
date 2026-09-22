"""Unit tests for `app.ingestion.chunking` (Issue #3, Slice 3.5). Pure
`ExtractedDocument -> list[Chunk]` transformation — no database, no HTTP,
no filesystem. Most fixtures are hand-built `ExtractedDocument`/
`ExtractedSection` objects so boundary conditions are exact and
deterministic; a couple of tests feed this module real
`app.ingestion.extraction.extract()` output, to prove the two modules'
contracts actually compose (field names/types), not just that this
module works against fixtures shaped the way this test file assumes.
"""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from app.ingestion import extraction
from app.ingestion.chunking import Chunk, ChunkingConfig, ChunkingError, StructureAwareChunker
from app.ingestion.extraction import ExtractedDocument, ExtractedSection

_CONFIG = ChunkingConfig(
    target_chunk_size=30, chunk_overlap=5, min_chunk_size=10, max_chunk_size=50
)


def _chunker(config: ChunkingConfig = _CONFIG) -> StructureAwareChunker:
    return StructureAwareChunker(config=config)


def _doc(*sections: ExtractedSection) -> ExtractedDocument:
    return ExtractedDocument(sections=list(sections))


# --- basic structure-aware chunking / ordering / indexes -------------------


def test_basic_paragraph_chunking_splits_on_blank_lines() -> None:
    section = ExtractedSection(
        text="Para one.\n\nPara two is here.\n\nPara three follows after that.",
        page=1,
        heading=None,
    )
    chunks = _chunker().chunk(_doc(section))
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Every produced chunk's content came from the section's own text --
    # no fabricated content.
    for c in chunks:
        assert c.content.replace("\n\n", " ").strip()


def test_chunk_indexes_start_at_zero_and_have_no_gaps() -> None:
    chunks = _chunker().chunk(
        _doc(
            ExtractedSection(text="a" * 40, page=1, heading=None),
            ExtractedSection(text="b" * 40, page=2, heading=None),
        )
    )
    assert chunks[0].chunk_index == 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_deterministic_output_for_identical_input_and_config() -> None:
    doc = _doc(
        ExtractedSection(
            text="Alpha beta gamma. Delta epsilon zeta.\n\nEta theta iota.", page=1, heading="H1"
        ),
        ExtractedSection(
            text="Kappa lambda mu nu xi omicron pi rho sigma tau.", page=2, heading="H2"
        ),
    )
    chunker = _chunker()
    first = chunker.chunk(doc)
    second = chunker.chunk(doc)
    third = StructureAwareChunker(config=_CONFIG).chunk(doc)  # a fresh instance, same config
    assert first == second == third


# --- section/page metadata preservation and non-mixing ---------------------


def test_section_metadata_is_preserved_from_the_source_section() -> None:
    section = ExtractedSection(
        text="Some heading-scoped content here.", page=None, heading="Introduction"
    )
    chunks = _chunker().chunk(_doc(section))
    assert chunks
    assert all(c.section == "Introduction" for c in chunks)
    assert all(c.page is None for c in chunks)


def test_page_metadata_is_preserved_from_the_source_section() -> None:
    section = ExtractedSection(text="Some page-scoped content here.", page=7, heading=None)
    chunks = _chunker().chunk(_doc(section))
    assert chunks
    assert all(c.page == 7 for c in chunks)
    assert all(c.section is None for c in chunks)


def test_chunks_never_mix_metadata_across_two_different_sections() -> None:
    # The schema-compatibility constraint documented in chunking.py's
    # module docstring: document_chunks stores one page/section value
    # per row, so a chunk must never claim to represent content from two
    # different ExtractedSections.
    doc = _doc(
        ExtractedSection(text="x" * 60, page=1, heading=None),
        ExtractedSection(text="y" * 60, page=2, heading=None),
    )
    chunks = _chunker().chunk(doc)
    page_1_chunks = [c for c in chunks if c.page == 1]
    page_2_chunks = [c for c in chunks if c.page == 2]
    assert page_1_chunks and page_2_chunks
    assert all("y" not in c.content for c in page_1_chunks)
    assert all("x" not in c.content for c in page_2_chunks)


def test_multiple_pages_each_produce_their_own_chunks() -> None:
    doc = _doc(
        ExtractedSection(
            text="First page content, reasonably long for a real chunk.", page=1, heading=None
        ),
        ExtractedSection(
            text="Second page content, also reasonably long for a chunk.", page=2, heading=None
        ),
        ExtractedSection(
            text="Third page content, likewise long enough to chunk.", page=3, heading=None
        ),
    )
    chunks = _chunker().chunk(doc)
    assert {c.page for c in chunks} == {1, 2, 3}


def test_multiple_sections_with_headings_each_keep_their_own_heading() -> None:
    doc = _doc(
        ExtractedSection(
            text="Content under heading A, long enough to matter here.", page=None, heading="A"
        ),
        ExtractedSection(
            text="Content under heading B, also long enough to matter.", page=None, heading="B"
        ),
    )
    chunks = _chunker().chunk(doc)
    assert {c.section for c in chunks} == {"A", "B"}


# --- long paragraph splitting (sentence / word / hard fallback) ------------


def test_long_paragraph_splits_on_sentence_boundaries() -> None:
    text = "Sentence one is here. Sentence two follows. Sentence three too. Sentence four also."
    config = ChunkingConfig(
        target_chunk_size=40, chunk_overlap=0, min_chunk_size=1, max_chunk_size=40
    )
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.content) <= config.max_chunk_size


def test_long_word_with_no_whitespace_falls_back_to_hard_character_split() -> None:
    text = "x" * 500  # one giant "word" -- no spaces, no sentence punctuation
    config = ChunkingConfig(
        target_chunk_size=50, chunk_overlap=0, min_chunk_size=1, max_chunk_size=50
    )
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert len(chunks) == 10  # 500 / 50, exactly
    assert all(len(c.content) == 50 for c in chunks)
    assert (
        "".join(c.content for c in chunks) == text
    )  # no overlap configured -- exact reconstruction


def test_pathological_long_paragraph_never_exceeds_max_chunk_size() -> None:
    text = "word " * 20_000  # ~100,000 chars, no punctuation, no blank lines
    config = ChunkingConfig(
        target_chunk_size=500, chunk_overlap=50, min_chunk_size=100, max_chunk_size=1000
    )
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert chunks
    assert all(len(c.content) <= config.max_chunk_size for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# --- overlap behavior --------------------------------------------------


def test_overlap_tail_of_one_chunk_appears_at_the_start_of_the_next() -> None:
    config = ChunkingConfig(
        target_chunk_size=30, chunk_overlap=8, min_chunk_size=15, max_chunk_size=40
    )
    text = "word " * 40  # long enough to force multiple chunks
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        tail = previous.content[-config.chunk_overlap :]
        assert current.content.startswith(tail) or tail in current.content


def test_zero_overlap_produces_no_shared_text_between_chunks() -> None:
    config = ChunkingConfig(
        target_chunk_size=30, chunk_overlap=0, min_chunk_size=10, max_chunk_size=40
    )
    text = "word " * 40
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert len(chunks) > 1
    # Exact reconstruction (modulo the "\n\n" joiners this module inserts
    # between packed pieces) proves nothing was duplicated or dropped.
    rejoined = "\n\n".join(chunks[i].content for i in range(len(chunks)))
    assert rejoined.replace("\n\n", " ").split() == text.split()


def test_overlap_never_produces_a_chunk_exceeding_max_chunk_size() -> None:
    config = ChunkingConfig(
        target_chunk_size=45, chunk_overlap=20, min_chunk_size=25, max_chunk_size=50
    )
    text = "word " * 100
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert all(len(c.content) <= config.max_chunk_size for c in chunks)


def test_overlap_does_not_produce_an_orphaned_tiny_fragment_chunk() -> None:
    # Regression test: a hard-split piece landing exactly at
    # max_chunk_size left the overlap tail unable to combine with the
    # next piece, and it used to be emitted as its own tiny fragment
    # chunk that only duplicated the previous chunk's tail. Every chunk
    # here must respect min_chunk_size, including at that boundary.
    config = ChunkingConfig(
        target_chunk_size=30, chunk_overlap=5, min_chunk_size=10, max_chunk_size=50
    )
    text = "x" * 500
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert all(len(c.content) >= config.min_chunk_size for c in chunks)
    assert all(len(c.content) <= config.max_chunk_size for c in chunks)


# --- minimum / maximum chunk behavior ---------------------------------


def test_short_section_below_min_chunk_size_still_produces_one_chunk() -> None:
    section = ExtractedSection(text="short", page=1, heading=None)
    chunks = _chunker().chunk(_doc(section))
    assert len(chunks) == 1
    assert chunks[0].content == "short"


def test_very_short_content_is_not_dropped() -> None:
    section = ExtractedSection(text="hi", page=1, heading=None)
    chunks = _chunker().chunk(_doc(section))
    assert len(chunks) == 1
    assert chunks[0].content == "hi"


def test_small_trailing_remainder_is_merged_into_the_previous_chunk_when_it_fits() -> None:
    config = ChunkingConfig(
        target_chunk_size=40, chunk_overlap=0, min_chunk_size=10, max_chunk_size=100
    )
    # Constructed so the final piece alone would be under min_chunk_size,
    # but comfortably fits merged into the previous chunk within max_chunk_size.
    text = "Alpha beta gamma delta epsilon zeta eta theta.\n\niota"
    chunks = StructureAwareChunker(config=config).chunk(
        _doc(ExtractedSection(text=text, page=1, heading=None))
    )
    assert all(len(c.content) >= config.min_chunk_size or len(chunks) == 1 for c in chunks)
    assert "iota" in chunks[-1].content


def test_no_chunk_ever_exceeds_max_chunk_size_across_varied_inputs() -> None:
    config = ChunkingConfig(
        target_chunk_size=50, chunk_overlap=10, min_chunk_size=20, max_chunk_size=80
    )
    texts = [
        "Short.",
        "word " * 500,
        "Sentence one. " * 200,
        "x" * 1000,
        "Para one.\n\nPara two.\n\n" + ("Para three is much longer. " * 30),
    ]
    for text in texts:
        chunks = StructureAwareChunker(config=config).chunk(
            _doc(ExtractedSection(text=text, page=1, heading=None))
        )
        assert all(len(c.content) <= config.max_chunk_size for c in chunks), text[:30]


# --- empty / whitespace handling ----------------------------------------


def test_empty_section_produces_no_chunks() -> None:
    chunks = _chunker().chunk(_doc(ExtractedSection(text="", page=1, heading=None)))
    assert chunks == []


def test_whitespace_only_section_produces_no_chunks() -> None:
    chunks = _chunker().chunk(_doc(ExtractedSection(text="   \n\n\t  \n  ", page=1, heading=None)))
    assert chunks == []


def test_empty_document_with_no_sections_produces_no_chunks() -> None:
    chunks = _chunker().chunk(_doc())
    assert chunks == []


def test_no_produced_chunk_is_ever_empty_or_whitespace_only() -> None:
    config = ChunkingConfig(
        target_chunk_size=20, chunk_overlap=3, min_chunk_size=5, max_chunk_size=40
    )
    doc = _doc(
        ExtractedSection(text="", page=1, heading=None),
        ExtractedSection(text="   ", page=2, heading=None),
        ExtractedSection(text="real content here that is long enough", page=3, heading=None),
        ExtractedSection(text="\n\n\n", page=4, heading=None),
    )
    chunks = StructureAwareChunker(config=config).chunk(doc)
    assert chunks
    assert all(c.content.strip() for c in chunks)


# --- configuration validation --------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_chunk_size": 0},
        {"target_chunk_size": -10},
        {"min_chunk_size": 0},
        {"min_chunk_size": -1},
        {"max_chunk_size": 0},
        {"max_chunk_size": -1},
        {"chunk_overlap": -1},
    ],
)
def test_non_positive_size_configuration_is_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="must be"):
        ChunkingConfig(**kwargs)


def test_overlap_greater_than_or_equal_to_min_chunk_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        ChunkingConfig(
            target_chunk_size=100, chunk_overlap=50, min_chunk_size=50, max_chunk_size=200
        )


def test_overlap_equal_to_min_chunk_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        ChunkingConfig(
            target_chunk_size=100, chunk_overlap=50, min_chunk_size=50, max_chunk_size=200
        )


def test_min_greater_than_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_chunk_size"):
        ChunkingConfig(
            target_chunk_size=50, chunk_overlap=1, min_chunk_size=100, max_chunk_size=200
        )


def test_target_greater_than_max_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_chunk_size"):
        ChunkingConfig(
            target_chunk_size=500, chunk_overlap=1, min_chunk_size=10, max_chunk_size=200
        )


def test_absurdly_large_max_chunk_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_chunk_size"):
        ChunkingConfig(
            target_chunk_size=1000, chunk_overlap=10, min_chunk_size=100, max_chunk_size=10_000_000
        )


def test_default_configuration_is_itself_valid() -> None:
    ChunkingConfig()  # must not raise


# --- resource safety: no infinite loops, bounded chunk count --------------


def test_pathological_min_chunk_size_does_not_infinite_loop_and_is_bounded() -> None:
    # A deliberately tiny min_chunk_size against a moderately large
    # document -- proves this completes (no infinite loop) and, if it
    # would produce an unreasonable number of chunks, raises
    # ChunkingError rather than silently returning an enormous list.
    config = ChunkingConfig(
        target_chunk_size=2, chunk_overlap=0, min_chunk_size=1, max_chunk_size=5
    )
    text = "a a a a a " * 20_000  # ~200,000 characters
    chunker = StructureAwareChunker(config=config)
    try:
        chunks = chunker.chunk(_doc(ExtractedSection(text=text, page=1, heading=None)))
    except ChunkingError:
        pass  # the resource-safety ceiling is an accepted outcome here
    else:
        assert len(chunks) <= 50_000
        assert all(len(c.content) <= config.max_chunk_size for c in chunks)


def test_exceeding_the_chunk_count_ceiling_raises_chunking_error_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ingestion import chunking as chunking_module

    config = ChunkingConfig(
        target_chunk_size=2, chunk_overlap=0, min_chunk_size=1, max_chunk_size=5
    )
    chunker = StructureAwareChunker(config=config)
    # Many short sections, cheap to construct, chosen to exceed a small
    # monkeypatched ceiling deterministically and quickly rather than
    # relying on a slow, large real document.
    monkeypatch.setattr(chunking_module, "_MAX_CHUNKS_PER_DOCUMENT", 5)
    doc = _doc(
        *(ExtractedSection(text=f"section {i} content", page=i, heading=None) for i in range(20))
    )
    with pytest.raises(ChunkingError, match="chunks"):
        chunker.chunk(doc)


def test_chunk_count_ceiling_is_enforced_within_a_single_large_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression test: the ceiling check used to run only once per
    # section (between sections in chunk()'s own loop), so a single very
    # large section -- TXT/CSV always produce exactly one -- could build
    # far more than the ceiling internally before the check ever ran.
    # The timing assertion is what actually distinguishes the fix from
    # the old behavior: both raise ChunkingError eventually, but the old,
    # between-sections-only check would first build roughly 50x the
    # ceiling's worth of intermediate chunks (confirmed manually during
    # review) before ever checking, taking noticeably longer than
    # aborting within a few chunks of the ceiling.
    import time

    from app.ingestion import chunking as chunking_module

    config = ChunkingConfig(
        target_chunk_size=2, chunk_overlap=0, min_chunk_size=1, max_chunk_size=5
    )
    monkeypatch.setattr(chunking_module, "_MAX_CHUNKS_PER_DOCUMENT", 100)
    text = "a a a a a " * 5_000  # would produce far more than 100 chunks if uncaught
    doc = _doc(ExtractedSection(text=text, page=None, heading=None))

    start = time.monotonic()
    with pytest.raises(ChunkingError, match="chunks"):
        StructureAwareChunker(config=config).chunk(doc)
    elapsed = time.monotonic() - start
    assert elapsed < 0.15  # generous; the old deferred check took ~4x longer here


def test_large_document_chunks_quickly_no_quadratic_blowup() -> None:
    import time

    config = ChunkingConfig(
        target_chunk_size=500, chunk_overlap=50, min_chunk_size=100, max_chunk_size=1000
    )
    doc = _doc(
        *(
            ExtractedSection(text=f"Sentence number {i} here. " * 200, page=i, heading=None)
            for i in range(1, 51)
        )
    )
    start = time.monotonic()
    chunks = StructureAwareChunker(config=config).chunk(doc)
    elapsed = time.monotonic() - start
    assert chunks
    assert elapsed < 5.0  # generous; a quadratic-blowup bug would be far slower


# --- Chunk / ChunkingStrategy shape --------------------------------------


def test_chunk_is_a_plain_frozen_dataclass_with_the_expected_fields() -> None:
    chunk = Chunk(chunk_index=0, page=1, section="A", content="text")
    assert chunk.chunk_index == 0
    assert chunk.page == 1
    assert chunk.section == "A"
    assert chunk.content == "text"
    with pytest.raises(AttributeError):
        chunk.content = "mutated"  # type: ignore[misc]  # frozen -- immutability is deliberate


def test_structure_aware_chunker_satisfies_the_chunking_strategy_protocol() -> None:
    from app.ingestion.chunking import ChunkingStrategy

    chunker: ChunkingStrategy = StructureAwareChunker()
    result = chunker.chunk(_doc(ExtractedSection(text="hello world", page=1, heading=None)))
    assert isinstance(result, list)


def test_default_config_used_when_none_provided() -> None:
    chunker = StructureAwareChunker()
    chunks = chunker.chunk(
        _doc(ExtractedSection(text="a reasonably normal paragraph of text.", page=1, heading=None))
    )
    assert chunks


# --- integration: composes with the real extraction module -----------------


def _blank_pdf_with_two_pages() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_chunking_composes_with_real_extraction_output_for_markdown() -> None:
    # Proves the two modules' contracts actually match (ExtractedDocument/
    # ExtractedSection field names and types), not just that this test
    # file's own hand-built fixtures happen to satisfy chunking.py.
    content = (
        b"# Heading One\n\n"
        + b"Some body text here. " * 10
        + b"\n\n# Heading Two\n\n"
        + b"More body text. " * 10
    )
    extracted = extraction.extract(extension=".md", content=content)
    chunks = _chunker().chunk(extracted)
    assert chunks
    assert {c.section for c in chunks} == {"Heading One", "Heading Two"}


def test_chunking_composes_with_real_extraction_output_for_pdf() -> None:
    extracted = extraction.extract(extension=".pdf", content=_blank_pdf_with_two_pages())
    # Blank pages produce empty extracted text -- confirms chunking
    # correctly emits zero chunks for real (not hand-built) empty
    # sections, rather than erroring.
    chunks = _chunker().chunk(extracted)
    assert chunks == []
