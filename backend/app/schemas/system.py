from __future__ import annotations

from pydantic import BaseModel


class CapabilityStatus(BaseModel):
    """One AI/speech capability as the UI needs to present it. `status` is
    "ready" when usable; anything else is a stable reason code and
    `message` is end-user-safe (never a key, URL or raw provider error)."""

    provider: str
    model: str | None
    status: str
    message: str


class CapabilitiesRead(BaseModel):
    llm: CapabilityStatus
    stt: CapabilityStatus
    tts: CapabilityStatus
