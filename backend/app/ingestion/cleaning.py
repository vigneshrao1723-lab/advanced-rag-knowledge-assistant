"""Document content cleaning (Issue #3, Slice 3.6).

Deterministic, conservative, loss-minimizing normalization applied to an
already-extracted `ExtractedDocument` before chunking. Pure, in-memory
transformation only -- no database/HTTP/filesystem dependency, matching
`extraction.py`'s and `chunking.py`'s own established shape:

    ExtractedDocument -> clean() -> ExtractedDocument

Deliberately minimal: this stage exists because the documented ingestion
state machine (`docs/RAG_DESIGN.md`, `UPLOADED -> ... -> PARSED ->
CLEANED -> CHUNKED`) names it as a distinct step, not because this
project's current requirements specify any content transformation
beyond what `extraction.py` already guarantees (safe decoding, structure
preservation). What it does, and why each is safe:

- Normalizes line endings (`\r\n`/`\r` -> `\n`) -- a document extracted
  from a Windows-authored source could carry literal `\r` characters
  through to this stage; normalizing here keeps that assumption
  explicit and centralized, rather than each downstream consumer
  needing to tolerate it independently.
- Strips trailing whitespace from each line, and leading/trailing
  whitespace from the section as a whole.
- Collapses a run of 3 or more consecutive blank lines down to exactly
  one blank line (two newlines) -- a single blank line still marks a
  paragraph break for `chunking.py`'s own boundary detection; nothing
  meaningful is lost by bounding how many *consecutive* blank lines
  survive, since the run itself carries no additional information once
  it exceeds one.

What this deliberately does NOT do: rewrite, summarize, translate, or
otherwise alter the actual words of the document; remove punctuation or
any semantic content; collapse whitespace *within* a line (a single
space between words is already meaningful and left untouched -- only
line-ending and blank-line *structure* is normalized); apply any
Unicode normalization form or strip characters based on script/category
(Tamil, Kannada, Hindi, emoji, CJK, combining-character sequences all
pass through completely unchanged, verified in tests). No LLM or
external service is used or implied anywhere in this module.

Total function, not expected to raise: every operation here is a
regex substitution or plain string method over a `str` that
`extraction.py` has already produced safely (never raw untrusted
bytes) -- there is no I/O, no recursion, no external call. Any
unexpected failure is still the caller's responsibility to handle
defensively (see `document_service.py`'s generic exception handling for
the extraction/chunking stages, applied identically here), not a reason
to add a dedicated exception type this module would never actually
raise.
"""

from __future__ import annotations

import re

from app.ingestion.extraction import ExtractedDocument, ExtractedSection

_CRLF_OR_CR_RE = re.compile(r"\r\n?")
# Matches a newline followed by two or more further blank-ish newline
# groups -- i.e. three or more consecutive line breaks -- so it can be
# collapsed to exactly two (one blank line).
_EXCESS_BLANK_LINES_RE = re.compile(r"\n[ \t]*(?:\n[ \t]*){2,}")


def clean(document: ExtractedDocument) -> ExtractedDocument:
    """Returns a new `ExtractedDocument` with each section's `text`
    cleaned; `page`/`heading` metadata and `page_count` pass through
    unchanged -- cleaning only ever touches content, never metadata."""
    return ExtractedDocument(
        sections=[_clean_section(section) for section in document.sections],
        page_count=document.page_count,
    )


def _clean_section(section: ExtractedSection) -> ExtractedSection:
    text = _CRLF_OR_CR_RE.sub("\n", section.text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _EXCESS_BLANK_LINES_RE.sub("\n\n", text)
    text = text.strip()
    return ExtractedSection(text=text, page=section.page, heading=section.heading)


__all__ = ["clean"]
