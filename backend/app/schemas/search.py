from __future__ import annotations

import uuid

from pydantic import BaseModel


class SearchResultRead(BaseModel):
    rank: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    page: int | None
    section: str | None
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    method: str
    results: list[SearchResultRead]
