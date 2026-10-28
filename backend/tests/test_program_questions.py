"""End-to-end behaviour for questions about labelled items in a document
("Explain Program 2", "the first program", "explain that line by line"):
extraction keeps code indentation, the right program's complete span reaches
the model, absent items get a deterministic answer, and follow-ups keep their
focus. Real upload -> extraction -> chunking -> retrieval -> citations; only
the model is scripted. The PDF is synthetic (tests/pdf_fixtures.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.generation.llm_provider import NO_EVIDENCE_ANSWER, get_llm_provider
from app.generation.prompts import ChatTurn
from app.services.storage_provider import LocalStorage, get_storage_provider
from tests.conftest import csrf_headers
from tests.pdf_fixtures import Line, lab_manual_pdf, positioned_pdf
from tests.test_conversations import (
    _create_conversation,
    _create_workspace,
    _post_message,
    _register,
)


class ScriptedProvider:
    model_name = "scripted"
    model_version = "test"
    is_generative = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.answer = "It is explained step by step. [1]"

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


def _upload_pdf(client: TestClient, workspace_id: str, filename: str, content: bytes) -> str:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, "application/pdf")},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    document_id: str = response.json()["id"]
    processed = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/process",
        headers=csrf_headers(client),
    )
    assert processed.json()["status"] == "READY", processed.text
    return document_id


def _setup(client: TestClient, filename: str = "PC_Lab_Manual.pdf") -> tuple[str, str, str]:
    _register(client)
    workspace = _create_workspace(client)
    document_id = _upload_pdf(client, workspace["id"], filename, lab_manual_pdf())
    conversation = _create_conversation(client, workspace["id"])
    return workspace["id"], conversation["id"], document_id


def _ask(client: TestClient, ws: str, conv: str, question: str) -> dict[str, Any]:
    response = _post_message(client, ws, conv, question)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# --- extraction fidelity through the real pipeline --------------------------------


def test_code_indentation_survives_upload_extraction_and_chunking(client: TestClient) -> None:
    ws, _, document_id = _setup(client)

    chunks = client.get(f"/api/v1/workspaces/{ws}/documents/{document_id}/chunks").json()

    text = "\n".join(chunk["content"] for chunk in chunks)
    assert "    for (int i = 0; i < n - 1; i++) {" in text
    assert "            if (a[j] > a[j + 1]) {" in text
    assert "                int t = a[j];" in text
    assert "\n        local += i;\n" in text


def test_prose_only_pdfs_are_extracted_unchanged(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)
    prose: list[Line] = [
        (0, "Visitors must wear a badge at all times.", False),
        (0, "Badges are issued at the front desk between eight and five.", False),
        (0, "Contractors need a separate permit from facilities.", False),
    ]
    document_id = _upload_pdf(client, workspace["id"], "visitors.pdf", positioned_pdf([prose]))

    chunks = client.get(f"/api/v1/workspaces/{workspace['id']}/documents/{document_id}/chunks")

    extracted = [line for line in chunks.json()[0]["content"].splitlines() if line.strip()]
    assert extracted == [line[1] for line in prose]  # unchanged: default extraction, no layout mode


# --- resolving "Program N" -----------------------------------------------------------


def test_explain_program_sends_that_programs_complete_span_and_only_that(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)

    body = _ask(client, ws, conv, "Explain Program 2.")

    context = provider.calls[0]["context"]
    assert "Program 2: Sum of an array with MPI_Reduce" in context  # heading
    assert "MPI_Reduce(&local, &total, 1, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD);" in context  # code
    assert "Total = 36" in context  # output
    assert "Source: PC_Lab_Manual.pdf" in context
    assert "Hello from rank" not in context  # Program 1 is not mixed in
    assert "Bubble sort" not in context  # nor Program 3
    assert body["citations"], "the resolved span is cited"
    assert all(c["page"] == 2 for c in body["citations"])


def test_a_program_that_continues_on_the_next_page_is_reassembled_and_cut_at_the_next_heading(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)

    body = _ask(client, ws, conv, "explain program number 3")

    context = provider.calls[0]["context"]
    assert "void bubble_sort(int a[], int n) {" in context  # page 3
    assert "bubble_sort(a, 5);" in context  # page 4
    assert "1 2 4 5 8" in context  # its output, on page 4
    assert "Program 4: Factorial" not in context  # the next program is cut off
    assert "long fact(int n)" not in context
    assert {c["page"] for c in body["citations"]} == {3, 4}


def test_the_answer_shows_the_original_code_exactly_even_if_the_model_does_not(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)
    provider.answer = "It sorts the array with nested loops. [1]"

    body = _ask(client, ws, conv, "Explain Program 3")

    content = body["content"]
    assert "**Original code from the document**" in content
    assert "            if (a[j] > a[j + 1]) {\n                int t = a[j];" in content


def test_a_model_that_retypes_the_code_wrongly_is_corrected_to_the_original(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)
    provider.answer = (
        "It prints greetings.\n```c\nint main() {\n  int rank;\n  printf(\"Hi\");\n}\n```"
    )

    body = _ask(client, ws, conv, "Explain Program 1")

    assert "printf(\"Hi\")" in body["content"]  # <50% of its lines exist: left as written
    assert "**Original code from the document**" in body["content"]
    assert '    printf("Hello from rank %d of %d\\n", rank, size);' in body["content"]


def test_the_first_program_means_the_first_in_the_document(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)

    _ask(client, ws, conv, "Explain the first program in my PC lab manual PDF")

    assert "Program 1: Hello from every process" in provider.calls[0]["context"]


def test_the_last_program_is_found(client: TestClient, provider: ScriptedProvider) -> None:
    ws, conv, _ = _setup(client)

    _ask(client, ws, conv, "explain the last program")

    assert "Program 4: Factorial using recursion" in provider.calls[0]["context"]
    assert "return n * fact(n - 1);" in provider.calls[0]["context"]


def test_an_absent_program_gets_a_deterministic_answer_that_lists_what_exists(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)

    body = _ask(client, ws, conv, "Explain Program 9 from my PC lab PDF")

    assert provider.calls == []  # no model call, nothing to hallucinate from
    assert body["citations"] == []
    assert "couldn't find Program 9" in body["content"]
    assert "PC_Lab_Manual.pdf" in body["content"]
    assert "Programs 1, 2, 3, 4" in body["content"]


def test_a_program_number_in_two_documents_asks_which_one(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)
    other: list[Line] = [
        (0, "Program 1: Linked list traversal", False),
        (0, "Aim: walk a singly linked list.", False),
        (0, "struct node *p = head;", True),
        (0, "while (p != NULL) {", True),
        (1, "p = p->next;", True),
        (0, "}", True),
    ]
    _upload_pdf(client, ws, "Data_Structures_Lab.pdf", positioned_pdf([other]))

    ambiguous = _ask(client, ws, conv, "Explain program 1")
    assert provider.calls == []
    assert "more than one document" in ambiguous["content"]
    assert "PC_Lab_Manual.pdf" in ambiguous["content"]
    assert "Data_Structures_Lab.pdf" in ambiguous["content"]

    resolved = _ask(client, ws, conv, "Explain program 1 from the data structures lab pdf")
    assert "Linked list traversal" in provider.calls[0]["context"]
    assert "Hello from rank" not in provider.calls[0]["context"]
    assert resolved["citations"]


def test_two_documents_matching_the_name_equally_are_not_guessed(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client, filename="Lab Manual 2023.pdf")
    _upload_pdf(client, ws, "Lab Manual 2024.pdf", positioned_pdf([[(0, "Program 1: x", False)]]))

    body = _ask(client, ws, conv, "explain the lab manual")

    assert provider.calls == []
    assert "Which document do you mean?" in body["content"]


# --- follow-ups ---------------------------------------------------------------------------


def test_a_follow_up_keeps_the_programs_evidence_and_history(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)
    _ask(client, ws, conv, "Explain Program 2")

    _ask(client, ws, conv, "explain that line by line")

    second = provider.calls[1]
    assert "MPI_Reduce(&local, &total" in second["context"]
    assert "Program 3" not in second["context"]
    assert [t.role for t in second["history"]] == ["user", "assistant"]
    assert "LINE-BY-LINE" in second["system"]


def test_a_follow_up_after_a_missing_program_still_needs_a_real_one(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)
    _ask(client, ws, conv, "Explain Program 9")

    body = _ask(client, ws, conv, "ok explain program 2 then")

    assert "Program 2: Sum of an array" in provider.calls[0]["context"]
    assert body["citations"]


def test_follow_ups_skip_a_question_that_found_nothing_and_return_to_the_last_real_topic(
    client: TestClient, provider: ScriptedProvider
) -> None:
    # Regression (found by running the owner's checklist): after "Explain
    # Program 1" found nothing, every follow-up repeated "I couldn't find
    # Program 1" because it was taken as the focus.
    ws, conv, _ = _setup(client)
    _ask(client, ws, conv, "Explain Program 2")
    _ask(client, ws, conv, "Explain Program 9")  # not in the manual
    assert len(provider.calls) == 1

    body = _ask(client, ws, conv, "Explain it as a beginner")

    assert "couldn't find" not in body["content"]
    assert "MPI_Reduce(&local, &total" in provider.calls[1]["context"]  # Program 2 again
    assert "Program 9" not in provider.calls[1]["context"]
    assert "BEGINNER" in provider.calls[1]["system"]


def test_a_follow_up_with_nothing_to_refer_to_asks_what_is_meant(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)
    _ask(client, ws, conv, "Explain Program 9")  # nothing resolved in this conversation

    body = _ask(client, ws, conv, "Explain it as a beginner")

    assert provider.calls == []
    assert "not sure which part you mean" in body["content"]
    assert body["citations"] == []
    # ...and naming something fixes it straight away.
    _ask(client, ws, conv, "Explain Program 2 as a beginner")
    assert "Program 2: Sum of an array" in provider.calls[0]["context"]


def test_a_follow_up_style_question_in_a_new_conversation_is_not_blocked(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)

    body = _ask(client, ws, conv, "Explain this as a beginner")  # no history at all

    assert "not sure which part you mean" not in body["content"]


# --- missing evidence -------------------------------------------------------------------------


def test_an_off_topic_question_gets_the_honest_answer_without_a_model_call(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)

    body = _ask(client, ws, conv, "What is the capital of Atlantis?")

    assert body["content"] == NO_EVIDENCE_ANSWER
    assert body["citations"] == []
    assert provider.calls == []


def test_a_normal_topical_question_still_retrieves_by_similarity(
    client: TestClient, provider: ScriptedProvider
) -> None:
    ws, conv, _ = _setup(client)

    _ask(client, ws, conv, "How does bubble sort work?")

    assert "bubble_sort" in provider.calls[0]["context"]


def test_workspace_isolation_holds_for_program_lookup(
    client_factory: Any, provider: ScriptedProvider
) -> None:
    owner = client_factory()
    ws, _, _ = _setup(owner)
    outsider = client_factory()
    _register(outsider)
    other_ws = _create_workspace(outsider, name="Other")
    other_conv = _create_conversation(outsider, other_ws["id"])

    body = _ask(outsider, other_ws["id"], other_conv["id"], "Explain Program 2")

    assert body["content"] == NO_EVIDENCE_ANSWER  # nothing of the owner's leaks
    assert provider.calls == []
    assert uuid.UUID(ws) != uuid.UUID(other_ws["id"])
