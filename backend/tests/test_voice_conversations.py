"""HTTP-level tests for the voice endpoints (Issue #6): posting a voice
message and playing back an assistant message's synthesized audio. Real
Postgres/Redis/filesystem, no mocks for the application itself — the
only test double used anywhere here is a stub `SpeechToTextProvider`
for one deliberate regression test (see
`test_voice_message_and_text_message_produce_identical_answers_for_the_same_transcript`),
which Issue #6's own testing requirements explicitly allow ("tested
against a mocked or sandboxed provider").
"""

from __future__ import annotations

import io
import uuid
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.storage_provider import LocalStorage, get_storage_provider
from app.voice.stt_provider import get_speech_to_text_provider
from app.voice.tts_provider import EspeakTextToSpeechProvider
from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"
_TXT_BYTES = (
    b"Our refund policy allows returns within thirty days of purchase. "
    b"Contact support for assistance with your return."
)


class _FixedTranscriptSTTProvider:
    """A deliberate test double (Issue #6's testing requirements
    explicitly permit "a mocked or sandboxed provider") -- ignores the
    uploaded audio entirely and always returns the same, predetermined
    transcript. Used only for the voice/text-parity regression test
    below, where the point is proving the *pipeline after transcription*
    behaves identically, not exercising real speech recognition."""

    provider_name = "fixed-transcript-stub"

    def __init__(self, transcript: str) -> None:
        self._transcript = transcript

    def transcribe(self, audio_bytes: bytes, *, mime_type: str) -> str:
        return self._transcript


def _silent_wav_bytes(*, duration_seconds: float = 0.05, frame_rate: int = 16000) -> bytes:
    # Short and deliberate -- see `test_voice_providers.py`'s identical
    # helper comment: PocketSphinx only reports "no speech detected" for
    # a *short* silent clip; a longer one gets decoded as a hallucinated
    # word from the noise floor instead (real, expected ASR behavior,
    # not a bug, but the wrong fixture here).
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * int(frame_rate * duration_seconds))
    return buffer.getvalue()


def _real_voice_audio_bytes(text: str) -> bytes:
    return EspeakTextToSpeechProvider().synthesize(text)


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def _register(client: TestClient, email: str | None = None) -> dict[str, Any]:
    email = email or _unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text


@pytest.fixture(autouse=True)
def _isolated_storage(app: FastAPI, tmp_path: Path) -> Iterator[None]:
    app.dependency_overrides[get_storage_provider] = lambda: LocalStorage(root=str(tmp_path))
    yield
    del app.dependency_overrides[get_storage_provider]


def _create_workspace(client: TestClient, name: str = "Acme") -> dict[str, Any]:
    response = client.post("/api/v1/workspaces", json={"name": name}, headers=csrf_headers(client))
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _add_member(client: TestClient, workspace_id: str, email: str, role: str) -> None:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": email, "role": role},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text


def _upload(client: TestClient, workspace_id: str, *, content: bytes) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("a.txt", content, "text/plain")},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _process(client: TestClient, workspace_id: str, document_id: str) -> Any:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
        headers=csrf_headers(client),
    )


def _ingest_ready_document(client: TestClient, workspace_id: str, *, content: bytes) -> None:
    document = _upload(client, workspace_id, content=content)
    response = _process(client, workspace_id, document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY", response.text


def _create_conversation(client: TestClient, workspace_id: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations", headers=csrf_headers(client)
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _post_voice_message(
    client: TestClient,
    workspace_id: str,
    conversation_id: str,
    audio_bytes: bytes,
    *,
    content_type: str = "audio/wav",
) -> Any:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/voice-messages",
        files={"audio": ("question.wav", audio_bytes, content_type)},
        headers=csrf_headers(client),
    )


def _post_message(client: TestClient, workspace_id: str, conversation_id: str, content: str) -> Any:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        json={"content": content},
        headers=csrf_headers(client),
    )


def _get_message_audio(
    client: TestClient, workspace_id: str, conversation_id: str, message_id: str
) -> Any:
    return client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"
        f"/messages/{message_id}/audio",
        headers=csrf_headers(client),
    )


# --- posting a voice message ------------------------------------------------


def test_posting_a_voice_message_returns_a_transcript_and_grounded_answer_shape(
    client: TestClient,
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    _ingest_ready_document(client, workspace["id"], content=_TXT_BYTES)
    conversation = _create_conversation(client, workspace["id"])

    audio_bytes = _real_voice_audio_bytes("what is the refund policy")
    response = _post_voice_message(client, workspace["id"], conversation["id"], audio_bytes)

    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["transcript"], str)
    assert body["transcript"].strip() != ""
    assert body["message"]["role"] == "ASSISTANT"
    assert isinstance(body["message"]["citations"], list)


def test_voice_message_and_text_message_produce_identical_answers_for_the_same_transcript(
    client: TestClient, app: FastAPI
) -> None:
    # The regression check Issue #6 explicitly requires: a voice-driven
    # question and its text-chat equivalent must produce the same
    # grounded/citation behavior from the existing (Issue #4) pipeline --
    # proving voice never forked it. Uses a stub STT provider (a
    # deliberate, explicitly-permitted test double) so the *transcript*
    # is controlled and identical between the two calls; everything from
    # that point on runs through the real, unmodified pipeline.
    _register(client)
    workspace = _create_workspace(client)
    _ingest_ready_document(client, workspace["id"], content=_TXT_BYTES)

    question = "What is the refund policy?"
    app.dependency_overrides[get_speech_to_text_provider] = lambda: _FixedTranscriptSTTProvider(
        question
    )
    try:
        voice_conversation = _create_conversation(client, workspace["id"])
        voice_response = _post_voice_message(
            client, workspace["id"], voice_conversation["id"], _silent_wav_bytes()
        )
    finally:
        del app.dependency_overrides[get_speech_to_text_provider]
    assert voice_response.status_code == 201, voice_response.text
    voice_body = voice_response.json()
    assert voice_body["transcript"] == question

    text_conversation = _create_conversation(client, workspace["id"])
    text_response = _post_message(client, workspace["id"], text_conversation["id"], question)
    assert text_response.status_code == 201, text_response.text
    text_body = text_response.json()

    assert voice_body["message"]["content"] == text_body["content"]
    voice_citations = [
        {k: v for k, v in c.items() if k != "rank"} for c in voice_body["message"]["citations"]
    ]
    text_citations = [{k: v for k, v in c.items() if k != "rank"} for c in text_body["citations"]]
    assert voice_citations == text_citations


def test_posting_silent_audio_returns_empty_transcript_error(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    conversation = _create_conversation(client, workspace["id"])

    response = _post_voice_message(client, workspace["id"], conversation["id"], _silent_wav_bytes())
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "empty_transcript"


def test_posting_unsupported_audio_format_is_rejected(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    conversation = _create_conversation(client, workspace["id"])

    response = _post_voice_message(
        client,
        workspace["id"],
        conversation["id"],
        b"not really mp3 data",
        content_type="audio/mpeg",
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "unsupported_audio_format"


def test_oversized_voice_audio_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_voice_audio_size_bytes", 10)
    _register(client)
    workspace = _create_workspace(client)
    conversation = _create_conversation(client, workspace["id"])

    response = _post_voice_message(client, workspace["id"], conversation["id"], _silent_wav_bytes())
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "voice_audio_too_large"


def test_voice_message_conversation_not_found_returns_404(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    response = _post_voice_message(client, workspace["id"], str(uuid.uuid4()), _silent_wav_bytes())
    assert response.status_code == 404


def test_viewer_cannot_post_a_voice_message(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    conversation = _create_conversation(owner, workspace["id"])

    viewer_email = _unique_email()
    _register(client_factory(), viewer_email)
    _add_member(owner, workspace["id"], viewer_email, "VIEWER")
    viewer = client_factory()
    _login(viewer, viewer_email)

    response = _post_voice_message(viewer, workspace["id"], conversation["id"], _silent_wav_bytes())
    assert response.status_code == 403


def test_voice_message_rate_limit_enforced_at_threshold(
    client: TestClient, app: FastAPI
) -> None:
    # Rate limiting is enforced before transcription ever runs (see
    # `post_voice_message()`), so the transcript content is irrelevant
    # here -- a stub STT provider keeps this fast and avoids a real,
    # observed risk with genuine STT: a real token bucket refills
    # continuously, and 21 real (CPU-bound, ~0.3-0.5s each) transcription
    # calls take long enough wall-clock time for a token or two to refill
    # mid-loop, occasionally letting the 21st request through.
    app.dependency_overrides[get_speech_to_text_provider] = lambda: _FixedTranscriptSTTProvider(
        "irrelevant question"
    )
    try:
        _register(client)
        workspace = _create_workspace(client)
        conversation = _create_conversation(client, workspace["id"])

        last_status = None
        for _ in range(21):
            last_status = _post_voice_message(
                client, workspace["id"], conversation["id"], _silent_wav_bytes()
            ).status_code
        assert last_status == 429
    finally:
        del app.dependency_overrides[get_speech_to_text_provider]


def test_cross_workspace_voice_message_is_not_reachable(
    client_factory: Callable[[], TestClient],
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    conversation = _create_conversation(owner_a, workspace_a["id"])

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = _post_voice_message(
        owner_b, workspace_b["id"], conversation["id"], _silent_wav_bytes()
    )
    assert response.status_code == 404


# --- audio playback ----------------------------------------------------


def test_get_message_audio_returns_wav_audio_for_an_assistant_message(
    client: TestClient,
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    _ingest_ready_document(client, workspace["id"], content=_TXT_BYTES)
    conversation = _create_conversation(client, workspace["id"])
    posted = _post_message(
        client, workspace["id"], conversation["id"], "What is the refund policy?"
    )
    assert posted.status_code == 201, posted.text
    message_id = posted.json()["id"]

    response = _get_message_audio(client, workspace["id"], conversation["id"], message_id)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content)) as wav_file:
        assert wav_file.getnframes() > 0


def test_get_message_audio_for_a_user_message_is_not_found(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    conversation = _create_conversation(client, workspace["id"])
    posted = _post_message(client, workspace["id"], conversation["id"], "anything")
    assert posted.status_code == 201, posted.text

    messages = client.get(
        f"/api/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/messages",
        headers=csrf_headers(client),
    ).json()
    user_message_id = next(m["id"] for m in messages if m["role"] == "USER")

    response = _get_message_audio(client, workspace["id"], conversation["id"], user_message_id)
    assert response.status_code == 404


def test_get_message_audio_from_another_workspace_is_not_reachable(
    client_factory: Callable[[], TestClient],
) -> None:
    owner_a = client_factory()
    _register(owner_a)
    workspace_a = _create_workspace(owner_a, name="A")
    conversation_a = _create_conversation(owner_a, workspace_a["id"])
    posted = _post_message(owner_a, workspace_a["id"], conversation_a["id"], "anything")
    assert posted.status_code == 201, posted.text
    message_id = posted.json()["id"]

    owner_b = client_factory()
    _register(owner_b)
    workspace_b = _create_workspace(owner_b, name="B")

    response = _get_message_audio(owner_b, workspace_b["id"], conversation_a["id"], message_id)
    assert response.status_code == 404
