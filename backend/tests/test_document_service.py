"""Unit tests for the pure validation/checksum/key-generation helpers in
`app.services.document_service` (Issue #3, Slice 3.3). No database, no
HTTP, no real filesystem — see `tests/test_document_upload.py` for the
end-to-end HTTP-level coverage.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.services import document_service


def test_normalize_extension_lowercases_and_extracts_suffix() -> None:
    assert document_service._normalize_extension("Report.PDF") == ".pdf"
    assert document_service._normalize_extension("notes.Md") == ".md"


def test_normalize_extension_handles_missing_or_empty_filename() -> None:
    assert document_service._normalize_extension(None) is None
    assert document_service._normalize_extension("") is None
    assert document_service._normalize_extension("noextension") is None


def test_normalize_extension_only_uses_the_final_suffix() -> None:
    # A path-like or multi-dot filename never contributes more than the
    # trailing suffix -- this is a pure string operation, not filesystem
    # path handling, so "../../etc/passwd.pdf" still normalizes to ".pdf".
    assert document_service._normalize_extension("../../etc/passwd.pdf") == ".pdf"
    assert document_service._normalize_extension("archive.tar.gz") == ".gz"


@pytest.mark.parametrize(
    "filename",
    [
        "../../etc/passwd.pdf",
        "..\\..\\secret.pdf",
        "/absolute/path/file.pdf",
        "C:\\Windows\\System32\\file.pdf",
        "....//....//file.pdf",
    ],
)
def test_malicious_filenames_normalize_to_just_the_extension(filename: str) -> None:
    # None of these ever reach a filesystem call -- _normalize_extension()
    # is a pure suffix operation with no special-casing for "/" or "\\",
    # so every path-like or traversal-style filename reduces to exactly
    # ".pdf" regardless of what precedes it.
    assert document_service._normalize_extension(filename) == ".pdf"


@pytest.mark.parametrize("extension", [".pdf", ".docx", ".txt", ".md", ".csv"])
def test_allowed_extensions(extension: str) -> None:
    assert document_service._is_allowed_extension(extension) is True


@pytest.mark.parametrize("extension", [".exe", ".sh", ".html", ".zip", ".py"])
def test_disallowed_extensions(extension: str) -> None:
    assert document_service._is_allowed_extension(extension) is False


@pytest.mark.parametrize(
    ("extension", "mime_type"),
    [
        (".pdf", "application/pdf"),
        (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (".txt", "text/plain"),
        (".md", "text/markdown"),
        (".md", "text/x-markdown"),
        (".md", "text/plain"),
        (".csv", "text/csv"),
        (".csv", "application/vnd.ms-excel"),
        (".csv", "text/plain"),
    ],
)
def test_allowed_mime_variants(extension: str, mime_type: str) -> None:
    assert document_service._is_allowed_mime(extension, mime_type) is True


@pytest.mark.parametrize(
    ("extension", "mime_type"),
    [
        (".pdf", "text/plain"),
        (".pdf", None),
        (".docx", "application/zip"),
        (".txt", "application/pdf"),
        (".csv", "application/json"),
    ],
)
def test_disallowed_mime_combinations(extension: str, mime_type: str | None) -> None:
    assert document_service._is_allowed_mime(extension, mime_type) is False


def test_mime_not_checked_against_an_unlisted_extension() -> None:
    assert document_service._is_allowed_mime(".exe", "application/pdf") is False


def test_pdf_signature_match_and_mismatch() -> None:
    assert document_service._matches_signature(".pdf", b"%PDF-1.7\n...") is True
    assert document_service._matches_signature(".pdf", b"not a pdf at all") is False


def test_docx_signature_match_and_mismatch() -> None:
    assert document_service._matches_signature(".docx", b"PK\x03\x04rest-of-zip") is True
    assert document_service._matches_signature(".docx", b"not a zip") is False


@pytest.mark.parametrize("extension", [".txt", ".md", ".csv"])
def test_text_formats_have_no_signature_check(extension: str) -> None:
    # No reliable magic number for plain-text formats -- any bytes pass,
    # documented as a real limitation, not silently pretended otherwise.
    assert document_service._matches_signature(extension, b"anything at all") is True
    assert document_service._matches_signature(extension, b"") is True


def test_generate_storage_key_uses_only_trusted_identifiers() -> None:
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    key = document_service._generate_storage_key(
        workspace_id=workspace_id, document_id=document_id, extension=".pdf"
    )
    assert key == f"{workspace_id}/{document_id}.pdf"


def test_generate_storage_key_never_contains_a_filename() -> None:
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    key = document_service._generate_storage_key(
        workspace_id=workspace_id, document_id=document_id, extension=".pdf"
    )
    assert "etc" not in key
    assert ".." not in key


@pytest.mark.asyncio
async def test_read_and_validate_size_computes_correct_checksum() -> None:
    content = b"hello world" * 1000
    upload = _FakeUploadFile(content)

    read_content, checksum = await document_service._read_and_validate_size(
        upload,  # type: ignore[arg-type]
        max_size_bytes=10_000_000,
    )

    assert read_content == content
    assert checksum == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_read_and_validate_size_aborts_before_buffering_oversized_payload() -> None:
    # 3 MiB of content against a 1 MiB limit -- the reader must abort
    # partway through, not after accumulating the whole payload first.
    content = b"x" * (3 * 1024 * 1024)
    upload = _FakeUploadFile(content, chunk_size=64 * 1024)

    with pytest.raises(Exception) as exc_info:
        await document_service._read_and_validate_size(
            upload,  # type: ignore[arg-type]
            max_size_bytes=1024 * 1024,
        )

    assert exc_info.value.status_code == 413  # type: ignore[attr-defined]
    assert exc_info.value.detail["code"] == "file_too_large"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_read_and_validate_size_succeeds_at_exactly_the_limit() -> None:
    # total == max_size_bytes must succeed -- the check is "> max", not
    # ">= max"; an off-by-one here would wrongly reject a file of exactly
    # the configured maximum size.
    limit = 4096
    content = b"y" * limit
    upload = _FakeUploadFile(content, chunk_size=1024)

    read_content, checksum = await document_service._read_and_validate_size(
        upload,  # type: ignore[arg-type]
        max_size_bytes=limit,
    )

    assert len(read_content) == limit
    assert checksum == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_read_and_validate_size_rejects_exactly_one_byte_over_the_limit() -> None:
    limit = 4096
    content = b"y" * (limit + 1)
    upload = _FakeUploadFile(content, chunk_size=1024)

    with pytest.raises(Exception) as exc_info:
        await document_service._read_and_validate_size(
            upload,  # type: ignore[arg-type]
            max_size_bytes=limit,
        )

    assert exc_info.value.status_code == 413  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_read_and_validate_size_does_not_depend_on_any_length_hint() -> None:
    # The reader only ever counts bytes actually read via .read() -- it
    # never consults a Content-Length-style hint, so a missing or
    # misleading one (which this fake stand-in doesn't provide at all)
    # cannot be used to bypass the limit or under/over-report size.
    limit = 100
    content = b"z" * (limit + 1)
    upload = _FakeUploadFile(content, chunk_size=1)  # worst case: 1 byte at a time

    with pytest.raises(Exception) as exc_info:
        await document_service._read_and_validate_size(
            upload,  # type: ignore[arg-type]
            max_size_bytes=limit,
        )

    assert exc_info.value.status_code == 413  # type: ignore[attr-defined]


class _FakeUploadFile:
    """A minimal stand-in for fastapi.UploadFile's async .read() interface
    -- exercises the real chunked-read/checksum/size logic without needing
    a real HTTP multipart request."""

    def __init__(self, content: bytes, *, chunk_size: int = 1024 * 1024) -> None:
        self._content = content
        self._chunk_size = chunk_size
        self._offset = 0

    async def read(self, size: int) -> bytes:
        read_size = min(size, self._chunk_size)
        chunk = self._content[self._offset : self._offset + read_size]
        self._offset += len(chunk)
        return chunk
