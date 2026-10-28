"""Code-fidelity guard for generative answers (ADR 0009).

A small language model asked to "show the code" re-types it: it reorders
declarations, drops lines and changes indentation, and the user cannot tell.
Rather than trusting the prompt, this module checks every fenced code block
in the answer against the evidence text the answer was built from:

- every line found (in order) in the evidence -> the block is *verified* and
  its lines are replaced by the evidence's exact lines (restoring original
  indentation);
- mostly found but altered or reordered -> the block is replaced by the
  contiguous verbatim slice of the evidence;
- mostly not found (an illustration, or output derived from the code) -> left
  as written;

and, when the question is about code and the answer did not reproduce a code
region of the evidence faithfully, the original region is appended under its
own heading. Pure functions; no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.generation.context_builder import ContextBlock

_FENCE_RE = re.compile(r"```[ \t]*([\w+#.-]*)[ \t]*\n(.*?)(?:\n[ \t]*```|\Z)", re.DOTALL)
_CODE_ENDINGS = (";", "{", "}", "*/")
_CODE_STARTS = (
    "#include", "#define", "import ", "from ", "def ", "class ", "public ", "private ",
    "static ", "for ", "for(", "while ", "while(", "if ", "if(", "else", "return", "//",
    "int ", "void ", "char ", "float ", "double ", "long ", "struct ", "try", "catch",
)  # fmt: skip
# Only a question about the whole program/code warrants appending the full
# original listing; narrow questions ("explain this loop", "what does it
# print") do not.
_WHOLE_CODE_QUESTION_RE = re.compile(
    r"\b(programs?|programme|code|listing|script|source|algorithm|experiment|practical|snippet)\b",
    re.IGNORECASE,
)
_MIN_REGION_CODE_LINES = 3
_REPLACE_THRESHOLD = 0.5
_ALREADY_SHOWN_THRESHOLD = 0.8


def _norm(line: str) -> str:
    return " ".join(line.split())


def _is_code_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return stripped.endswith(_CODE_ENDINGS) or stripped.startswith(_CODE_STARTS)


@dataclass(frozen=True)
class CodeRegion:
    block_marker: int
    lines: tuple[str, ...]  # raw lines, original indentation


def find_code_regions(blocks: Sequence[ContextBlock]) -> list[CodeRegion]:
    """Maximal runs of code-looking lines (blank lines and lone brace/keyword
    lines inside a run are kept) with at least a few real code lines."""
    regions: list[CodeRegion] = []
    for block in blocks:
        lines = block.candidate.content.split("\n")
        run: list[str] = []
        code_count = 0

        def flush(run: list[str], code_count: int, marker: int = block.marker) -> None:
            while run and not run[-1].strip():
                run.pop()
            if code_count >= _MIN_REGION_CODE_LINES and run:
                regions.append(CodeRegion(marker, tuple(run)))

        for line in lines:
            if _is_code_line(line):
                run.append(line)
                code_count += 1
            elif not line.strip() and run:
                run.append(line)
            elif line.startswith((" ", "\t")) and run and line.strip():
                run.append(line)  # indented continuation inside a run
                code_count += 1
            else:
                flush(run, code_count)
                run, code_count = [], 0
        flush(run, code_count)
    return regions


def _match_in_order(model_lines: list[str], evidence_lines: list[str]) -> list[int]:
    """Greedy in-order match of normalised lines; returns the evidence index
    per matched model line (skipping model lines with no later match)."""
    norm_evidence = [_norm(line) for line in evidence_lines]
    positions: list[int] = []
    cursor = 0
    for line in model_lines:
        target = _norm(line)
        for index in range(cursor, len(norm_evidence)):
            if norm_evidence[index] == target:
                positions.append(index)
                cursor = index + 1
                break
    return positions


def _repair_block(code: str, blocks: Sequence[ContextBlock]) -> str:
    model_lines = [line for line in code.split("\n") if line.strip()]
    if not model_lines:
        return code
    best: tuple[int, list[int], list[str]] | None = None  # (matched, positions, evidence_lines)
    for block in blocks:
        evidence_lines = block.candidate.content.split("\n")
        positions = _match_in_order(model_lines, evidence_lines)
        if best is None or len(positions) > best[0]:
            best = (len(positions), positions, evidence_lines)
    if best is None or best[0] == 0:
        return code
    matched, positions, evidence_lines = best
    coverage = matched / len(model_lines)
    if matched == len(model_lines):
        # Verified (possibly an excerpt): restore the exact original lines.
        return "\n".join(evidence_lines[i] for i in positions)
    if coverage >= _REPLACE_THRESHOLD:
        # Altered/reordered: show the contiguous verbatim slice instead.
        return "\n".join(evidence_lines[positions[0] : positions[-1] + 1])
    return code


def _guess_language(lines: Sequence[str]) -> str:
    text = "\n".join(lines)
    if "#include" in text:
        return "cpp" if ("std::" in text or "cout" in text) else "c"
    if re.search(r"^\s*(def |import |from \w+ import )", text, re.MULTILINE):
        return "python"
    if re.search(r"\b(public|private)\s+(static\s+)?(class|void|int)\b", text):
        return "java"
    return ""


def _shown_fraction(region: CodeRegion, answer_blocks: Sequence[str]) -> float:
    wanted = {_norm(line) for line in region.lines if line.strip()}
    if not wanted:
        return 1.0
    shown = {_norm(line) for code in answer_blocks for line in code.split("\n") if line.strip()}
    return len(wanted & shown) / len(wanted)


def enforce_code_fidelity(
    answer: str, blocks: Sequence[ContextBlock], query: str
) -> str:
    """Returns `answer` with its code blocks verified/repaired against the
    evidence, plus the original code appended when appropriate (see module
    docstring). Answers without code and evidence without code regions pass
    through unchanged."""
    if not blocks:
        return answer

    def repl(match: re.Match[str]) -> str:
        lang, code = match.group(1), match.group(2)
        return f"```{lang}\n{_repair_block(code, blocks)}\n```"

    repaired = _FENCE_RE.sub(repl, answer)

    regions = find_code_regions(blocks)
    if not regions:
        return repaired
    if not _WHOLE_CODE_QUESTION_RE.search(query):
        return repaired
    answer_codes = [m.group(2) for m in _FENCE_RE.finditer(repaired)]

    missing = [r for r in regions if _shown_fraction(r, answer_codes) < _ALREADY_SHOWN_THRESHOLD]
    if not missing:
        return repaired
    parts = [repaired.rstrip()]
    for region in missing:
        language = _guess_language(region.lines)
        parts.append("")
        parts.append(f"**Original code from the document** [{region.block_marker}]")
        parts.append(f"```{language}\n" + "\n".join(region.lines) + "\n```")
    return "\n".join(parts)


__all__ = ["CodeRegion", "enforce_code_fidelity", "find_code_regions"]
