"""Unit tests for `app.ingestion.cleaning` (Issue #3, Slice 3.6). Pure
`ExtractedDocument -> ExtractedDocument` transformation — no database,
HTTP, or filesystem.
"""

from __future__ import annotations

from app.ingestion.cleaning import clean
from app.ingestion.extraction import ExtractedDocument, ExtractedSection


def _doc(*sections: ExtractedSection) -> ExtractedDocument:
    return ExtractedDocument(sections=list(sections))


def test_crlf_and_cr_line_endings_are_normalized_to_lf() -> None:
    text = "Line one.\r\nLine two.\rLine three.\r\n"
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert "\r" not in result.sections[0].text
    assert result.sections[0].text == "Line one.\nLine two.\nLine three."


def test_trailing_whitespace_per_line_is_stripped() -> None:
    text = "Line one.   \nLine two.\t\t\nLine three."
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert result.sections[0].text == "Line one.\nLine two.\nLine three."


def test_leading_and_trailing_section_whitespace_is_stripped() -> None:
    text = "   \n\nActual content.\n\n   "
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert result.sections[0].text == "Actual content."


def test_excess_blank_lines_collapse_to_exactly_one() -> None:
    text = "Para one.\n\n\n\n\nPara two."
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert result.sections[0].text == "Para one.\n\nPara two."


def test_single_blank_line_is_preserved_not_removed() -> None:
    # A single blank line still marks a real paragraph break for
    # chunking.py's own boundary detection -- must not be collapsed away.
    text = "Para one.\n\nPara two."
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert "\n\n" in result.sections[0].text
    assert result.sections[0].text == text


def test_within_line_whitespace_is_never_touched() -> None:
    # Only line/blank-line *structure* is normalized -- spacing between
    # words on the same line is left completely alone.
    text = "word1   word2\tword3     word4"
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert result.sections[0].text == text


def test_punctuation_and_semantic_content_are_never_removed() -> None:
    text = "Hello, world! Is this correct? Yes... (definitely) [confirmed]."
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert result.sections[0].text == text


def test_unicode_content_is_fully_preserved() -> None:
    text = "தமிழ் text.\r\n\r\nಕನ್ನಡ text.\r\n\r\n\r\nहिन्दी emoji 😀👨‍👩‍👧‍👦"
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert "தமிழ்" in result.sections[0].text
    assert "ಕನ್ನಡ" in result.sections[0].text
    assert "हिन्दी" in result.sections[0].text
    assert "😀" in result.sections[0].text
    assert "👨‍👩‍👧‍👦" in result.sections[0].text


def test_combining_characters_are_preserved() -> None:
    text = "é" * 10  # e + combining acute accent, repeated
    result = clean(_doc(ExtractedSection(text=text, page=1, heading=None)))
    assert result.sections[0].text == text


def test_page_and_heading_metadata_pass_through_unchanged() -> None:
    result = clean(_doc(ExtractedSection(text="content", page=5, heading="Intro")))
    assert result.sections[0].page == 5
    assert result.sections[0].heading == "Intro"


def test_page_count_passes_through_unchanged() -> None:
    doc = ExtractedDocument(
        sections=[ExtractedSection(text="a", page=1, heading=None)], page_count=7
    )
    result = clean(doc)
    assert result.page_count == 7


def test_multiple_sections_each_cleaned_independently() -> None:
    doc = _doc(
        ExtractedSection(text="One.\r\n\r\n\r\n\r\nTwo.", page=1, heading=None),
        ExtractedSection(text="Three.   \nFour.", page=2, heading=None),
    )
    result = clean(doc)
    assert result.sections[0].text == "One.\n\nTwo."
    assert result.sections[1].text == "Three.\nFour."


def test_empty_section_remains_empty_after_cleaning() -> None:
    result = clean(_doc(ExtractedSection(text="", page=1, heading=None)))
    assert result.sections[0].text == ""


def test_whitespace_only_section_becomes_empty_after_cleaning() -> None:
    result = clean(_doc(ExtractedSection(text="   \r\n\r\n\t  ", page=1, heading=None)))
    assert result.sections[0].text == ""


def test_empty_document_with_no_sections_stays_empty() -> None:
    result = clean(_doc())
    assert result.sections == []


def test_cleaning_is_deterministic_for_identical_input() -> None:
    doc = _doc(ExtractedSection(text="A.\r\n\r\n\r\nB.   \n\nC.", page=1, heading="H"))
    first = clean(doc)
    second = clean(doc)
    assert first == second


def test_cleaning_is_idempotent() -> None:
    # Cleaning an already-clean document a second time must be a no-op --
    # a real property for a "safe normalization" stage: it should
    # converge, not keep transforming content on repeated application.
    doc = _doc(ExtractedSection(text="A.\r\n\r\n\r\nB.   \n\nC.", page=1, heading="H"))
    once = clean(doc)
    twice = clean(once)
    assert once == twice
