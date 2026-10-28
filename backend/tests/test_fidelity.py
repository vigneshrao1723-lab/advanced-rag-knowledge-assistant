"""Code-fidelity guard (app/generation/fidelity.py): a generative answer's
code blocks are checked against the evidence, never trusted."""

from __future__ import annotations

import uuid

from app.generation.context_builder import ContextBlock
from app.generation.fidelity import enforce_code_fidelity, find_code_regions
from app.retrieval.types import RetrievalCandidate

CODE = """Program 2: Sum with MPI_Reduce
Aim: add the numbers.

#include <mpi.h>
int main(int argc, char *argv[]) {
    int rank, local = 0, total = 0;
    MPI_Init(&argc, &argv);
    for (int i = 0; i < 2; i++) {
        local += i;
    }
    MPI_Reduce(&local, &total, 1, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD);
    return 0;
}

Output:
Total = 36"""


def _block(content: str, marker: int = 1) -> ContextBlock:
    candidate = RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        content=content,
        page=1,
        section=None,
        score=1.0,
    )
    return ContextBlock(marker=marker, candidate=candidate)


def test_regions_are_code_only_not_prose_or_output() -> None:
    regions = find_code_regions([_block(CODE)])

    assert len(regions) == 1
    text = "\n".join(regions[0].lines)
    assert text.startswith("#include <mpi.h>") and text.rstrip().endswith("}")
    assert "Aim:" not in text and "Total = 36" not in text
    assert "        local += i;" in text  # original indentation kept


def test_prose_lines_ending_in_a_closing_paren_and_colon_are_not_code() -> None:
    # Regression (found with the real model): "Output (run with 4 processes):"
    # was classified as code and swallowed into the appended listing.
    result = enforce_code_fidelity("Adds numbers. [1]", [_block(CODE)], "Explain program 2")

    assert "run with 4 processes" not in result.split("**Original code")[1]
    block = _block("Program 1\nint x;\nint y;\nreturn 0;\n\nOutput (run with 3 processes):\nHi")
    assert all("Output" not in "\n".join(r.lines) for r in find_code_regions([block]))


def test_flat_but_correct_block_gets_its_original_indentation_back() -> None:
    answer = "Explanation.\n```c\nfor (int i = 0; i < 2; i++) {\nlocal += i;\n}\n```"

    fixed = enforce_code_fidelity(answer, [_block(CODE)], "explain this loop")

    assert "```c\n    for (int i = 0; i < 2; i++) {\n        local += i;\n    }\n```" in fixed
    assert "Original code from the document" not in fixed  # narrow question: no appendix


def test_altered_or_reordered_block_is_replaced_by_the_verbatim_slice() -> None:
    altered = (
        "```c\nint main(int argc, char *argv[]) {\n"
        "    int rank, size;\n"  # invented
        "    MPI_Init(&argc, &argv);\n"
        "    return 0;\n}\n```"
    )

    fixed = enforce_code_fidelity("Here:\n" + altered, [_block(CODE)], "explain program 2")

    assert "int rank, size;" not in fixed
    assert "    int rank, local = 0, total = 0;" in fixed
    assert "MPI_Reduce(&local, &total" in fixed  # the contiguous original slice


def test_derived_output_and_illustrations_are_left_alone() -> None:
    answer = "It prints:\n```\nTotal = 99\n```"

    assert enforce_code_fidelity(answer, [_block(CODE)], "what does it print") == answer


def test_original_code_is_appended_when_the_answer_omitted_it() -> None:
    answer = "It adds numbers and reduces them to rank 0. [1]"

    result = enforce_code_fidelity(answer, [_block(CODE)], "Explain program 2")

    assert result.startswith(answer)
    assert "**Original code from the document** [1]\n```c\n#include <mpi.h>" in result
    assert result.rstrip().endswith("```")  # the fence is closed
    assert "```c\n#include <mpi.h>" in result
    assert "        local += i;" in result
    assert "Total = 36" not in result


def test_original_code_is_not_duplicated_when_the_answer_already_shows_it() -> None:
    shown = "See:\n```c\n" + CODE.split("\n\n")[1] + "\n```"
    result = enforce_code_fidelity(shown, [_block(CODE)], "Explain program 2")
    assert "Original code from the document" not in result


def test_narrow_questions_do_not_trigger_the_full_listing() -> None:
    for question in ("what does it print", "why is there a loop", "explain this line"):
        result = enforce_code_fidelity("Short answer. [1]", [_block(CODE)], question)
        assert "Original code from the document" not in result


def test_prose_question_without_code_in_answer_gets_no_appendix() -> None:
    answer = "The budget is four million dollars. [1]"

    assert enforce_code_fidelity(answer, [_block(CODE)], "what is the budget?") == answer


def test_no_code_in_evidence_and_no_blocks_pass_through() -> None:
    prose = _block("Visitors must wear a badge. Badges are issued at the front desk.")
    answer = "Wear a badge. [1]"
    assert enforce_code_fidelity(answer, [prose], "explain the code") == answer
    assert enforce_code_fidelity(answer, [], "explain the code") == answer
