"""Which AI/speech capabilities are actually usable right now -- lets the
UI say "the AI model isn't running" up front instead of failing on the
first question (docs/AI_SETUP.md)."""

from __future__ import annotations

import shutil
import time
from threading import Lock

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.generation.llm_provider import (
    LLMProvider,
    OpenAICompatibleLLMProvider,
    get_llm_provider,
)
from app.models.user import User
from app.schemas.system import CapabilitiesRead, CapabilityStatus
from app.voice.stt_provider import SpeechToTextProvider, get_speech_to_text_provider

router = APIRouter(prefix="/system", tags=["system"])

_LLM_STATUS_TTL_SECONDS = 10.0
_llm_cache: tuple[float, CapabilityStatus] | None = None
_llm_cache_lock = Lock()


def _llm_status(provider: LLMProvider) -> CapabilityStatus:
    global _llm_cache
    if not isinstance(provider, OpenAICompatibleLLMProvider):
        return CapabilityStatus(
            provider="extractive",
            model=None,
            status="extractive",
            message=(
                "No AI model is configured: answers are the matching passages quoted from your "
                "documents, not explanations. See docs/AI_SETUP.md to enable a model."
            ),
        )
    with _llm_cache_lock:
        if _llm_cache and time.monotonic() - _llm_cache[0] < _LLM_STATUS_TTL_SECONDS:
            return _llm_cache[1]
    status, message = provider.check_availability()
    result = CapabilityStatus(
        provider="openai_compatible", model=provider.model_name, status=status, message=message
    )
    with _llm_cache_lock:
        _llm_cache = (time.monotonic(), result)
    return result


def _stt_status(provider: SpeechToTextProvider) -> CapabilityStatus:
    status, message = provider.check_availability()
    return CapabilityStatus(
        provider=provider.provider_name, model=provider.model_name, status=status, message=message
    )


def _tts_status() -> CapabilityStatus:
    if shutil.which("espeak-ng") is None:
        return CapabilityStatus(
            provider="espeak-ng",
            model=None,
            status="unavailable",
            message="espeak-ng is not installed in the backend.",
        )
    return CapabilityStatus(
        provider="espeak-ng",
        model=None,
        status="ready",
        message="Server speech synthesis is ready.",
    )


@router.get("/capabilities", response_model=CapabilitiesRead)
def get_capabilities(
    _user: User = Depends(get_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
    stt_provider: SpeechToTextProvider = Depends(get_speech_to_text_provider),
) -> CapabilitiesRead:
    return CapabilitiesRead(
        llm=_llm_status(provider),
        stt=_stt_status(stt_provider),
        tts=_tts_status(),
    )
