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
import zipfile
from dataclasses import dataclass, field
from typing import Final

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


def _enforce_text_budget(text: str) -> str:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= _MAX_EXTRACTED_TEXT_BYTES:
        return text
    # Truncate on a UTF-8 boundary rather than raise: a very large but
    # genuinely valid document still produces useful, bounded output,
    # rather than being treated as an outright failure.
    return encoded[:_MAX_EXTRACTED_TEXT_BYTES].decode("utf-8", errors="ignore")


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
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001 - a single malformed page must not crash the rest
            raise ExtractionError(
                f"The PDF could not be read — page {index} is malformed."
            ) from exc
        sections.append(ExtractedSection(text=_enforce_text_budget(text), page=index))

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
    current_heading: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        text = "\n".join(current_lines).strip()
        if text or current_heading is not None:
            sections.append(
                ExtractedSection(text=_enforce_text_budget(text), heading=current_heading)
            )

    for paragraph in document.paragraphs:
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
    current_heading: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        body = "\n".join(current_lines).strip()
        if body or current_heading is not None:
            sections.append(
                ExtractedSection(text=_enforce_text_budget(body), heading=current_heading)
            )

    for line in text.splitlines():
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

    rendered = "\n".join(", ".join(cell for cell in row) for row in rows)
    return ExtractedDocument(
        sections=[ExtractedSection(text=_enforce_text_budget(rendered))], page_count=None
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
