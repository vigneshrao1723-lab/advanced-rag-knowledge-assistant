"""Words a speaker in this workspace is likely to say, taken from their own
documents, used to bias speech recognition (`vocabulary_hint`). Names the
user can see anyway - titles and filenames - never document body text."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.retrieval.references import filename_tokens

_TITLE_RE = re.compile(
    r"^[ \t#*>]*(?:programs?|programmes?|exercises?|experiments?|practicals?|questions?|problems?|"
    r"tasks?|assignments?|listings?|examples?|chapters?|sections?)[ \t]*(?:no\.?|number|#)?[ \t]*"
    r"\d{1,3}[ \t]*[:.\-–][ \t]*(?P<title>[^\n]{3,60})$",
    re.IGNORECASE | re.MULTILINE,
)
_MAX_TERMS = 24
_MAX_CHUNKS_SCANNED = 400


def build_vocabulary_hint(db: Session, *, workspace_id: uuid.UUID) -> str | None:
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        cleaned = " ".join(term.split()).strip(" .:-")
        key = cleaned.lower()
        if cleaned and key not in seen and len(terms) < _MAX_TERMS:
            seen.add(key)
            terms.append(cleaned)

    chunks = db.execute(
        select(DocumentChunk.content)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.workspace_id == workspace_id,
            Document.status == DocumentStatus.READY,
        )
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        .limit(_MAX_CHUNKS_SCANNED)
    ).scalars()
    for content in chunks:
        for match in _TITLE_RE.finditer(content):
            add(match.group("title"))

    filenames = db.execute(
        select(Document.filename).where(
            Document.workspace_id == workspace_id, Document.status == DocumentStatus.READY
        )
    ).scalars()
    for filename in filenames:
        add(" ".join(filename_tokens(filename)))

    if not terms:
        return None
    return "Terms: " + ", ".join(terms) + "."


__all__ = ["build_vocabulary_hint"]
