"""Text-to-speech provider abstraction (docs/ARCHITECTURE.md "Provider
abstractions", GitHub Issue #6).

Mirrors `stt_provider.py`'s shape exactly: a `Protocol`, one concrete
implementation today, and a settings-driven factory
(`get_text_to_speech_provider()`). `EspeakTextToSpeechProvider` is a
genuine, fully offline synthesizer (the `espeak-ng` command-line tool —
see `infra/docker/backend.Dockerfile`) that needs no API key and no
network call. Synthesized speech is robotic (espeak's own voice), a
known, honest limitation, not a bug.

Shells out to the real `espeak-ng` binary (`-w <file>` writes a WAV file
directly) rather than going through the `pyttsx3` Python bindings:
`pyttsx3`'s espeak driver caches internal callback/proxy state at the
process level, and empirically, repeated `synthesize()` calls within one
process (especially across different `asyncio.to_thread()` worker
threads) corrupted that state (`ReferenceError: weakly-referenced
object no longer exists`), sometimes producing a truncated/empty audio
file. Invoking `espeak-ng` as a subprocess has no such shared state
between calls — each invocation is a fresh, independent process.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import wave
from typing import Protocol

_ESPEAK_TIMEOUT_SECONDS = 15


class TextToSpeechError(Exception):
    """Any synthesis failure — treated by the calling endpoint as an
    expected, handled outcome, never a raw stack trace. Never includes
    provider-internal detail (no subprocess output) in the message,
    matching `SpeechToTextError`'s own convention."""


class TextToSpeechProvider(Protocol):
    provider_name: str

    def synthesize(self, text: str) -> bytes:
        """Returns WAV audio bytes for the given text. Empty/whitespace
        text returns a minimal, valid, silent WAV (a defined,
        non-crashing result) rather than invoking the synthesizer.
        Raises `TextToSpeechError` on a provider-internal failure."""
        ...


def _silent_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"")
    return buffer.getvalue()


class EspeakTextToSpeechProvider:
    provider_name = "espeak-ng"

    def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return _silent_wav()

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            result = subprocess.run(
                ["espeak-ng", "-w", path, text],
                capture_output=True,
                timeout=_ESPEAK_TIMEOUT_SECONDS,
                check=False,
            )
            if result.returncode != 0:
                raise TextToSpeechError("Speech synthesis failed.")
            with open(path, "rb") as audio_file:
                audio_bytes = audio_file.read()
        except (OSError, subprocess.SubprocessError) as exc:
            raise TextToSpeechError("Speech synthesis failed.") from exc
        finally:
            os.unlink(path)

        if not audio_bytes:
            raise TextToSpeechError("Speech synthesis produced no audio.")
        return audio_bytes


def get_text_to_speech_provider() -> TextToSpeechProvider:
    """`EspeakTextToSpeechProvider` is the only implementation today —
    this gains a branch on `Settings.text_to_speech_provider` (matching
    `get_speech_to_text_provider()`'s pattern) when a second, real
    implementation is actually added, not before."""
    return EspeakTextToSpeechProvider()


__all__ = [
    "EspeakTextToSpeechProvider",
    "TextToSpeechError",
    "TextToSpeechProvider",
    "get_text_to_speech_provider",
]
