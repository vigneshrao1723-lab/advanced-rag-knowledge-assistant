"""Document outline and labelled-item lookup ("Program 5", "the first
exercise").

Chunking cuts documents by size and by page, so the heading of a program, its
code and its output often live in different chunks and similarity search
returns an arbitrary subset of them. For a question that *names* an item this
module finds the item's heading in the stored chunks and reassembles the
item's whole span -- from its heading up to the next item's heading -- so the
model sees the program, its code and its output together. When the item does
not exist it says so and lists what does, without calling the model.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.retrieval.references import Locator, heading_pattern
from app.retrieval.types import RetrievalCandidate

_MAX_SPAN_CHUNKS = 12
_MIN_OVERLAP_CHARS = 20
_MAX_OVERLAP_CHARS = 250


@dataclass(frozen=True)
class OutlineEntry:
    document_id: uuid.UUID
    chunk_index: int
    offset: int  # character offset of the heading line inside the chunk
    number: int

    @property
    def position(self) -> tuple[int, int]:
        return (self.chunk_index, self.offset)


@dataclass(frozen=True)
class Found:
    candidates: list[RetrievalCandidate]
    document_id: uuid.UUID
    label: str


@dataclass(frozen=True)
class Reply:
    """A deterministic answer (missing item / several documents match)."""

    message: str


Resolution = Found | Reply | None


def build_outline(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    kind: str,
    document_ids: list[uuid.UUID] | None,
) -> dict[uuid.UUID, list[OutlineEntry]]:
    """Headings of `kind` per document, in document order, first occurrence
    of each number only."""
    stmt = (
        select(DocumentChunk.document_id, DocumentChunk.chunk_index, DocumentChunk.content)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.workspace_id == workspace_id,
            Document.status == DocumentStatus.READY,
            DocumentChunk.content.ilike(f"%{kind}%"),
        )
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    )
    if document_ids is not None:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
    pattern = heading_pattern(kind)
    outline: dict[uuid.UUID, list[OutlineEntry]] = defaultdict(list)
    seen: set[tuple[uuid.UUID, int]] = set()
    for document_id, chunk_index, content in db.execute(stmt).all():
        for match in pattern.finditer(content):
            number = int(match.group("num"))
            if (document_id, number) in seen:
                continue
            seen.add((document_id, number))
            offset = match.start()
            # Leading whitespace/markup belongs to the heading line.
            outline[document_id].append(OutlineEntry(document_id, chunk_index, offset, number))
    return dict(outline)


def _trim_overlap(previous: str, current: str) -> str:
    """Chunks of one section overlap (the tail of one repeats at the head of
    the next); drop the repeat so the span reads once."""
    limit = min(len(previous), len(current), _MAX_OVERLAP_CHARS)
    for size in range(limit, _MIN_OVERLAP_CHARS - 1, -1):
        if previous.endswith(current[:size]):
            return current[size:]
    return current


def _chunks_between(
    db: Session, *, document_id: uuid.UUID, first: int, last: int
) -> list[DocumentChunk]:
    return list(
        db.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_index >= first,
                DocumentChunk.chunk_index <= last,
            )
            .order_by(DocumentChunk.chunk_index)
        ).scalars()
    )


def build_span(
    db: Session,
    *,
    entries: list[OutlineEntry],
    start: OutlineEntry,
    max_chars: int,
) -> list[RetrievalCandidate]:
    later = [e for e in entries if e.position > start.position and e.number != start.number]
    boundary = min(later, key=lambda e: e.position) if later else None
    last_index = boundary.chunk_index if boundary else start.chunk_index + _MAX_SPAN_CHUNKS
    last_index = min(last_index, start.chunk_index + _MAX_SPAN_CHUNKS)
    rows = _chunks_between(
        db, document_id=start.document_id, first=start.chunk_index, last=last_index
    )

    pieces: list[RetrievalCandidate] = []
    previous_text = ""
    used = 0
    for row in rows:
        text = row.content
        if row.chunk_index == start.chunk_index:
            text = text[start.offset :]
        if boundary and row.chunk_index == boundary.chunk_index:
            # The next item's heading may sit in this very chunk.
            cut = boundary.offset - (start.offset if row.chunk_index == start.chunk_index else 0)
            text = text[: max(cut, 0)]
        if previous_text:
            text = _trim_overlap(previous_text, text)
        previous_text = row.content if row.chunk_index != start.chunk_index else text
        text = text.strip("\n")
        if not text.strip():
            continue
        if pieces and used + len(text) > max_chars:
            break
        used += len(text)
        pieces.append(
            RetrievalCandidate(
                chunk_id=row.id,
                document_id=row.document_id,
                workspace_id=row.workspace_id,
                content=text,
                page=row.page,
                section=row.section,
                score=1.0 - 0.01 * len(pieces),
            )
        )
        if boundary and row.chunk_index == boundary.chunk_index:
            break
    return pieces


def _numbers(entries: list[OutlineEntry]) -> str:
    return ", ".join(str(e.number) for e in entries)


def resolve_locator(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    locator: Locator,
    document_names: dict[uuid.UUID, str],
    scope: list[uuid.UUID] | None,
    max_chars: int,
) -> Resolution:
    """`None` means "this workspace/scope has no items of that kind at all":
    the caller falls back to ordinary retrieval (the document may simply not
    label things this way)."""
    outline = build_outline(db, workspace_id=workspace_id, kind=locator.kind, document_ids=scope)
    if not outline:
        return None
    label = locator.kind.capitalize()

    if locator.number is not None:
        holders = [
            doc_id
            for doc_id, entries in outline.items()
            if any(e.number == locator.number for e in entries)
        ]
        if not holders:
            parts = [
                f"{document_names.get(doc_id, 'a document')} has {label}s {_numbers(entries)}"
                for doc_id, entries in outline.items()
            ]
            return Reply(
                f"I couldn't find {locator.describe()} in your documents. "
                + "; ".join(parts)
                + f". Which {locator.kind} would you like me to explain?"
            )
        if len(holders) > 1:
            names = ", ".join(document_names.get(d, "a document") for d in holders)
            return Reply(
                f"{locator.describe()} appears in more than one document ({names}). "
                "Which document do you mean?"
            )
        document_id = holders[0]
        start = next(e for e in outline[document_id] if e.number == locator.number)
    else:
        if len(outline) > 1:
            names = ", ".join(document_names.get(d, "a document") for d in outline)
            return Reply(
                f"I found {locator.kind}s in more than one document ({names}). "
                "Which document do you mean?"
            )
        document_id = next(iter(outline))
        entries = outline[document_id]
        index = len(entries) - 1 if locator.ordinal == -1 else (locator.ordinal or 1) - 1
        if not 0 <= index < len(entries):
            return Reply(
                f"{document_names.get(document_id, 'That document')} has only "
                f"{len(entries)} {locator.kind}(s) ({label}s {_numbers(entries)})."
            )
        start = entries[index]

    candidates = build_span(db, entries=outline[document_id], start=start, max_chars=max_chars)
    if not candidates:
        return None
    return Found(
        candidates=candidates,
        document_id=document_id,
        label=f"{label} {start.number}",
    )


__all__ = ["Found", "OutlineEntry", "Reply", "Resolution", "build_outline", "resolve_locator"]
