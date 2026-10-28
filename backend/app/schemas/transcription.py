from __future__ import annotations

from pydantic import BaseModel


class TranscriptionRead(BaseModel):
    """Result of transcribing a recording, *without* asking the assistant
    anything: the UI shows it for review and correction first. An empty
    `transcript` means no speech was recognised (not an error)."""

    transcript: str
    language: str | None
    duration_seconds: float | None
    provider: str
    model: str
