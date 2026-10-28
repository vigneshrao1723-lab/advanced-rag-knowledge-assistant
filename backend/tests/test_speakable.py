"""What gets read aloud (app/voice/speakable.py)."""

from __future__ import annotations

from app.voice.speakable import CODE_ON_SCREEN, REST_ON_SCREEN, speakable_text

ANSWER = """**What it does**: Program 3 sorts an array using bubble sort. [1]

### How it works
1. The outer loop runs `n-1` times. [1]
2. The inner loop compares neighbours.

```c
void bubble_sort(int a[], int n) {
    for (int i = 0; i < n; i++) {}
}
```

**Output**: it prints `1 2 4 5 8`.

**Line by line**
- `void bubble_sort(int a[], int n) {` — Defines the function. [1]

**Original code from the document** [1]
```c
void bubble_sort(int a[], int n) {}
```"""


def test_keeps_the_explanation_and_drops_markup_citations_and_code() -> None:
    spoken = speakable_text(ANSWER)

    assert "Program 3 sorts an array using bubble sort." in spoken
    assert "The outer loop runs n-1 times." in spoken
    assert "it prints 1 2 4 5 8." in spoken
    for noise in ("**", "`", "###", "[1]", "void bubble_sort", "for (int i"):
        assert noise not in spoken
    assert spoken.count(CODE_ON_SCREEN) == 1


def test_stops_before_the_reference_sections_and_says_so() -> None:
    spoken = speakable_text(ANSWER)

    assert "Defines the function" not in spoken
    assert spoken.endswith(REST_ON_SCREEN)


def test_long_answers_are_cut_at_a_sentence_boundary() -> None:
    long = " ".join(f"Sentence number {i} explains something." for i in range(200))

    spoken = speakable_text(long, max_chars=300)

    assert len(spoken) <= 300 + len(REST_ON_SCREEN) + 1
    assert spoken.endswith(f"explains something. {REST_ON_SCREEN}")


def test_short_plain_text_is_left_alone() -> None:
    text = "The refund window is thirty days."
    assert speakable_text(text) == text


def test_an_unterminated_code_fence_never_gets_read_out() -> None:
    spoken = speakable_text("Here is the code:\n```c\nint main() {\n    return 0;")

    assert "int main" not in spoken and CODE_ON_SCREEN in spoken


def test_empty_input() -> None:
    assert speakable_text("") == ""
