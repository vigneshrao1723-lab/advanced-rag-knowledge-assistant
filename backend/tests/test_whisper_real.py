"""Opt-in checks against the REAL local speech model (faster-whisper).

Skipped unless the model is already installed (infra/scripts/setup-local-stt.sh)
-- CI and a fresh checkout never download one. Audio is synthesised with
espeak-ng, so this proves the pipeline (WAV -> model -> text) and that
technical phrases come back readable; it does NOT prove accuracy on real human
voices or accents, which only a manual test with a microphone can.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import pytest

from app.core.config import get_settings
from app.voice.stt_provider import WhisperSpeechToTextProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_WHISPER_TESTS") != "1" or shutil.which("espeak-ng") is None,
    reason="set RUN_WHISPER_TESTS=1 with espeak-ng and an installed speech model",
)


def _speak(text: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        subprocess.run(["espeak-ng", "-s", "150", "-w", handle.name, text], check=True)
        return handle.read()


# The product passes the workspace's own titles as a hint (app/voice/vocabulary.py).
# Without it the synthetic voice's "bubble sort" is heard as "verbal sort".
_LAB_HINT = "Terms: Bubble sort, Factorial using recursion, Sum of an array with MPI_Reduce."


@pytest.mark.parametrize(
    ("spoken", "hint", "must_contain"),
    [
        ("Explain program number five", None, ["program", "5"]),
        ("What is the output of the bubble sort program", _LAB_HINT, ["output", "bubble", "sort"]),
        ("Explain MPI reduce line by line", None, ["reduce", "line"]),
    ],
)
def test_real_model_transcribes_technical_phrases(
    spoken: str, hint: str | None, must_contain: list[str]
) -> None:
    provider = WhisperSpeechToTextProvider(get_settings())  # model/dir from STT_* settings
    assert provider.check_availability()[0] == "ready"

    transcript = provider.transcribe_detailed(
        _speak(spoken), mime_type="audio/wav", vocabulary_hint=hint
    )

    text = transcript.text.lower().replace("five", "5").replace("five.", "5")
    print(f"{spoken!r} -> {transcript.text!r} ({transcript.language})")
    for word in must_contain:
        assert word in text, (spoken, transcript.text)


def test_real_model_returns_nothing_for_silence() -> None:
    import struct
    import wave
    from io import BytesIO

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(struct.pack("<h", 0) * 16000 * 2)

    transcript = WhisperSpeechToTextProvider(get_settings()).transcribe_detailed(
        buffer.getvalue(), mime_type="audio/wav"
    )

    assert transcript.text == ""
