"""Validation of an uploaded voice recording (shared by the voice-message
and the transcription endpoints). Bounded reads, header-only duration check.
"""

from __future__ import annotations

import io
import wave

from fastapi import HTTPException, UploadFile, status

MAX_VOICE_AUDIO_DURATION_SECONDS = 120.0
VOICE_UPLOAD_CHUNK_SIZE = 1024 * 1024


def voice_audio_too_large_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={
            "code": "voice_audio_too_large",
            "message": "The uploaded audio exceeds the maximum allowed size or duration.",
        },
    )


async def read_and_validate_voice_upload(upload: UploadFile, *, max_size_bytes: int) -> bytes:
    """Streams the upload in bounded chunks -- never buffers an
    arbitrarily large payload first and checks its length afterward.
    Mirrors `document_service._read_and_validate_size()`'s identical
    pattern."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(VOICE_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise voice_audio_too_large_error()
        chunks.append(chunk)
    return b"".join(chunks)


def validate_wav_duration(audio_bytes: bytes, *, max_duration_seconds: float) -> None:
    """A lightweight header-only check (no full decode). A file that
    fails to parse as WAV here is deliberately let through unrejected --
    `SpeechToTextProvider.transcribe()` is the single source of truth
    for "is this genuinely valid, readable audio," so a malformed file
    fails there with the correct `transcription_failed` outcome instead
    of a misleading `voice_audio_too_large` one."""
    try:
        with wave.open(io.BytesIO(audio_bytes)) as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return
            duration = wav_file.getnframes() / frame_rate
    except (wave.Error, EOFError):
        return
    if duration > max_duration_seconds:
        raise voice_audio_too_large_error()



__all__ = [
    "MAX_VOICE_AUDIO_DURATION_SECONDS",
    "read_and_validate_voice_upload",
    "validate_wav_duration",
    "voice_audio_too_large_error",
]
