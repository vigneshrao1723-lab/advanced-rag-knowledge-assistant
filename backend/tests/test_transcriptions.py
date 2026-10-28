"""POST /workspaces/{id}/transcriptions: recording -> transcript for review,
without touching the conversation (ADR 0010). Real Postgres/auth/rate
limiter; the recognizer is scripted so error paths are exact."""

from __future__ import annotations

import io
import struct
import wave
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.voice.stt_provider import (
    SpeechToTextError,
    SpeechToTextUnavailableError,
    Transcript,
    UnsupportedAudioFormatError,
    get_speech_to_text_provider,
)
from tests.conftest import csrf_headers
from tests.test_conversations import _add_member, _create_workspace, _login, _register


def _wav(seconds: float = 0.2, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"".join(struct.pack("<h", 500) for _ in range(int(rate * seconds))))
    return buffer.getvalue()


class ScriptedStt:
    provider_name = "scripted"
    model_name = "scripted-model"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result: Transcript = Transcript(
            text="explain program one", language="en", duration_seconds=1.5
        )
        self.error: Exception | None = None

    def transcribe(self, audio_bytes: bytes, *, mime_type: str, language: str | None = None) -> str:
        return self.transcribe_detailed(audio_bytes, mime_type=mime_type, language=language).text

    def transcribe_detailed(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str,
        language: str | None = None,
        vocabulary_hint: str | None = None,
    ) -> Transcript:
        self.calls.append(
            {
                "bytes": len(audio_bytes),
                "mime": mime_type,
                "language": language,
                "hint": vocabulary_hint,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result

    def check_availability(self) -> tuple[str, str]:
        return "ready", "ok"


@pytest.fixture
def stt(app: FastAPI) -> ScriptedStt:
    scripted = ScriptedStt()
    app.dependency_overrides[get_speech_to_text_provider] = lambda: scripted
    return scripted


def _post(
    client: TestClient,
    workspace_id: str,
    *,
    audio: bytes | None = None,
    content_type: str = "audio/wav",
    language: str | None = None,
) -> Any:
    data = {"language": language} if language is not None else None
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/transcriptions",
        files={"audio": ("speech.wav", _wav() if audio is None else audio, content_type)},
        data=data,
        headers=csrf_headers(client),
    )


def test_returns_the_transcript_with_provider_details_and_no_side_effects(
    client: TestClient, stt: ScriptedStt, db_session: DbSession
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    before = (
        db_session.scalar(select(func.count()).select_from(Message)),
        db_session.scalar(select(func.count()).select_from(Conversation)),
    )

    response = _post(client, workspace["id"])

    assert response.status_code == 200, response.text
    assert response.json() == {
        "transcript": "explain program one",
        "language": "en",
        "duration_seconds": 1.5,
        "provider": "scripted",
        "model": "scripted-model",
    }
    # Transcribing is not asking: no conversation or message was created.
    after = (
        db_session.scalar(select(func.count()).select_from(Message)),
        db_session.scalar(select(func.count()).select_from(Conversation)),
    )
    assert after == before
    assert stt.calls[0]["language"] is None and stt.calls[0]["mime"] == "audio/wav"


def test_language_hint_is_normalised(client: TestClient, stt: ScriptedStt) -> None:
    _register(client)
    workspace = _create_workspace(client)

    cases = (("EN", "en"), ("auto", None), ("", None), (" hi ", "hi"), ("pt-BR", "pt-br"))
    for sent, expected in cases:
        assert _post(client, workspace["id"], language=sent).status_code == 200
        assert stt.calls[-1]["language"] == expected, sent


@pytest.mark.parametrize("bad", ["english!", "e", "../etc", "x" * 10])
def test_invalid_language_is_rejected_before_the_recognizer_runs(
    client: TestClient, stt: ScriptedStt, bad: str
) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = _post(client, workspace["id"], language=bad)

    assert response.status_code == 422
    assert response.json()["error"]["code"] in ("invalid_language", "validation_error")
    assert stt.calls == []


def test_empty_transcript_is_a_normal_result_not_an_error(
    client: TestClient, stt: ScriptedStt
) -> None:
    stt.result = Transcript(text="", language=None, duration_seconds=0.2)
    _register(client)
    workspace = _create_workspace(client)

    response = _post(client, workspace["id"])

    assert response.status_code == 200 and response.json()["transcript"] == ""


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (
            SpeechToTextUnavailableError(
                "model_not_downloaded", "The speech model is not installed."
            ),
            503,
            "stt_unavailable",
        ),
        (UnsupportedAudioFormatError("nope"), 400, "unsupported_audio_format"),
        (SpeechToTextError("boom: secret internals"), 422, "transcription_failed"),
    ],
)
def test_provider_failures_map_to_clear_errors_without_internals(
    client: TestClient, stt: ScriptedStt, error: Exception, status: int, code: str
) -> None:
    stt.error = error
    _register(client)
    workspace = _create_workspace(client)

    response = _post(client, workspace["id"])

    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code
    assert "secret internals" not in body["message"] and "boom" not in body["message"]
    if status == 503:
        assert "not installed" in body["message"]


def test_oversize_and_overlong_recordings_are_rejected(
    client: TestClient, stt: ScriptedStt
) -> None:
    _register(client)
    workspace = _create_workspace(client)

    too_big = _post(client, workspace["id"], audio=b"RIFF" + b"\0" * (11 * 1024 * 1024))
    too_long = _post(client, workspace["id"], audio=_wav(seconds=130.0, rate=8000))

    assert too_big.status_code == 413 and too_long.status_code == 413
    assert stt.calls == []


def test_requires_login_membership_and_member_role(
    client_factory: Callable[[], TestClient], app: FastAPI, stt: ScriptedStt
) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)

    anonymous = client_factory()
    anonymous.get("/api/v1/auth/csrf")
    assert _post(anonymous, workspace["id"]).status_code == 401

    outsider = client_factory()
    _register(outsider)
    assert _post(outsider, workspace["id"]).status_code == 404  # not a member: non-leaking

    viewer = client_factory()
    viewer_email = _register(viewer)["user"]["email"]
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    _login(viewer, viewer_email)
    assert _post(viewer, workspace["id"]).status_code == 403

    assert stt.calls == []


def test_capabilities_reports_the_recognizer_status(client: TestClient, app: FastAPI) -> None:
    class Down(ScriptedStt):
        def check_availability(self) -> tuple[str, str]:
            return "model_not_downloaded", "The speech model 'small' is not installed."

    app.dependency_overrides[get_speech_to_text_provider] = lambda: Down()
    _register(client)

    stt_status = client.get("/api/v1/system/capabilities").json()["stt"]

    assert stt_status["status"] == "model_not_downloaded"
    assert stt_status["provider"] == "scripted" and stt_status["model"] == "scripted-model"


def _upload_ready_text(client: TestClient, workspace_id: str, filename: str, text: str) -> None:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, text.encode(), "text/plain")},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    processed = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{response.json()['id']}/process",
        headers=csrf_headers(client),
    )
    assert processed.json()["status"] == "READY", processed.text


def test_recognition_is_biased_toward_the_workspaces_own_titles_and_filenames(
    client: TestClient, stt: ScriptedStt
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    _upload_ready_text(
        client,
        workspace["id"],
        "PC_Lab_Manual.txt",
        "Program 3: Bubble sort\nSorts numbers.\n\nProgram 4: Factorial using recursion\nn!",
    )

    assert _post(client, workspace["id"]).status_code == 200

    hint = stt.calls[0]["hint"]
    assert hint is not None
    assert "Bubble sort" in hint and "Factorial using recursion" in hint
    assert "pc lab manual" in hint.lower()


def test_the_vocabulary_hint_never_includes_another_workspaces_terms(
    client_factory: Callable[[], TestClient], stt: ScriptedStt
) -> None:
    owner = client_factory()
    _register(owner)
    owner_ws = _create_workspace(owner)
    _upload_ready_text(
        owner, owner_ws["id"], "secret_plan.txt", "Program 1: Confidential merger\nx"
    )

    other = client_factory()
    _register(other)
    other_ws = _create_workspace(other, name="Other")
    assert _post(other, other_ws["id"]).status_code == 200

    assert stt.calls[0]["hint"] is None  # nothing of the owner's leaks into this workspace


def test_a_workspace_without_documents_sends_no_hint(client: TestClient, stt: ScriptedStt) -> None:
    _register(client)
    workspace = _create_workspace(client)
    assert _post(client, workspace["id"]).status_code == 200
    assert stt.calls[0]["hint"] is None
