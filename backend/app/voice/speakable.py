"""Turns a written answer into something sensible to *read aloud*.

An answer is Markdown: headings, bullet lists, fenced code, `[n]` citation
markers, a line-by-line table and the original listing. Read verbatim by a
speech synthesiser that is gibberish ("backtick backtick c hash include..."),
so spoken output keeps the explanation, replaces code with a short pointer to
the screen, and stops before the long reference sections. The text on screen
is unchanged. The browser has an equivalent (`frontend/lib/speakable.ts`); the
two are kept in step by their tests.
"""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
# Reference sections appended after the explanation: not worth hearing.
_REFERENCE_SECTION_RE = re.compile(
    r"\n\s*\*\*(?:Line by line|Original code from the document)\*\*", re.IGNORECASE
)
_CITATION_RE = re.compile(r"\s*\[\d{1,3}\]")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s")

CODE_ON_SCREEN = "The code is shown on screen."
REST_ON_SCREEN = "The rest is on screen."
DEFAULT_MAX_CHARS = 1100


def speakable_text(markdown: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    cut = _REFERENCE_SECTION_RE.search(markdown)
    text = markdown[: cut.start()] if cut else markdown
    had_reference_section = cut is not None

    text = _FENCE_RE.sub(f" {CODE_ON_SCREEN} ", text)
    text = text.replace("`", "")
    text = _CITATION_RE.sub("", text)
    text = _HEADING_RE.sub("", text)
    text = _LIST_MARKER_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    # Line breaks become sentence breaks so list items are not run together.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = " ".join(line if line.endswith((".", "!", "?", ":")) else line + "." for line in lines)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?:\b" + re.escape(CODE_ON_SCREEN) + r"\s*){2,}", CODE_ON_SCREEN + " ", text)

    truncated = False
    if len(text) > max_chars:
        window = text[:max_chars]
        ends = [m.end() for m in _SENTENCE_END_RE.finditer(window)]
        text = window[: ends[-1]].strip() if ends else window.rstrip()
        truncated = True
    if truncated or had_reference_section:
        text = f"{text} {REST_ON_SCREEN}".strip()
    return text


__all__ = ["CODE_ON_SCREEN", "REST_ON_SCREEN", "speakable_text"]
