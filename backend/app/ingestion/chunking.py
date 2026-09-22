"""Structure-aware chunking (Issue #3, Slice 3.5).

Turns an `ExtractedDocument` (Slice 3.4) into an ordered list of `Chunk`
objects, sized for downstream embedding (a later slice). Pure, in-memory
transformation only: this module never touches the filesystem,
`StorageProvider`, the database, or HTTP -- no chunk is persisted, no
document status transition happens here. Wiring `Chunk`s into
`document_chunks` rows and any `PARSED -> CLEANED -> CHUNKED` lifecycle
transition is explicitly a later slice's job (see `HANDOFF.md`).

**Schema-compatibility constraint, deliberate and load-bearing**: the
`document_chunks` table (`app/models/document_chunk.py`, migration
`0004`) stores exactly one `page: int | None` and one `section: str |
None` per chunk row -- no array/range type. A chunk therefore never
spans more than one `ExtractedSection`: each `ExtractedSection` already
carries a single `page`/`heading` pair (one page for PDF, one heading
for DOCX/Markdown, `None`/`None` for TXT/CSV's single section), and
every `Chunk` this module produces inherits that section's `page`/
`heading` unchanged. Merging content across two different sections into
one chunk would force inventing a `page`/`section` value that doesn't
honestly describe the chunk's content (e.g. claiming "page 3" for text
that is actually pages 3 and 4) -- so this module never does that, even
when it would help reach `target_chunk_size` for a short section. A
short section simply produces its own short chunk. Overlap follows the
same rule: it never carries text across a section boundary, only
between consecutive chunks within the same section.

**Character-based, not token-based.** `target_chunk_size`/
`chunk_overlap`/`min_chunk_size`/`max_chunk_size` all count Python `str`
characters (`len(text)`), not model tokens. No tokenizer is used or
implied anywhere in this module -- see "Dependency discipline" in
`HANDOFF.md` for why one wasn't added.

Boundary preference, in order, matching this project's chunking
requirements: section (an `ExtractedSection`, the current level a chunk
can never cross) -> paragraph (a blank line, or -- since most of this
project's own extractors join lines with a single `\n`, not `\n\n`, see
`extraction.py` -- a single newline when no blank line exists) ->
sentence (a `.`/`!`/`?` followed by whitespace; a punctuation heuristic,
not real sentence segmentation) -> word (whitespace) -> a hard
character cut, only ever reached for a single "word" with no internal
whitespace that alone still exceeds `max_chunk_size` (e.g. a very long
URL or base64 blob).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol

from app.ingestion.extraction import ExtractedDocument, ExtractedSection

# A sane ceiling, not a tuned value: a "chunk" larger than this defeats
# the purpose of chunking for retrieval/embedding, so a config requesting
# one is almost certainly a mistake, not a legitimate use case.
_ABSOLUTE_MAX_CHUNK_SIZE: Final = 100_000

# Defense-in-depth against a pathological configuration (e.g. a very
# small min_chunk_size) combined with a large document producing an
# unreasonable number of chunks. Extraction already bounds total input
# text to 20 MiB (`extraction._MAX_EXTRACTED_TEXT_BYTES`); this catches
# the case where min_chunk_size is small enough that 20 MiB of text would
# still produce an excessive chunk count, rather than silently returning
# an enormous list.
_MAX_CHUNKS_PER_DOCUMENT: Final = 50_000

_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class ChunkingError(Exception):
    """Raised only for a resource-safety ceiling being exceeded during
    `chunk()` (see `_MAX_CHUNKS_PER_DOCUMENT`). Configuration itself is
    validated eagerly at `ChunkingConfig` construction time via
    `ValueError` -- standard fail-fast validation for a plain config
    object in this codebase (see `app/core/config.py`'s own `ValueError`
    validation for a precedent), not a runtime chunking failure."""


@dataclass(frozen=True)
class ChunkingConfig:
    """All sizes are character counts (`len(text)`), not tokens.

    - `target_chunk_size`: the size a chunk is closed at once reached,
      when doing so doesn't violate `min_chunk_size` for what remains.
    - `max_chunk_size`: a hard ceiling -- no produced chunk's `content`
      ever exceeds this, by construction (verified in tests).
    - `min_chunk_size`: a target floor, not an absolute guarantee -- a
      section shorter than this produces its own short chunk rather
      than being merged with a *different* section (see the module
      docstring's schema-compatibility constraint), and a small trailing
      remainder that can't be merged into the previous chunk without
      exceeding `max_chunk_size` is emitted as-is rather than dropped or
      forced to violate `max_chunk_size`.
    - `chunk_overlap`: characters of a chunk's tail carried into the next
      chunk's head, within the same section only.
    """

    target_chunk_size: int = 1000
    chunk_overlap: int = 100
    min_chunk_size: int = 200
    max_chunk_size: int = 2000

    def __post_init__(self) -> None:
        if self.target_chunk_size <= 0:
            raise ValueError("target_chunk_size must be > 0.")
        if self.min_chunk_size <= 0:
            raise ValueError("min_chunk_size must be > 0.")
        if self.max_chunk_size <= 0:
            raise ValueError("max_chunk_size must be > 0.")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0.")
        if self.max_chunk_size > _ABSOLUTE_MAX_CHUNK_SIZE:
            raise ValueError(f"max_chunk_size must be <= {_ABSOLUTE_MAX_CHUNK_SIZE}.")
        if not (self.min_chunk_size <= self.target_chunk_size <= self.max_chunk_size):
            raise ValueError(
                "must have min_chunk_size <= target_chunk_size <= max_chunk_size."
            )
        if self.chunk_overlap >= self.min_chunk_size:
            # Also rules out chunk_overlap >= max_chunk_size (a stricter
            # upstream check), and structurally prevents overlap alone
            # from ever filling an entire new chunk -- each new chunk
            # must contain at least (min_chunk_size - chunk_overlap) > 0
            # characters of genuinely new content.
            raise ValueError("chunk_overlap must be < min_chunk_size.")


@dataclass(frozen=True)
class Chunk:
    """Deliberately not the `DocumentChunk` SQLAlchemy model: this module
    has no database dependency (see the module docstring), and coupling
    a pure text-transformation's output type to an ORM model would pull
    SQLAlchemy into every place this module is unit-tested. Field names
    match `document_chunks`' own columns 1:1 (minus `document_id`/
    `workspace_id`/`id`, which only exist once a document/workspace
    context is applied by whatever later slice persists these) so
    mapping to that model, when it happens, is a trivial 1:1 copy.
    """

    chunk_index: int
    page: int | None
    section: str | None
    content: str


class ChunkingStrategy(Protocol):
    """A strategy is any object providing `chunk(document) -> list[Chunk]`.
    `StructureAwareChunker` below is the one concrete implementation this
    slice provides; the protocol exists so a future strategy (fixed-size,
    recursive -- both explicitly named in `docs/RAG_DESIGN.md`, not
    implemented here) can be swapped in without changing any caller."""

    def chunk(self, document: ExtractedDocument) -> list[Chunk]: ...


class StructureAwareChunker:
    """Chunks each `ExtractedSection` independently (never merging across
    sections -- see the module docstring), preferring paragraph/sentence/
    word boundaries over a hard character cut, and applying `chunk_overlap`
    only between chunks within the same section.

    Deterministic: pure function of `(document, config)` with no
    randomness, no wall-clock/ID generation, and no reliance on set/dict
    iteration order beyond Python's own guaranteed-stable `dict`/list
    ordering -- the same input and config always produce byte-identical
    output (verified in tests, not just assumed).
    """

    def __init__(self, *, config: ChunkingConfig | None = None) -> None:
        self._config = config or ChunkingConfig()

    def chunk(self, document: ExtractedDocument) -> list[Chunk]:
        chunks: list[Chunk] = []
        next_index = 0
        for section in document.sections:
            section_chunks = self._chunk_section(section, start_index=next_index)
            chunks.extend(section_chunks)
            next_index += len(section_chunks)
        return chunks

    def _chunk_section(self, section: ExtractedSection, *, start_index: int) -> list[Chunk]:
        text = section.text.strip()
        if not text:
            return []  # never emit an empty chunk for an empty/whitespace section
        pieces = self._split_into_pieces(text)
        # `index_offset=start_index`: the ceiling check inside `_pack()`
        # must see the running total across *all* sections so far, not
        # just this section's own count -- checking only between
        # sections (an earlier version of this method did that) would
        # let a single large section (TXT/CSV always produce exactly
        # one) build far more than `_MAX_CHUNKS_PER_DOCUMENT` chunks
        # before the check ever ran, since one `_chunk_section()` call
        # would already have returned. Confirmed empirically during
        # review: a 5,000,000-character single-section document with a
        # pathologically small `min_chunk_size` produced roughly
        # 500,000+ intermediate chunks before a between-sections-only
        # check would have fired -- ten times the stated ceiling.
        packed = self._pack(pieces, index_offset=start_index)
        return [
            Chunk(
                chunk_index=start_index + i,
                page=section.page,
                section=section.heading,
                content=content,
            )
            for i, content in enumerate(packed)
        ]

    # --- boundary-aware splitting into pieces, each <= max_chunk_size --

    def _split_into_pieces(self, text: str) -> list[str]:
        blocks = [block.strip() for block in _PARAGRAPH_SPLIT_RE.split(text) if block.strip()]
        if len(blocks) <= 1:
            # No blank-line paragraph break found. Most of this project's
            # own extractors join lines with a single "\n", not "\n\n"
            # (see extraction.py's _extract_docx/_extract_markdown/
            # _extract_pdf) -- fall back to single newlines as a softer
            # paragraph-like boundary before giving up on paragraph-level
            # structure entirely.
            single_newline_blocks = [b.strip() for b in text.split("\n") if b.strip()]
            if len(single_newline_blocks) > 1:
                blocks = single_newline_blocks
        if not blocks:
            blocks = [text]

        pieces: list[str] = []
        for block in blocks:
            pieces.extend(self._split_oversized(block))
        return pieces

    def _split_oversized(self, text: str) -> list[str]:
        """Recursively falls through paragraph (caller) -> sentence ->
        word -> hard-character boundaries until every returned piece is
        <= max_chunk_size. Always terminates: hard-character splitting
        makes guaranteed progress (a fixed-size cut), so there is no
        boundary level at which this can recurse without shrinking the
        remaining text."""
        max_size = self._config.max_chunk_size
        if len(text) <= max_size:
            return [text]

        sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s]
        if len(sentences) > 1:
            result: list[str] = []
            for sentence in sentences:
                result.extend(self._split_oversized(sentence))
            return result

        words = text.split(" ")
        if len(words) > 1:
            return self._pack_words(words, max_size)

        return self._split_hard(text, max_size)

    def _pack_words(self, words: list[str], max_size: int) -> list[str]:
        result: list[str] = []
        buffer = ""
        for word in words:
            candidate = f"{buffer} {word}" if buffer else word
            if len(candidate) <= max_size:
                buffer = candidate
                continue
            if buffer:
                result.append(buffer)
                buffer = ""
            if len(word) > max_size:
                result.extend(self._split_hard(word, max_size))
            else:
                buffer = word
        if buffer:
            result.append(buffer)
        return result

    def _split_hard(self, text: str, max_size: int) -> list[str]:
        return [text[i : i + max_size] for i in range(0, len(text), max_size)]

    # --- packing pieces toward target_chunk_size, with overlap ---------

    def _pack(self, pieces: list[str], *, index_offset: int) -> list[str]:
        if not pieces:
            return []
        config = self._config
        chunks: list[str] = []
        buffer = ""
        # True exactly when `buffer` is leftover overlap text carried
        # from the last close, with no new piece content added to it
        # yet. Tracked so that if the next piece doesn't fit even
        # alongside just that overlap, the overlap is discarded rather
        # than emitted as its own tiny "chunk" -- it would contain
        # nothing that isn't already the tail of the previous chunk, so
        # keeping it would only produce a redundant near-duplicate
        # fragment, not new information.
        buffer_is_pure_overlap = False

        for piece in pieces:
            candidate = f"{buffer}\n\n{piece}" if buffer else piece
            if len(candidate) <= config.max_chunk_size:
                buffer = candidate
                buffer_is_pure_overlap = False
                if len(buffer) >= config.target_chunk_size:
                    # Always >= target_chunk_size >= min_chunk_size here,
                    # so a direct append is safe -- no merge-back check
                    # needed (that's `_close_buffer`'s job for the other,
                    # possibly-undersized closing points below).
                    chunks.append(buffer)
                    self._check_chunk_ceiling(index_offset, len(chunks))
                    buffer = self._overlap_tail(buffer)
                    buffer_is_pure_overlap = bool(buffer)
                continue

            # `piece` doesn't fit alongside the current buffer.
            if buffer and not buffer_is_pure_overlap:
                self._close_buffer(chunks, buffer)
                self._check_chunk_ceiling(index_offset, len(chunks))
                overlap = self._overlap_tail(buffer)
            else:
                overlap = ""  # nothing genuinely new to close/carry forward

            candidate_with_overlap = f"{overlap}\n\n{piece}" if overlap else piece
            if len(candidate_with_overlap) <= config.max_chunk_size:
                buffer = candidate_with_overlap
            else:
                buffer = piece
            buffer_is_pure_overlap = False

        if buffer and not buffer_is_pure_overlap:
            self._close_buffer(chunks, buffer)
            self._check_chunk_ceiling(index_offset, len(chunks))
        return chunks

    def _check_chunk_ceiling(self, index_offset: int, chunks_in_section_so_far: int) -> None:
        """Checked after every chunk this section closes -- not just once
        per section -- so a single very large section (TXT/CSV always
        produce exactly one) can't build far more than
        `_MAX_CHUNKS_PER_DOCUMENT` chunks internally before this ever
        runs; see `_chunk_section()`'s docstring comment for the
        empirical case that motivated checking incrementally rather than
        only between sections."""
        if index_offset + chunks_in_section_so_far > _MAX_CHUNKS_PER_DOCUMENT:
            raise ChunkingError(
                f"Chunking produced more than {_MAX_CHUNKS_PER_DOCUMENT} "
                "chunks for one document; aborting rather than continuing "
                "to accumulate unbounded output."
            )

    def _close_buffer(self, chunks: list[str], buffer: str) -> None:
        """Appends `buffer` as a new chunk, unless it's under
        `min_chunk_size` and can be merged into the previous chunk
        without exceeding `max_chunk_size` -- in which case it's merged
        instead, avoiding an avoidably tiny chunk. A merge is skipped
        (buffer stands alone) only when there is no previous chunk in
        this section, or merging would exceed `max_chunk_size` -- an
        unavoidable, documented exception to the `min_chunk_size` target,
        never to the `max_chunk_size` hard limit."""
        if not buffer:
            return
        if chunks and len(buffer) < self._config.min_chunk_size:
            merged = f"{chunks[-1]}\n\n{buffer}"
            if len(merged) <= self._config.max_chunk_size:
                chunks[-1] = merged
                return
        chunks.append(buffer)

    def _overlap_tail(self, text: str) -> str:
        overlap = self._config.chunk_overlap
        if overlap <= 0 or not text:
            return ""
        return text[-overlap:]


__all__ = ["Chunk", "ChunkingConfig", "ChunkingError", "ChunkingStrategy", "StructureAwareChunker"]
