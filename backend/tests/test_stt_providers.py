"""Speech-to-text provider mechanics (ADR 0010) that do not need a real
speech model: WAV decoding/resampling, the 'model is never downloaded during
a request' guarantee, and the OpenAI-compatible adapter over real HTTP.
(Real-model accuracy is checked separately: tests/test_whisper_real.py.)"""

from __future__ import annotations

import contextlib
import io
import json
import struct
import threading
import wave
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.voice.stt_provider import (
    OpenAICompatibleSpeechToTextProvider,
    PocketSphinxSpeechToTextProvider,
    SpeechToTextError,
    SpeechToTextUnavailableError,
    UnsupportedAudioFormatError,
    WhisperSpeechToTextProvider,
    _join_prompt,
    decode_wav_to_mono_16k,
    get_speech_to_text_provider,
)


def _wav(*, rate: int = 16000, channels: int = 1, seconds: float = 0.5, width: int = 2) -> bytes:
    frames = int(rate * seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(width)
        wav_file.setframerate(rate)
        if width != 2:
            wav_file.writeframes(b"\x00" * frames * width * channels)
        elif channels == 1:
            wav_file.writeframes(
                b"".join(struct.pack("<h", int(8000 * (i % 50 / 50 - 0.5))) for i in range(frames))
            )
        else:  # left +100, right -100: the mono mix is ~0
            wav_file.writeframes(b"".join(struct.pack("<hh", 100, -100) for _ in range(frames)))
    return buffer.getvalue()


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+psycopg://x:y@localhost/z",
        "secret_key": "test-secret-key-for-pytest-only-not-a-real-secret",
    }
    values.update(overrides)
    return Settings(**values)


# --- WAV decoding -----------------------------------------------------------------


def test_decode_keeps_16k_mono_untouched() -> None:
    samples, duration = decode_wav_to_mono_16k(_wav(rate=16000, seconds=0.5))
    assert len(samples) == 8000 and duration == pytest.approx(0.5)
    assert samples.dtype.name == "float32"


def test_decode_resamples_48k_stereo_to_16k_mono() -> None:
    samples, duration = decode_wav_to_mono_16k(_wav(rate=48000, channels=2, seconds=1.0))
    assert len(samples) == pytest.approx(16000, abs=2)
    assert duration == pytest.approx(1.0)
    assert float(abs(samples).max()) < 0.01  # stereo L=100,R=-100 averages to ~0


@pytest.mark.parametrize("bad", [b"not a wav at all", b"", b"RIFF\x00\x00\x00\x00WAVE"])
def test_decode_rejects_garbage(bad: bytes) -> None:
    with pytest.raises(SpeechToTextError):
        decode_wav_to_mono_16k(bad)


def test_decode_rejects_non_16_bit_audio() -> None:
    with pytest.raises(SpeechToTextError, match="16-bit"):
        decode_wav_to_mono_16k(_wav(width=1))


# --- local whisper without a model --------------------------------------------------


def test_whisper_never_downloads_during_a_request(tmp_path: Path) -> None:
    provider = WhisperSpeechToTextProvider(
        _settings(stt_model="tiny", stt_model_dir=str(tmp_path / "empty"))
    )

    status, message = provider.check_availability()
    assert status == "model_not_downloaded"
    assert "setup-local-stt.sh" in message
    with pytest.raises(SpeechToTextUnavailableError) as raised:
        provider.transcribe(_wav(), mime_type="audio/wav")
    assert raised.value.code == "model_not_downloaded"
    assert not (tmp_path / "empty").exists() or not any((tmp_path / "empty").iterdir())


def test_whisper_checks_the_format_before_loading_anything() -> None:
    provider = WhisperSpeechToTextProvider(_settings(stt_model="tiny"))
    with pytest.raises(UnsupportedAudioFormatError):
        provider.transcribe(b"x", mime_type="audio/mpeg")


def test_empty_audio_is_an_empty_transcript_not_an_error(tmp_path: Path) -> None:
    provider = WhisperSpeechToTextProvider(_settings(stt_model_dir=str(tmp_path)))
    empty = _wav(seconds=0.0)
    assert provider.transcribe_detailed(empty, mime_type="audio/wav").text == ""


def test_factory_selects_providers_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, expected in (
        ("local", PocketSphinxSpeechToTextProvider),
        ("pocketsphinx", PocketSphinxSpeechToTextProvider),
        ("faster_whisper", WhisperSpeechToTextProvider),
        ("openai_compatible", OpenAICompatibleSpeechToTextProvider),
    ):
        monkeypatch.setattr(
            "app.voice.stt_provider.get_settings",
            lambda n=name: _settings(speech_to_text_provider=n),
        )
        assert isinstance(get_speech_to_text_provider(), expected)


# --- OpenAI-compatible adapter ----------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.status = 200
        self.body: Any = {"text": " explain program one "}


@pytest.fixture
def stt_server() -> Iterator[tuple[str, _Recorder]]:
    recorder = _Recorder()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            recorder.requests.append(
                {"path": self.path, "headers": dict(self.headers), "body": body}
            )
            raw = json.dumps(recorder.body).encode()
            self.send_response(recorder.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(raw)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/v1", recorder
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_openai_compatible_stt_posts_the_audio_with_model_language_and_prompt(
    stt_server: tuple[str, _Recorder],
) -> None:
    url, recorder = stt_server
    provider = OpenAICompatibleSpeechToTextProvider(
        _settings(
            stt_base_url=url, stt_model="whisper-1", stt_api_key="sk-SECRET-123", stt_language="en"
        )
    )

    transcript = provider.transcribe_detailed(_wav(), mime_type="audio/wav", language="hi")

    request = recorder.requests[0]
    assert request["path"] == "/v1/audio/transcriptions"
    assert request["headers"]["Authorization"] == "Bearer sk-SECRET-123"
    body = request["body"]
    assert b'name="model"' in body and b"whisper-1" in body
    assert b'name="language"' in body and b"\r\n\r\nhi\r\n" in body  # request language wins
    assert b'name="prompt"' in body and b"RIFF" in body  # prompt + the WAV bytes
    assert transcript.text == "explain program one"


@pytest.mark.parametrize(
    ("status", "code"), [(401, "unauthorized"), (403, "unauthorized")]
)
def test_openai_compatible_stt_reports_auth_failures(
    stt_server: tuple[str, _Recorder], status: int, code: str
) -> None:
    url, recorder = stt_server
    recorder.status = status
    provider = OpenAICompatibleSpeechToTextProvider(_settings(stt_base_url=url, stt_api_key="k"))
    with pytest.raises(SpeechToTextUnavailableError) as raised:
        provider.transcribe(_wav(), mime_type="audio/wav")
    assert raised.value.code == code and raised.value.message != "k"


def test_openai_compatible_stt_unconfigured_and_unreachable() -> None:
    unconfigured = OpenAICompatibleSpeechToTextProvider(_settings())
    assert unconfigured.check_availability()[0] == "not_configured"
    with pytest.raises(SpeechToTextUnavailableError) as raised:
        unconfigured.transcribe(_wav(), mime_type="audio/wav")
    assert raised.value.code == "not_configured"

    dead = OpenAICompatibleSpeechToTextProvider(_settings(stt_base_url="http://127.0.0.1:9/v1"))
    with pytest.raises(SpeechToTextUnavailableError) as raised2:
        dead.transcribe(_wav(), mime_type="audio/wav")
    assert raised2.value.code == "unreachable" and "127.0.0.1" not in raised2.value.message


def test_openai_compatible_stt_bad_body_is_a_failure_not_a_crash(
    stt_server: tuple[str, _Recorder],
) -> None:
    url, recorder = stt_server
    recorder.body = {"unexpected": True}
    provider = OpenAICompatibleSpeechToTextProvider(_settings(stt_base_url=url))
    with pytest.raises(SpeechToTextError):
        provider.transcribe(_wav(), mime_type="audio/wav")


def test_prompt_joins_generic_text_and_vocabulary_and_is_capped() -> None:
    assert _join_prompt(None, None) is None
    assert _join_prompt("  ", "") is None
    assert _join_prompt("generic.", "Terms: bubble sort.") == "generic. Terms: bubble sort."
    long = _join_prompt("g" * 300, "Terms: " + "x" * 300)
    assert long is not None and len(long) == 400 and long.endswith("x")  # the vocabulary survives
