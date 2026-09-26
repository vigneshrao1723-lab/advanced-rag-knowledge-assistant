"""Speech-to-text provider abstraction (docs/ARCHITECTURE.md "Provider
abstractions", GitHub Issue #6).

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
from typing import Protocol

import speech_recognition as sr

_SUPPORTED_MIME_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/wave"})


class SpeechToTextError(Exception):
    """Any transcription failure — treated by the calling endpoint as an
    expected, handled `422`/`500` outcome, never a raw stack trace.
    Never includes provider-internal detail (no library exception text)
    in the message, matching `EmbeddingError`'s own convention."""


class UnsupportedAudioFormatError(SpeechToTextError):
    """The uploaded audio's declared MIME type isn't one this provider
    can read. Raised before any audio bytes are actually parsed."""


class SpeechToTextProvider(Protocol):
    provider_name: str

    def transcribe(self, audio_bytes: bytes, *, mime_type: str) -> str:
        """Returns the transcribed text — an empty string if the audio
        contains no recognizable speech (a defined, non-crashing result,
        not an error). Raises `UnsupportedAudioFormatError` for an
        unrecognized `mime_type`, `SpeechToTextError` for anything else
        that prevents transcription (corrupt audio, a provider-internal
        failure)."""
        ...


class PocketSphinxSpeechToTextProvider:
    """Offline, no API key, no network call. Only reads WAV audio (PCM,
    any sample rate `speech_recognition`'s `AudioFile` accepts) — this
    project's frontend is responsible for encoding recorded audio to WAV
    client-side before upload (see `frontend/lib/wav-encoder.ts`), the
    same "validate/normalize at the boundary" precedent as document
    upload's extension/MIME/magic-byte checks."""

    provider_name = "pocketsphinx"

    def transcribe(self, audio_bytes: bytes, *, mime_type: str) -> str:
        if mime_type not in _SUPPORTED_MIME_TYPES:
            raise UnsupportedAudioFormatError(
                f"Unsupported audio format: {mime_type}. Only WAV audio is supported."
            )

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
            return ""
        except Exception as exc:
            raise SpeechToTextError("Speech recognition failed.") from exc

        return str(text)


def get_speech_to_text_provider() -> SpeechToTextProvider:
    """`PocketSphinxSpeechToTextProvider` is the only implementation
    today — this gains a branch on `Settings.speech_to_text_provider`
    (matching `get_storage_provider()`/`get_embedding_provider()`'s
    pattern) when a second, real implementation is actually added, not
    before."""
    return PocketSphinxSpeechToTextProvider()


__all__ = [
    "PocketSphinxSpeechToTextProvider",
    "SpeechToTextError",
    "SpeechToTextProvider",
    "UnsupportedAudioFormatError",
    "get_speech_to_text_provider",
]
