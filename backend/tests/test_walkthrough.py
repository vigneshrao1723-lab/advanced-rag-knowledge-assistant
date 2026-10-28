"""Structural line-by-line walkthrough (app/generation/walkthrough.py)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from app.generation.context_builder import ContextBlock
from app.generation.fidelity import find_code_regions
from app.generation.prompts import ChatTurn, build_system_prompt
from app.generation.service import generate_answer
from app.generation.walkthrough import (
    build_walkthrough,
    clean_explanation,
    wants_line_by_line,
)
from app.retrieval.types import RetrievalCandidate

CODE = """Program 3: Bubble sort
#include <stdio.h>
void bubble_sort(int a[], int n) {
    for (int i = 0; i < n - 1; i++) {
        if (a[i] > a[i + 1]) {
            int t = a[i];
        }
    }
}
"""


class NumberingProvider:
    """Answers walkthrough calls like a well-behaved model and the main call
    with a short overview. `skip` lists line numbers it 'forgets'."""

    model_name = "scripted"
    model_version = "t"
    is_generative = True

    def __init__(self, skip: Sequence[int] = ()) -> None:
        self.calls: list[tuple[str, str]] = []
        self.skip = set(skip)

    def generate(
        self, *, system_prompt: str, context: str, query: str, history: Sequence[ChatTurn] = ()
    ) -> str:
        self.calls.append((system_prompt, context))
        if "numbered line" in system_prompt:
            rows = re.findall(r"^(\d+): (.*)$", context, re.MULTILINE)
            return "\n".join(
                f"{n}: Explains `{text}`." for n, text in rows if int(n) not in self.skip
            )
        return "It sorts an array. [1]"


def _blocks() -> list[ContextBlock]:
    candidate = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        content=CODE,
        page=3,
        section=None,
        score=1.0,
    )
    return [ContextBlock(marker=1, candidate=candidate)]


def test_trigger_phrases() -> None:
    for query in (
        "explain this code line by line",
        "Explain statement by statement",
        "explain each line",
    ):
        assert wants_line_by_line(query)
    assert not wants_line_by_line("explain program 3")


def test_every_code_line_gets_an_explanation_in_order_across_groups() -> None:
    provider = NumberingProvider()
    regions = find_code_regions(_blocks())

    text = build_walkthrough(regions, provider) or ""

    bullets = text.splitlines()
    assert len(bullets) == 8  # 8 non-blank code lines, 2 model calls (6 + 2)
    assert len(provider.calls) == 2
    assert bullets[0].startswith("- `#include <stdio.h>` — Explains")
    assert bullets[-1].startswith("- `}` —")
    assert all(b.endswith("[1]") for b in bullets)


def test_a_line_the_model_skips_is_reported_not_dropped() -> None:
    text = build_walkthrough(find_code_regions(_blocks()), NumberingProvider(skip=[2])) or ""

    assert "(no explanation was generated for this line)" in text.splitlines()[1]
    assert len(text.splitlines()) == 8


def test_no_code_means_no_walkthrough() -> None:
    assert build_walkthrough([], NumberingProvider()) is None


def test_the_walkthrough_call_treats_the_code_as_untrusted_evidence() -> None:
    provider = NumberingProvider()
    build_walkthrough(find_code_regions(_blocks()), provider)

    system, context = provider.calls[0]
    assert "untrusted data" in system
    assert "#include <stdio.h>" in context and "#include" not in system


def test_system_prompt_asks_for_overview_only_when_a_walkthrough_is_added() -> None:
    plain = build_system_prompt("explain it line by line")
    added = build_system_prompt("explain it line by line", walkthrough_added=True)

    assert "cover EVERY line" in plain
    assert "do NOT walk through the lines yourself" in added


def test_generate_answer_assembles_overview_walkthrough_and_original_code() -> None:
    provider = NumberingProvider()
    candidate = _blocks()[0].candidate

    answer, context = generate_answer(
        query="Explain program 3 line by line",
        candidates=[candidate],
        llm_provider=provider,
        cite_all=True,
    )

    assert answer.startswith("It sorts an array. [1]")
    assert "**Line by line**" in answer
    assert "- `for (int i = 0; i < n - 1; i++) {` — Explains" in answer
    assert "**Original code from the document** [1]" in answer
    assert "        if (a[i] > a[i + 1]) {" in answer  # exact indentation in the listing
    assert [b.marker for b in context.blocks] == [1]


def test_other_questions_do_not_trigger_extra_model_calls() -> None:
    provider = NumberingProvider()
    generate_answer(
        query="Explain program 3", candidates=[_blocks()[0].candidate], llm_provider=provider
    )
    assert len(provider.calls) == 1


def test_template_echo_and_code_repeats_are_removed_from_explanations() -> None:
    echoed = clean_explanation("N: explanation Declares two ints.", "int a, b;")
    assert echoed == "Declares two ints."
    assert clean_explanation("int a, b;: Declares two ints.", "int a, b;") == "Declares two ints."
    assert clean_explanation("Explanation: Closes the block.", "}") == "Closes the block."
    assert clean_explanation("Returns zero.", "return 0;") == "Returns zero."
    assert clean_explanation("return 0;", "return 0;") == ""  # nothing left: reported as missing
