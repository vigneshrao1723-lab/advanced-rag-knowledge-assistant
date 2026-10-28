"""Pure parsing of what a question points at (app/retrieval/references.py)."""

from __future__ import annotations

import uuid

import pytest

from app.retrieval.references import (
    Locator,
    content_terms,
    heading_pattern,
    is_followup,
    match_documents,
    parse_locator,
    shares_content_terms,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Explain Program 1 from my uploaded PC Lab PDF.", Locator("program", number=1)),
        ("explain program number 5", Locator("program", number=5)),
        ("Explain programme no. 7 please", Locator("program", number=7)),
        ("what does Exercise 3 ask?", Locator("exercise", number=3)),
        ("Explain the first program in my PC lab PDF", Locator("program", ordinal=1)),
        ("explain the second MPI program", Locator("program", ordinal=2)),
        ("show the last program", Locator("program", ordinal=-1)),
        ("explain the 3rd experiment", Locator("experiment", ordinal=3)),
        ("Question 12 answer?", Locator("question", number=12)),
    ],
)
def test_parse_locator_variants(query: str, expected: Locator) -> None:
    assert parse_locator(query) == expected


@pytest.mark.parametrize(
    "query",
    ["What is the refund policy?", "explain this code line by line", "program output", "page 4"],
)
def test_parse_locator_ignores_questions_without_a_label(query: str) -> None:
    assert parse_locator(query) is None


def test_headings_match_items_but_not_ranges_or_mentions() -> None:
    pattern = heading_pattern("program")
    text = (
        "MPI Lab Programs 5 to 9\nProgram 5: MPI_Send\nsee Program 6 for more\n"
        "## Program 7\n**Program 8**\nPrograms 1 and 2\n   Program 9 - Reduce"
    )
    assert [m.group("num") for m in pattern.finditer(text)] == ["5", "7", "8", "9"]


def test_match_documents_by_filename_words() -> None:
    lab, notes, specs = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    docs = [(lab, "PC_LAB_TEST.pdf"), (notes, "OS notes.pdf"), (specs, "product_specs.txt")]

    assert match_documents("Explain program 1 from my PC lab PDF", docs) == [lab]
    assert match_documents("explain PC_LAB_TEST.pdf", docs) == [lab]
    assert match_documents("what is in the product specs?", docs) == [specs]
    assert match_documents("what is the refund policy?", docs) == []
    # One shared generic word is not enough to pick a file.
    assert match_documents("run the test again", docs) == []


def test_match_documents_reports_ties() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    docs = [(a, "Lab Manual 2023.pdf"), (b, "Lab Manual 2024.pdf")]
    assert set(match_documents("explain the lab manual", docs)) == {a, b}


def test_single_word_filenames_match_when_quoted() -> None:
    handbook = uuid.uuid4()
    assert match_documents("summarise the handbook", [(handbook, "handbook.docx")]) == [handbook]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("explain that line by line", True),
        ("now as a beginner", True),
        ("why?", True),
        ("give me a short exam-ready explanation", True),
        ("What is the refund policy for returns within thirty days of purchase today?", False),
        ("Explain Program 5", False),
    ],
)
def test_is_followup(query: str, expected: bool) -> None:
    assert is_followup(query) is expected


def test_content_terms_drop_command_words_and_stem_to_prefixes() -> None:
    assert content_terms("Explain the rotation of production credentials") == {
        "rotat", "produ", "crede",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("query", "passage", "expected"),
    [
        ("How often are credentials rotated?", "Credentials must be rotated every 90 days.", True),
        ("What is the capital of Atlantis?", "Orion launches from Kourou in March.", False),
        ("What is the meaning of life?", "The Vega station is in Tromso.", False),
        ("Explain it", "anything at all", True),  # no content words: never discard evidence
        ("What does the document say?", "Visitors must wear a badge.", True),  # meta question
        ("Summarise the main points", "The Vega station is in Tromso.", True),
    ],
)
def test_shares_content_terms(query: str, passage: str, expected: bool) -> None:
    assert shares_content_terms(query, passage) is expected
