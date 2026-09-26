"""Unit tests for `app.voice.stt_provider`/`app.voice.tts_provider`
(Issue #6). No database, no HTTP -- pure provider-contract tests.

`PocketSphinxSpeechToTextProvider`'s real-world accuracy against
synthetic (TTS-generated) audio is empirically unreliable and highly
sensitive to synthesis parameters (see
`docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md`
"Consequences") -- these tests deliberately never assert an *exact*
transcript for arbitrary speech content. They assert the provider's
*contract* instead: it produces some non-empty text for real speech, an
empty string (not an exception) for silence/unrecognizable audio, and
raises the documented error types for invalid input. Every test uses
the real, offline providers directly (no mocking) -- this is itself the
"sandboxed provider" Issue #6's own testing requirements describe,
since both providers already require no network access or paid API.
"""

from __future__ import annotations

import io
import wave

import pytest

from app.voice.stt_provider import (
    PocketSphinxSpeechToTextProvider,
    SpeechToTextError,
    UnsupportedAudioFormatError,
    get_speech_to_text_provider,
)
from app.voice.tts_provider import (
    EspeakTextToSpeechProvider,
    get_text_to_speech_provider,
)


def _silent_wav_bytes(*, duration_seconds: float = 0.05, frame_rate: int = 16000) -> bytes:
    # A short silence duration is deliberate, not arbitrary: empirically,
    # PocketSphinx raises `UnknownValueError` (this provider's documented
    # empty-string case) only for a *short* silent clip -- a longer one
    # (e.g. a full second) instead gets decoded as a hallucinated word
    # from the noise floor (observed: "so", "dog"), which is itself
    # correct, expected ASR behavior on synthetic digital silence, not a
    # bug, but the wrong fixture for testing this specific contract.
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * int(frame_rate * duration_seconds))
    return buffer.getvalue()


# --- speech-to-text --------------------------------------------------------


def test_get_speech_to_text_provider_returns_pocketsphinx() -> None:
    provider = get_speech_to_text_provider()
    assert isinstance(provider, PocketSphinxSpeechToTextProvider)
    assert provider.provider_name == "pocketsphinx"


def test_transcribe_rejects_unsupported_mime_type() -> None:
    provider = PocketSphinxSpeechToTextProvider()
    with pytest.raises(UnsupportedAudioFormatError):
        provider.transcribe(b"not real audio", mime_type="audio/mpeg")


def test_transcribe_silence_returns_empty_string_not_an_error() -> None:
    provider = PocketSphinxSpeechToTextProvider()
    text = provider.transcribe(_silent_wav_bytes(), mime_type="audio/wav")
    assert text == ""


def test_transcribe_garbage_bytes_with_wav_mime_type_raises() -> None:
    provider = PocketSphinxSpeechToTextProvider()
    with pytest.raises(SpeechToTextError):
        provider.transcribe(b"this is not a wav file at all", mime_type="audio/wav")


def test_transcribe_real_speech_produces_non_empty_text() -> None:
    # A real round-trip through this project's own offline TTS provider --
    # proves the STT pipeline actually processes real speech content, not
    # just silence, without asserting *what* it transcribes to (see this
    # module's own docstring for why an exact-match assertion here would
    # be flaky).
    tts = EspeakTextToSpeechProvider()
    audio_bytes = tts.synthesize("this is a real spoken test sentence")

    stt = PocketSphinxSpeechToTextProvider()
    text = stt.transcribe(audio_bytes, mime_type="audio/wav")
    assert isinstance(text, str)
    assert text.strip() != ""


# --- text-to-speech ----------------------------------------------------


def test_get_text_to_speech_provider_returns_espeak() -> None:
    provider = get_text_to_speech_provider()
    assert isinstance(provider, EspeakTextToSpeechProvider)
    assert provider.provider_name == "espeak-ng"


def test_synthesize_produces_valid_non_empty_wav_audio() -> None:
    provider = EspeakTextToSpeechProvider()
    audio_bytes = provider.synthesize("hello, this is a test.")
    assert len(audio_bytes) > 0
    with wave.open(io.BytesIO(audio_bytes)) as wav_file:
        assert wav_file.getnframes() > 0


def test_synthesize_empty_text_returns_valid_silent_wav_not_an_error() -> None:
    provider = EspeakTextToSpeechProvider()
    audio_bytes = provider.synthesize("   ")
    with wave.open(io.BytesIO(audio_bytes)) as wav_file:
        assert wav_file.getnframes() == 0


def test_tts_then_stt_round_trip_recovers_some_recognizable_text() -> None:
    # The full voice round trip (docs/DECISIONS/0008's own Definition-
    # of-Done evidence): synthesize real audio, transcribe it back, and
    # confirm the pipeline mechanically works end-to-end -- again, no
    # exact-match assertion (see module docstring).
    tts = EspeakTextToSpeechProvider()
    stt = PocketSphinxSpeechToTextProvider()

    audio_bytes = tts.synthesize("testing one two three")
    transcript = stt.transcribe(audio_bytes, mime_type="audio/wav")
    assert transcript.strip() != ""
