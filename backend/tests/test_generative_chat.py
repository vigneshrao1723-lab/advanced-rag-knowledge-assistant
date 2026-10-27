"""HTTP-level tests for chat with a *generative* provider (ADR 0009): the
answer is the model's explanation, citations are limited to the evidence it
cited, history reaches the model, and an unavailable model fails honestly
(503, no orphan question, existing answers untouched). Real Postgres,
retrieval and citation persistence; only the model is scripted.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

import app.api.v1.system as system_api
from app.generation.llm_provider import (
    NO_EVIDENCE_ANSWER,
    LLMUnavailableError,
    LocalGroundedExtractiveProvider,
    OpenAICompatibleLLMProvider,
    get_llm_provider,
)
from app.generation.prompts import ChatTurn
from app.models.message import Message
from app.services.storage_provider import LocalStorage, get_storage_provider
from tests.conftest import csrf_headers
from tests.test_conversations import (
    _create_conversation,
    _create_workspace,
    _post_message,
    _push_user_message_earlier,
    _register,
)
from tests.test_llm_provider import FakeServer, _settings, fake_llm  # noqa: F401


class ScriptedProvider:
    """A generative provider whose behaviour the test controls."""

    model_name = "scripted"
    model_version = "test"
    is_generative = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.answer = "It prints the value. [2]"
        self.error: LLMUnavailableError | None = None

    def generate(
        self,
        *,
        system_prompt: str,
        context: str,
        query: str,
        history: Sequence[ChatTurn] = (),
    ) -> str:
        self.calls.append(
            {"system": system_prompt, "context": context, "query": query, "history": list(history)}
        )
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture(autouse=True)
def _isolated_storage(app: FastAPI, tmp_path: Path) -> Iterator[None]:
    app.dependency_overrides[get_storage_provider] = lambda: LocalStorage(root=str(tmp_path))
    yield
    del app.dependency_overrides[get_storage_provider]


@pytest.fixture
def provider(app: FastAPI) -> ScriptedProvider:
    scripted = ScriptedProvider()
    app.dependency_overrides[get_llm_provider] = lambda: scripted
    return scripted


@pytest.fixture(autouse=True)
def _reset_capability_cache() -> Iterator[None]:
    system_api._llm_cache = None
    yield
    system_api._llm_cache = None


def _upload_ready(client: TestClient, workspace_id: str, filename: str, text: str) -> None:
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


def _setup(client: TestClient) -> tuple[str, str]:
    _register(client)
    workspace = _create_workspace(client)
    _upload_ready(client, workspace["id"], "alpha_notes.txt", "Alpha program prints hello world.")
    _upload_ready(client, workspace["id"], "beta_notes.txt", "Beta program prints the value seven.")
    _upload_ready(client, workspace["id"], "gamma_notes.txt", "Gamma program prints the program.")
    conversation = _create_conversation(client, workspace["id"])
    return workspace["id"], conversation["id"]


# --- answer + citations -----------------------------------------------------------


def test_answer_is_the_models_explanation_and_citations_match_what_it_cited(
    client: TestClient, provider: ScriptedProvider
) -> None:
    workspace_id, conversation_id = _setup(client)

    response = _post_message(client, workspace_id, conversation_id, "What does the program print?")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content"] == "It prints the value. [2]"  # not "Based on the available documents"
    assert [c["rank"] for c in body["citations"]] == [2]
    # The citation points at the evidence block the model labelled [2].
    context = provider.calls[0]["context"]
    assert "[2] (Source:" in context


def test_when_the_model_cites_nothing_the_top_sources_are_still_attached(
    client: TestClient, provider: ScriptedProvider
) -> None:
    workspace_id, conversation_id = _setup(client)
    provider.answer = "A confident answer with no citation markers."

    question = "What does the program print?"
    body = _post_message(client, workspace_id, conversation_id, question).json()

    assert 1 <= len(body["citations"]) <= 3


def test_markers_the_model_invents_are_ignored(
    client: TestClient, provider: ScriptedProvider
) -> None:
    workspace_id, conversation_id = _setup(client)
    provider.answer = "See [1] and also [99]."

    question = "What does the program print?"
    body = _post_message(client, workspace_id, conversation_id, question).json()

    assert [c["rank"] for c in body["citations"]] == [1]


def test_evidence_sent_to_the_model_is_labelled_with_its_source_file(
    client: TestClient, provider: ScriptedProvider
) -> None:
    workspace_id, conversation_id = _setup(client)

    _post_message(client, workspace_id, conversation_id, "What does the program print?")

    context = provider.calls[0]["context"]
    assert "Source: beta_notes.txt" in context or "Source: alpha_notes.txt" in context


def test_follow_up_questions_receive_the_earlier_turns(
    client: TestClient, provider: ScriptedProvider
) -> None:
    workspace_id, conversation_id = _setup(client)
    _post_message(client, workspace_id, conversation_id, "What does the program print?")
    provider.answer = "Line by line... [1]"

    _post_message(client, workspace_id, conversation_id, "Explain that line by line")

    second = provider.calls[1]
    assert [(t.role, t.content) for t in second["history"]] == [
        ("user", "What does the program print?"),
        ("assistant", "It prints the value. [2]"),
    ]
    assert second["query"] == "Explain that line by line"
    assert "LINE-BY-LINE" in second["system"]


def test_a_workspace_without_documents_gets_the_fixed_answer_and_no_model_call(
    client: TestClient, provider: ScriptedProvider
) -> None:
    _register(client)
    workspace = _create_workspace(client)
    conversation = _create_conversation(client, workspace["id"])

    body = _post_message(client, workspace["id"], conversation["id"], "Explain program 1").json()

    assert body["content"] == NO_EVIDENCE_ANSWER
    assert body["citations"] == []
    assert provider.calls == []


# --- unavailable model ------------------------------------------------------------


def _message_count(db_session: DbSession, conversation_id: str) -> int:
    return db_session.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
    ) or 0


def test_unavailable_model_returns_503_and_leaves_no_orphan_question(
    client: TestClient, provider: ScriptedProvider, db_session: DbSession
) -> None:
    workspace_id, conversation_id = _setup(client)
    provider.error = LLMUnavailableError("unreachable", "The AI model server cannot be reached.")

    response = _post_message(client, workspace_id, conversation_id, "What does the program print?")

    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error["code"] == "llm_unavailable"
    assert "cannot be reached" in error["message"]
    assert _message_count(db_session, conversation_id) == 0
    url = f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages"
    assert client.get(url).json() == []


def test_regenerate_with_the_model_down_keeps_the_existing_answer(
    client: TestClient, provider: ScriptedProvider, db_session: DbSession
) -> None:
    workspace_id, conversation_id = _setup(client)
    original = _post_message(client, workspace_id, conversation_id, "What does the program print?")
    message_id = original.json()["id"]
    _push_user_message_earlier(db_session, conversation_id=conversation_id)
    provider.error = LLMUnavailableError("timeout", "The AI model took too long to answer.")

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"
        f"/messages/{message_id}/regenerate",
        headers=csrf_headers(client),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"
    listed = client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages"
    ).json()
    answers = [m["content"] for m in listed if m["role"] == "ASSISTANT"]
    assert answers == ["It prints the value. [2]"]


# --- extractive stays as it was -----------------------------------------------------


def test_extractive_provider_still_quotes_evidence_and_cites_every_block(
    client: TestClient, app: FastAPI
) -> None:
    app.dependency_overrides[get_llm_provider] = LocalGroundedExtractiveProvider
    workspace_id, conversation_id = _setup(client)

    question = "What does the program print?"
    body = _post_message(client, workspace_id, conversation_id, question).json()

    assert body["content"].startswith("Based on the available documents:")
    assert len(body["citations"]) == 3


# --- capabilities --------------------------------------------------------------------


def test_capabilities_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/system/capabilities").status_code == 401


def test_capabilities_reports_extractive_mode_honestly(client: TestClient, app: FastAPI) -> None:
    app.dependency_overrides[get_llm_provider] = LocalGroundedExtractiveProvider
    _register(client)

    llm = client.get("/api/v1/system/capabilities").json()["llm"]

    assert llm["status"] == "extractive" and llm["model"] is None
    assert "not explanations" in llm["message"]


def test_capabilities_reports_a_reachable_model_and_a_down_model(
    client: TestClient, app: FastAPI, fake_llm: FakeServer  # noqa: F811
) -> None:
    _register(client)
    provider = OpenAICompatibleLLMProvider(_settings(llm_base_url=fake_llm.url))
    app.dependency_overrides[get_llm_provider] = lambda: provider

    ready = client.get("/api/v1/system/capabilities").json()["llm"]
    assert (ready["provider"], ready["model"], ready["status"]) == (
        "openai_compatible",
        "test-model",
        "ready",
    )

    system_api._llm_cache = None
    fake_llm.models = (200, {"data": [{"id": "other"}]})
    missing = client.get("/api/v1/system/capabilities").json()["llm"]
    assert missing["status"] == "model_not_found"
    assert "127.0.0.1" not in str(missing)


def test_capabilities_stt_and_tts_blocks_are_present(client: TestClient, app: FastAPI) -> None:
    app.dependency_overrides[get_llm_provider] = LocalGroundedExtractiveProvider
    _register(client)
    body = client.get("/api/v1/system/capabilities").json()
    assert set(body) == {"llm", "stt", "tts"}
    assert body["stt"]["status"] == "ready"


