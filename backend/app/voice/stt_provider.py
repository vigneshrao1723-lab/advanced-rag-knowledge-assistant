"""Speech-to-text provider abstraction (docs/ARCHITECTURE.md "Provider
abstractions", GitHub Issue #6; ADR 0010 for the neural providers).

Three implementations: `PocketSphinxSpeechToTextProvider` (the original,
very weak on natural speech -- kept as the default for backward
compatibility and for the offline test suite), `WhisperSpeechToTextProvider`
(faster-whisper, local, free; recommended) and
`OpenAICompatibleSpeechToTextProvider` (audio is sent to a server you
configure). The remainder of this docstring describes the original contract.

Mirrors `EmbeddingProvider`/`StorageProvider`'s shape: a `Protocol`, one
concrete implementation today, and a settings-driven factory
(`get_speech_to_text_provider()`). No commercial vendor is selected yet
(see the forthcoming voice-providers ADR, mirroring
[ADR 0007](../../../docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md))
— `PocketSphinxSpeechToTextProvider` is a genuine, fully offline speech
recognizer (CMU PocketSphinx via the `SpeechRecognition` package) that
needs no API key, no network call, and no separate model download (the
package ships its own default acoustic/language model). Its accuracy is
materially weaker than a modern neural ASR model, especially against
synthetic (text-to-speech) audio rather than real human speech — this is
a known, honest limitation (matching `LocalHashingEmbeddingProvider`'s
own documented trade-off), not a bug. Swapping in a real hosted provider
later is additive: implement `SpeechToTextProvider`, branch on it in
`get_speech_to_text_provider()`, done.

This module is pure with respect to the rest of the application: no
database, HTTP, or conversation/message dependency. It knows nothing
about `Message`/`Conversation` rows — `conversation_service.py` is
responsible for calling this and feeding the resulting transcript into
the existing `post_message()` flow.
"""

from __future__ import annotations

import io
import logging
import threading
import time
import wave
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import speech_recognition as sr

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.voice")

_SUPPORTED_MIME_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/wave"})
_TARGET_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None = None
    duration_seconds: float | None = None


class SpeechToTextError(Exception):
    """Any transcription failure — treated by the calling endpoint as an
    expected, handled `422`/`500` outcome, never a raw stack trace.
    Never includes provider-internal detail (no library exception text)
    in the message, matching `EmbeddingError`'s own convention."""


class UnsupportedAudioFormatError(SpeechToTextError):
    """The uploaded audio's declared MIME type isn't one this provider
    can read. Raised before any audio bytes are actually parsed."""


class SpeechToTextUnavailableError(SpeechToTextError):
    """The configured recognizer cannot be used right now (model not
    installed, server unreachable, missing configuration). `code` is a
    stable reason and `message` is safe for end users (no URLs, keys or raw
    provider errors)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SpeechToTextProvider(Protocol):
    provider_name: str
    model_name: str

    def transcribe(
        self, audio_bytes: bytes, *, mime_type: str, language: str | None = None
    ) -> str:
        """Returns the transcribed text — an empty string if the audio
        contains no recognizable speech (a defined, non-crashing result,
        not an error). Raises `UnsupportedAudioFormatError` for an
        unrecognized `mime_type`, `SpeechToTextUnavailableError` when the
        recognizer cannot run, `SpeechToTextError` for anything else
        that prevents transcription (corrupt audio, a provider-internal
        failure)."""
        ...

    def transcribe_detailed(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str,
        language: str | None = None,
        vocabulary_hint: str | None = None,
    ) -> Transcript:
        """`vocabulary_hint` is a short text of words the speaker is likely to
        say (document titles, program names) that biases recognition toward
        them; providers that cannot use it ignore it."""
        ...

    def check_availability(self) -> tuple[str, str]:
        """(`status`, `message`); status is "ready" or a reason code."""
        ...


def _require_wav(mime_type: str) -> None:
    if mime_type not in _SUPPORTED_MIME_TYPES:
        raise UnsupportedAudioFormatError(
            f"Unsupported audio format: {mime_type}. Only WAV audio is supported."
        )


_MAX_PROMPT_CHARS = 400


def _join_prompt(base: str | None, hint: str | None) -> str | None:
    """The workspace vocabulary goes *after* the generic prompt (Whisper
    weighs the end of its prompt most) and the whole is capped: the model
    only reads a few hundred tokens of prompt."""
    parts = [part.strip() for part in (base, hint) if part and part.strip()]
    if not parts:
        return None
    return " ".join(parts)[-_MAX_PROMPT_CHARS:]


def decode_wav_to_mono_16k(audio_bytes: bytes) -> tuple[Any, float]:
    """16-bit PCM WAV -> (float32 mono samples at 16 kHz, duration seconds).
    Anything else raises `SpeechToTextError`."""
    import numpy as np

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            channels = wav_file.getnchannels()
            width = wav_file.getsampwidth()
            rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())
    except (wave.Error, EOFError) as exc:
        raise SpeechToTextError("The uploaded audio could not be read.") from exc
    if width != 2 or channels < 1 or rate < 8000:
        raise SpeechToTextError("Only 16-bit PCM WAV audio is supported.")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        usable = len(samples) - len(samples) % channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    duration = len(samples) / rate if rate else 0.0
    if rate != _TARGET_SAMPLE_RATE and len(samples):
        target_length = max(1, int(round(len(samples) * _TARGET_SAMPLE_RATE / rate)))
        positions = np.linspace(0, len(samples) - 1, num=target_length)
        samples = np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)
    return samples, float(duration)


class PocketSphinxSpeechToTextProvider:
    """Offline, no API key, no network call. Only reads WAV audio (PCM,
    any sample rate `speech_recognition`'s `AudioFile` accepts) — this
    project's frontend is responsible for encoding recorded audio to WAV
    client-side before upload (see `frontend/lib/wav-encoder.ts`), the
    same "validate/normalize at the boundary" precedent as document
    upload's extension/MIME/magic-byte checks."""

    provider_name = "pocketsphinx"
    model_name = "pocketsphinx"

    def check_availability(self) -> tuple[str, str]:
        return "ready", "Basic offline speech recognition (low accuracy; see docs/AI_SETUP.md)."

    def transcribe(
        self, audio_bytes: bytes, *, mime_type: str, language: str | None = None
    ) -> str:
        return self.transcribe_detailed(audio_bytes, mime_type=mime_type, language=language).text

    def transcribe_detailed(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str,
        language: str | None = None,
        vocabulary_hint: str | None = None,
    ) -> Transcript:
        _require_wav(mime_type)

        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
                audio_data = recognizer.record(source)
        except Exception as exc:
            raise SpeechToTextError("The uploaded audio could not be read.") from exc

        try:
            text = recognizer.recognize_sphinx(audio_data)
        except sr.UnknownValueError:
            # No recognizable speech in the audio -- a defined, honest
            # empty transcript, matching `LocalHashingEmbeddingProvider`'s
            # "empty input -> zero vector" convention, not an error.
            return Transcript(text="")
        except Exception as exc:
            raise SpeechToTextError("Speech recognition failed.") from exc

        return Transcript(text=str(text), language="en")


# One model per process, shared by every request (loading takes seconds and
# ~0.5-1.5 GB of RAM); transcription itself is serialised.
_whisper_models: dict[tuple[str, str, str], Any] = {}
_whisper_lock = threading.Lock()


class WhisperSpeechToTextProvider:
    """Local neural speech recognition (faster-whisper / CTranslate2). Free,
    offline, and dramatically more accurate than PocketSphinx on natural
    speech and technical vocabulary. The model is *never* downloaded as a
    side effect of a request: `infra/scripts/setup-local-stt.sh` (or
    `python -m app.voice.download_model`) installs it, and until then the
    provider reports `model_not_downloaded`."""

    provider_name = "faster_whisper"

    def __init__(self, settings: Settings) -> None:
        self._model_name = settings.stt_model
        self._device = settings.stt_device
        self._compute_type = settings.stt_compute_type
        self._threads = settings.stt_cpu_threads
        self._model_dir = settings.stt_model_dir
        self._language = settings.stt_language
        self._initial_prompt = settings.stt_initial_prompt or None
        self.model_name = f"whisper-{self._model_name}"

    def _load(self) -> Any:
        key = (self._model_name, self._device, self._compute_type)
        with _whisper_lock:
            if key in _whisper_models:
                return _whisper_models[key]
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - dependency is installed
                raise SpeechToTextUnavailableError(
                    "unavailable", "The faster-whisper package is not installed."
                ) from exc
            try:
                model = WhisperModel(
                    self._model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                    cpu_threads=self._threads,
                    download_root=self._model_dir,
                    local_files_only=True,
                )
            except Exception as exc:
                logger.warning(
                    "stt_model_unavailable",
                    extra={"model": self._model_name, "error": type(exc).__name__},
                )
                raise SpeechToTextUnavailableError(
                    "model_not_downloaded",
                    f"The speech model '{self._model_name}' is not installed. Run "
                    "infra/scripts/setup-local-stt.sh once (it downloads the model).",
                ) from exc
            _whisper_models[key] = model
            return model

    def check_availability(self) -> tuple[str, str]:
        try:
            self._load()
        except SpeechToTextUnavailableError as exc:
            return exc.code, exc.message
        return "ready", f"Local speech model '{self._model_name}' is ready."

    def transcribe(
        self, audio_bytes: bytes, *, mime_type: str, language: str | None = None
    ) -> str:
        return self.transcribe_detailed(audio_bytes, mime_type=mime_type, language=language).text

    def transcribe_detailed(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str,
        language: str | None = None,
        vocabulary_hint: str | None = None,
    ) -> Transcript:
        _require_wav(mime_type)
        samples, duration = decode_wav_to_mono_16k(audio_bytes)
        if len(samples) == 0:
            return Transcript(text="", duration_seconds=0.0)
        model = self._load()
        started = time.monotonic()
        try:
            with _whisper_lock:
                segments, info = model.transcribe(
                    samples,
                    language=language or self._language,
                    task="transcribe",
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 500},
                    initial_prompt=_join_prompt(self._initial_prompt, vocabulary_hint),
                    condition_on_previous_text=False,
                    temperature=0.0,
                )
                kept = [
                    segment.text.strip()
                    for segment in segments
                    if segment.text.strip() and segment.no_speech_prob < 0.7
                ]
        except SpeechToTextError:
            raise
        except Exception as exc:
            logger.warning("stt_failed", extra={"error": type(exc).__name__})
            raise SpeechToTextError("Speech recognition failed.") from exc
        logger.info(
            "stt_transcribed",
            extra={
                "model": self._model_name,
                "audio_seconds": round(duration, 2),
                "latency_ms": int((time.monotonic() - started) * 1000),
                "language": getattr(info, "language", None),
            },
        )
        return Transcript(
            text=" ".join(kept).strip(),
            language=getattr(info, "language", None),
            duration_seconds=duration,
        )


class OpenAICompatibleSpeechToTextProvider:
    """Sends the recorded audio to an OpenAI-style `/audio/transcriptions`
    server configured in `STT_BASE_URL`/`STT_MODEL` (a self-hosted
    faster-whisper server, or a hosted provider). **The audio leaves this
    machine** -- only enable it deliberately."""

    provider_name = "openai_compatible"

    def __init__(self, settings: Settings) -> None:
        self._base_url = (settings.stt_base_url or "").rstrip("/")
        self._model = settings.stt_model
        self._api_key = settings.stt_api_key
        self._language = settings.stt_language
        self._prompt = settings.stt_initial_prompt or None
        self._timeout = settings.stt_timeout_seconds
        self.model_name = self._model

    def _require_configured(self) -> None:
        if not self._base_url:
            raise SpeechToTextUnavailableError(
                "not_configured", "No speech server is configured. Set STT_BASE_URL and STT_MODEL."
            )

    def check_availability(self) -> tuple[str, str]:
        try:
            self._require_configured()
        except SpeechToTextUnavailableError as exc:
            return exc.code, exc.message
        return "ready", "A speech server is configured (not probed: it would send no audio)."

    def transcribe(
        self, audio_bytes: bytes, *, mime_type: str, language: str | None = None
    ) -> str:
        return self.transcribe_detailed(audio_bytes, mime_type=mime_type, language=language).text

    def transcribe_detailed(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str,
        language: str | None = None,
        vocabulary_hint: str | None = None,
    ) -> Transcript:
        _require_wav(mime_type)
        self._require_configured()
        data = {"model": self._model, "response_format": "json"}
        chosen = language or self._language
        if chosen:
            data["language"] = chosen
        prompt = _join_prompt(self._prompt, vocabulary_hint)
        if prompt:
            data["prompt"] = prompt
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            response = httpx.post(
                f"{self._base_url}/audio/transcriptions",
                data=data,
                files={"file": ("speech.wav", audio_bytes, "audio/wav")},
                headers=headers,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
            )
        except httpx.TimeoutException as exc:
            raise SpeechToTextUnavailableError(
                "timeout", "The speech server took too long to answer."
            ) from exc
        except httpx.HTTPError as exc:
            raise SpeechToTextUnavailableError(
                "unreachable", "The speech server cannot be reached."
            ) from exc
        if response.status_code in (401, 403):
            raise SpeechToTextUnavailableError(
                "unauthorized", "The speech server rejected the credentials."
            )
        if response.status_code >= 400:
            raise SpeechToTextError("Speech recognition failed.")
        try:
            text = response.json()["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SpeechToTextError("Speech recognition failed.") from exc
        return Transcript(text=str(text).strip(), language=chosen)


def get_speech_to_text_provider() -> SpeechToTextProvider:
    """Settings-driven (`SPEECH_TO_TEXT_PROVIDER`). Never switches provider on
    its own; an unusable provider reports why instead."""
    settings = get_settings()
    if settings.speech_to_text_provider == "faster_whisper":
        return WhisperSpeechToTextProvider(settings)
    if settings.speech_to_text_provider == "openai_compatible":
        return OpenAICompatibleSpeechToTextProvider(settings)
    return PocketSphinxSpeechToTextProvider()


__all__ = [
    "OpenAICompatibleSpeechToTextProvider",
    "PocketSphinxSpeechToTextProvider",
    "SpeechToTextError",
    "SpeechToTextProvider",
    "SpeechToTextUnavailableError",
    "Transcript",
    "UnsupportedAudioFormatError",
    "WhisperSpeechToTextProvider",
    "decode_wav_to_mono_16k",
    "get_speech_to_text_provider",
]
