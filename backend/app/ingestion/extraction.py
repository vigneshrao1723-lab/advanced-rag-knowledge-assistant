"""Text extraction (Issue #3, Slice 3.4).

Parses the bytes a document was uploaded with (Slice 3.3) into a
structured, in-memory representation — headings/pages, not just a flat
text blob, per the documented ingestion-pipeline requirement. This
module never touches the filesystem, StorageProvider, or the database
directly; it is a pure function of (extension, bytes) -> ExtractedDocument
(or a raised ExtractionError), so it can be unit-tested without any of
those, and so the orchestration layer (app/services/document_service.py)
stays the only place that knows about documents/storage/audit.

Every uploaded file is untrusted input. Every format here is bounded:
input size is already capped at upload time (Slice 3.3,
`max_upload_size_bytes`); output text is capped again here
(`_MAX_EXTRACTED_TEXT_BYTES`) so a pathological-but-valid file can't
amplify into unbounded memory; DOCX additionally gets a pre-flight ZIP
safety check (member count, per-member and total uncompressed size,
member-name traversal) before python-docx ever touches it, since a ZIP
container's compressed size says nothing about its expansion cost.

No parser failure is allowed to propagate a raw exception, a filesystem
path, or an internal stack trace past this module — every failure path
raises `ExtractionError` with a short, generic reason string safe to
store in `documents.failure_reason` and eventually show a user.

Deliberately not implemented here: chunking, embeddings, any state
transition, any I/O. Those are later slices' or the orchestration
layer's job, not this one's.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Final

import docx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Output bound, independent of the (already-enforced) input bound — a
# small-but-pathological input could still expand into more extracted
# text than is sensible to hold in memory or eventually chunk from.
_MAX_EXTRACTED_TEXT_BYTES: Final = 20 * 1024 * 1024  # 20 MiB of text

# PDF: bounds worst-case iteration over a pathological page count.
_MAX_PDF_PAGES: Final = 2000

# DOCX is a ZIP container — its compressed size on disk (already capped
# at 50 MiB by the upload limit) says nothing about how much memory
# fully decompressing every member would take. All three limits below
# are checked from ZipInfo metadata alone (no member is actually read)
# before python-docx is ever invoked.
_MAX_DOCX_MEMBER_COUNT: Final = 2000
_MAX_DOCX_MEMBER_UNCOMPRESSED_BYTES: Final = 50 * 1024 * 1024  # 50 MiB, any one member
_MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES: Final = 200 * 1024 * 1024  # 200 MiB, all members


class ExtractionError(Exception):
    """Any extraction failure — malformed input, an unsupported/unknown
    extension, a resource limit exceeded, or a parser library raising
    something unexpected. Always a short, generic, storage-safe message
    — never the parser's own exception text, never a filesystem path."""


@dataclass
class ExtractedSection:
    text: str
    page: int | None = None
    heading: str | None = None


@dataclass
class ExtractedDocument:
    sections: list[ExtractedSection] = field(default_factory=list)
    page_count: int | None = None

    @property
    def full_text(self) -> str:
        return "\n\n".join(section.text for section in self.sections if section.text)


def _truncate_to_budget(text: str, *, max_bytes: int) -> tuple[str, int]:
    """Truncates `text` to at most `max_bytes` of UTF-8-encoded output, on
    a UTF-8 boundary (never raising on a split multibyte sequence).
    Returns `(truncated_text, actual_encoded_byte_length)` so a caller can
    accumulate a running total across multiple sections/pages -- a single
    per-call cap is not the same thing as a per-*document* cap when a
    format can produce more than one section (see `_extract_pdf`/
    `_extract_docx`/`_extract_markdown` below, each of which tracks a
    running total; only formats that always produce exactly one section,
    like TXT, can safely use `_enforce_text_budget` alone).
    """
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, len(encoded)
    # Truncate on a UTF-8 boundary rather than raise: a very large but
    # genuinely valid document still produces useful, bounded output,
    # rather than being treated as an outright failure.
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, len(truncated.encode("utf-8"))


def _enforce_text_budget(text: str) -> str:
    truncated, _ = _truncate_to_budget(text, max_bytes=_MAX_EXTRACTED_TEXT_BYTES)
    return truncated


# --- Code-aware page text --------------------------------------------------
#
# pypdf's default `extract_text()` returns text in content-stream order and
# drops horizontal positioning, so a PDF that places code with positioning
# operators (LaTeX `listings`, most lab manuals) loses ALL indentation and
# blank lines: nested braces/Python blocks become flat and ambiguous.
# `extraction_mode="layout"` reconstructs the geometry (indentation and
# blank lines) but pads every word gap with extra spaces and offsets
# centred headings by dozens of columns, and on multi-column prose it
# interleaves the columns -- so it is only used for pages that look like
# source code, and its output is normalised below.

_CODE_LINE_ENDINGS = (";", "{", "}", "*/")
_CODE_LINE_STARTS = (
    "#include",
    "#define",
    "import ",
    "from ",
    "def ",
    "class ",
    "public ",
    "private ",
    "static ",
    "for ",
    "for(",
    "while ",
    "while(",
    "if ",
    "if(",
    "else",
    "return",
    "//",
    "int ",
    "void ",
    "char ",
    "float ",
    "double ",
)
_MIN_CODE_LINES = 3
_MIN_CODE_RATIO = 0.2
_CENTRED_HEADING_MAX_CHARS = 60
_CENTRED_HEADING_MIN_INDENT = 16


def _looks_like_code(text: str) -> bool:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < _MIN_CODE_LINES:
        return False
    code_lines = sum(
        1
        for line in lines
        if line.endswith(_CODE_LINE_ENDINGS) or line.startswith(_CODE_LINE_STARTS)
    )
    return code_lines >= _MIN_CODE_LINES and code_lines / len(lines) >= _MIN_CODE_RATIO


def _normalize_layout_text(layout_text: str) -> str:
    """Turns pypdf layout output into clean text that keeps relative
    indentation: collapses padded word gaps, drops centred-heading offsets,
    re-bases indentation to 4 spaces per level and caps blank runs."""
    raw_lines = [line.rstrip() for line in layout_text.replace("\r\n", "\n").split("\n")]
    parsed: list[tuple[int, str]] = []
    for line in raw_lines:
        body = line.lstrip(" ")
        indent = len(line) - len(body)
        body = re.sub(r"(?<=\S) {2,}(?=\S)", " ", body)
        is_short = bool(body) and len(body) <= _CENTRED_HEADING_MAX_CHARS
        if is_short and indent >= _CENTRED_HEADING_MIN_INDENT:
            indent = 0  # a centred title, not code nesting
        parsed.append((indent, body))

    indents = sorted({indent for indent, body in parsed if body})
    margin = indents[0] if indents else 0
    # One indentation level = the most common gap between neighbouring
    # indentation columns (the smallest gap is unreliable: the first step is
    # often rounded narrower than the rest).
    gaps = Counter(b - a for a, b in zip(indents, indents[1:], strict=False) if b - a > 0)
    unit = max(gaps, key=lambda gap: (gaps[gap], gap)) if gaps else 0

    out: list[str] = []
    blank_run = 0
    for indent, body in parsed:
        if not body:
            blank_run += 1
            if blank_run <= 1:
                out.append("")
            continue
        blank_run = 0
        level = round((indent - margin) / unit) if unit and indent > margin else 0
        out.append(" " * (4 * level) + body)
    return "\n".join(out).strip("\n")


def _page_text(page: Any) -> str:
    text = page.extract_text() or ""
    if not _looks_like_code(text):
        return text
    try:
        layout = page.extract_text(extraction_mode="layout") or ""
    except Exception:  # noqa: BLE001 - fall back to the plain text, never fail the page
        return text
    normalized = _normalize_layout_text(layout)
    # Never trade content for formatting: if layout mode lost a lot of text,
    # keep the plain extraction.
    if len(re.sub(r"\s+", "", normalized)) < 0.9 * len(re.sub(r"\s+", "", text)):
        return text
    return normalized


def _extract_pdf(content: bytes) -> ExtractedDocument:
    try:
        reader = PdfReader(io.BytesIO(content))
        page_count = len(reader.pages)
    except PdfReadError as exc:
        raise ExtractionError("The PDF could not be read — it may be corrupt.") from exc
    except Exception as exc:  # noqa: BLE001 - any other pypdf failure is still untrusted-input
        raise ExtractionError("The PDF could not be read — it may be corrupt.") from exc

    if page_count > _MAX_PDF_PAGES:
        raise ExtractionError(
            f"The PDF has too many pages to process (limit: {_MAX_PDF_PAGES})."
        )

    sections: list[ExtractedSection] = []
    total_bytes = 0
    for index, page in enumerate(reader.pages, start=1):
        # A running total across the whole document, not just a per-page
        # cap: pypdf decompresses each page's content stream internally,
        # so a page's share of the already-capped 50 MiB *compressed*
        # upload says nothing about its *decompressed* text output (a
        # classic decompression-bomb shape). A per-page-only cap would
        # still let up to `_MAX_PDF_PAGES` pages each reach the per-page
        # maximum, summing to far more than `_MAX_EXTRACTED_TEXT_BYTES`
        # overall. Once the running total reaches the budget, remaining
        # pages are skipped entirely (not just truncated) -- this also
        # stops paying the decompression/extraction cost for pages whose
        # output would only be discarded anyway.
        if total_bytes >= _MAX_EXTRACTED_TEXT_BYTES:
            break
        try:
            text = _page_text(page)
        except Exception as exc:  # noqa: BLE001 - a single malformed page must not crash the rest
            raise ExtractionError(
                f"The PDF could not be read — page {index} is malformed."
            ) from exc
        remaining = _MAX_EXTRACTED_TEXT_BYTES - total_bytes
        truncated, used = _truncate_to_budget(text, max_bytes=remaining)
        sections.append(ExtractedSection(text=truncated, page=index))
        total_bytes += used

    return ExtractedDocument(sections=sections, page_count=page_count)


def _validate_docx_archive_safety(content: bytes) -> zipfile.ZipFile:
    """Inspects ZIP member metadata only (`infolist()` never decompresses
    anything) before any member is actually read, so a zip-bomb-style
    DOCX is rejected before it can cost anything beyond this cheap scan.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ExtractionError("The DOCX file could not be read — it may be corrupt.") from exc

    infos = archive.infolist()
    if len(infos) > _MAX_DOCX_MEMBER_COUNT:
        raise ExtractionError("The DOCX file has too many internal parts to process safely.")

    total_uncompressed = 0
    for info in infos:
        # Defense in depth against a traversal-crafted member name, even
        # though python-docx never extracts to the filesystem — it reads
        # members in-memory via ZipFile.read(). Still validated here so
        # this function's own safety guarantee doesn't silently depend
        # on that library's current internals never changing.
        if info.filename.startswith("/") or ".." in info.filename.replace("\\", "/").split("/"):
            raise ExtractionError("The DOCX file contains an unsafe internal file path.")
        if info.file_size > _MAX_DOCX_MEMBER_UNCOMPRESSED_BYTES:
            raise ExtractionError("The DOCX file contains an oversized internal part.")
        total_uncompressed += info.file_size

    if total_uncompressed > _MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES:
        raise ExtractionError("The DOCX file would expand to an unsafe size.")

    return archive


_HEADING_STYLE_PREFIX: Final = "Heading"


def _extract_docx(content: bytes) -> ExtractedDocument:
    _validate_docx_archive_safety(content)  # raises ExtractionError; result unused below

    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001 - any python-docx failure is still untrusted-input
        raise ExtractionError("The DOCX file could not be read — it may be corrupt.") from exc

    sections: list[ExtractedSection] = []
    total_bytes = 0
    current_heading: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        # A running total across every section, not a per-section cap --
        # see _extract_pdf's identical rationale. DOCX's total uncompressed
        # size is already bounded by _validate_docx_archive_safety(), but
        # that bound (200 MiB) is far larger than the documented
        # per-document extracted-text budget, so relying on it alone would
        # let a document with many heading-split sections produce far more
        # than `_MAX_EXTRACTED_TEXT_BYTES` of total extracted text.
        nonlocal total_bytes
        text = "\n".join(current_lines).strip()
        if (text or current_heading is not None) and total_bytes < _MAX_EXTRACTED_TEXT_BYTES:
            remaining = _MAX_EXTRACTED_TEXT_BYTES - total_bytes
            truncated, used = _truncate_to_budget(text, max_bytes=remaining)
            sections.append(ExtractedSection(text=truncated, heading=current_heading))
            total_bytes += used

    for paragraph in document.paragraphs:
        if total_bytes >= _MAX_EXTRACTED_TEXT_BYTES:
            break
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if style_name.startswith(_HEADING_STYLE_PREFIX) and paragraph.text.strip():
            _flush()
            current_heading = paragraph.text.strip()
            current_lines = []
        elif paragraph.text.strip():
            current_lines.append(paragraph.text)
    _flush()

    return ExtractedDocument(sections=sections, page_count=None)


def _decode_text(content: bytes) -> str:
    # Never raises on invalid byte sequences -- replaces them with the
    # standard Unicode replacement character rather than crashing or
    # silently dropping content.
    return content.decode("utf-8", errors="replace")


def _extract_txt(content: bytes) -> ExtractedDocument:
    text = _enforce_text_budget(_decode_text(content))
    return ExtractedDocument(sections=[ExtractedSection(text=text)], page_count=None)


_MARKDOWN_HEADING_PREFIX: Final = "#"


def _extract_markdown(content: bytes) -> ExtractedDocument:
    text = _decode_text(content)
    sections: list[ExtractedSection] = []
    total_bytes = 0
    current_heading: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        # Running total across sections -- see _extract_pdf's rationale.
        # Markdown's decode is ~1:1 with input bytes (no decompression),
        # so the total is already indirectly bounded by the 50 MiB upload
        # limit, but a heading-heavy document could still split that into
        # many sections each individually under the per-section cap while
        # the *document's* total exceeds `_MAX_EXTRACTED_TEXT_BYTES` --
        # tracked explicitly here so the documented per-document budget is
        # actually true, not just "usually true because of an unrelated
        # cap."
        nonlocal total_bytes
        body = "\n".join(current_lines).strip()
        if (body or current_heading is not None) and total_bytes < _MAX_EXTRACTED_TEXT_BYTES:
            remaining = _MAX_EXTRACTED_TEXT_BYTES - total_bytes
            truncated, used = _truncate_to_budget(body, max_bytes=remaining)
            sections.append(ExtractedSection(text=truncated, heading=current_heading))
            total_bytes += used

    for line in text.splitlines():
        if total_bytes >= _MAX_EXTRACTED_TEXT_BYTES:
            break
        stripped = line.strip()
        if stripped.startswith(_MARKDOWN_HEADING_PREFIX) and " " in stripped:
            _flush()
            current_heading = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)
    _flush()

    if not sections:
        sections = [ExtractedSection(text=_enforce_text_budget(text))]

    return ExtractedDocument(sections=sections, page_count=None)


def _extract_csv(content: bytes) -> ExtractedDocument:
    text = _decode_text(content)
    try:
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as exc:
        raise ExtractionError("The CSV file could not be read — it may be malformed.") from exc

    # Rendered incrementally, row by row, tracking the exact running byte
    # total (including the "\n" that will join each row) rather than
    # joining every row into one large string first and truncating
    # afterward. Two reasons: (1) re-serializing "," as ", " modestly
    # expands a pathological, comma-dense CSV, so building the whole
    # expanded string before truncating pays for more peak memory than
    # necessary; (2) a CSV with a huge number of tiny rows could otherwise
    # let the "\n" separators alone push the final joined size past the
    # budget even if every individual row was itself within it.
    parts: list[str] = []
    total_bytes = 0
    for row in rows:
        separator_cost = 1 if parts else 0  # the "\n" that will precede this row
        if total_bytes + separator_cost >= _MAX_EXTRACTED_TEXT_BYTES:
            break
        line = ", ".join(row)
        remaining = _MAX_EXTRACTED_TEXT_BYTES - total_bytes - separator_cost
        truncated, used = _truncate_to_budget(line, max_bytes=remaining)
        parts.append(truncated)
        total_bytes += used + separator_cost
        if used < len(line.encode("utf-8")):
            break  # this row was itself truncated -- budget is now exhausted

    rendered = "\n".join(parts)
    return ExtractedDocument(
        sections=[ExtractedSection(text=rendered)], page_count=None
    )


_EXTRACTORS: Final = {
    ".pdf": _extract_pdf,
    ".docx": _extract_docx,
    ".txt": _extract_txt,
    ".md": _extract_markdown,
    ".csv": _extract_csv,
}


def extract(*, extension: str, content: bytes) -> ExtractedDocument:
    """Dispatches to the extractor for `extension` (already validated and
    normalized by the upload flow — see app/services/document_service.py).
    Raises `ExtractionError` for an unsupported extension or any parser
    failure; never returns a partial result for a failed parse."""
    extractor = _EXTRACTORS.get(extension)
    if extractor is None:
        raise ExtractionError(f"No extractor available for {extension!r}.")
    return extractor(content)


__all__ = ["ExtractedDocument", "ExtractedSection", "ExtractionError", "extract"]
