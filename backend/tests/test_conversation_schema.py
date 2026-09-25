"""Schema-only tests for GitHub Issue #4 Slice 4.1 (`conversations` /
`messages` / `citations` / `retrieval_events`). Exercises the real
Postgres schema directly through the ORM, following this project's
established no-mock-datastore convention (docs/DECISIONS/0002;
`tests/conftest.py`'s `db_session`). Mirrors `tests/test_document_schema.py`'s
own structure and depth.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.db import engine
from app.models import (
    Citation,
    Conversation,
    Document,
    DocumentChunk,
    Message,
    MessageRole,
    RetrievalEvent,
    User,
    Workspace,
)


def _make_workspace(db_session: DbSession, name: str = "Test workspace") -> Workspace:
    workspace = Workspace(name=name)
    db_session.add(workspace)
    db_session.flush()
    return workspace


def _make_user(db_session: DbSession) -> User:
    user = User(email=f"user-{uuid.uuid4()}@example.com", password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.flush()
    return user


def _make_document(db_session: DbSession, *, workspace: Workspace) -> Document:
    document = Document(
        workspace_id=workspace.id,
        filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256=uuid.uuid4().hex,
        storage_key=f"{workspace.id}/{uuid.uuid4()}.pdf",
    )
    db_session.add(document)
    db_session.flush()
    return document


def _make_chunk(
    db_session: DbSession, *, workspace: Workspace, document: Document
) -> DocumentChunk:
    chunk = DocumentChunk(
        document_id=document.id, workspace_id=workspace.id, chunk_index=0, content="Chunk text."
    )
    db_session.add(chunk)
    db_session.flush()
    return chunk


def _make_conversation(db_session: DbSession, *, workspace: Workspace) -> Conversation:
    conversation = Conversation(workspace_id=workspace.id)
    db_session.add(conversation)
    db_session.flush()
    return conversation


def _make_message(
    db_session: DbSession, *, workspace: Workspace, conversation: Conversation, role: MessageRole
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        role=role,
        content="Hello.",
    )
    db_session.add(message)
    db_session.flush()
    return message


# --- table existence ---------------------------------------------------------


@pytest.mark.parametrize(
    "table_name", ["conversations", "messages", "citations", "retrieval_events"]
)
def test_table_exists(db_session: DbSession, table_name: str) -> None:
    inspector = sa.inspect(engine)
    assert table_name in inspector.get_table_names()


# --- conversations -----------------------------------------------------------


def test_conversation_references_workspace(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    conversation = _make_conversation(db_session, workspace=workspace)

    fetched = db_session.get(Conversation, conversation.id)
    assert fetched is not None
    assert fetched.workspace_id == workspace.id


def test_conversation_created_by_is_nullable(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    conversation = _make_conversation(db_session, workspace=workspace)

    fetched = db_session.get(Conversation, conversation.id)
    assert fetched is not None
    assert fetched.created_by is None


def test_deleting_user_sets_conversation_created_by_to_null(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    user = _make_user(db_session)
    conversation = Conversation(workspace_id=workspace.id, created_by=user.id)
    db_session.add(conversation)
    db_session.flush()

    db_session.delete(user)
    db_session.flush()
    db_session.expire_all()

    fetched = db_session.get(Conversation, conversation.id)
    assert fetched is not None
    assert fetched.created_by is None


def test_invalid_workspace_fk_is_rejected_for_conversations(db_session: DbSession) -> None:
    conversation = Conversation(workspace_id=uuid.uuid4())
    db_session.add(conversation)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_workspace_cascades_to_conversations(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    conversation = _make_conversation(db_session, workspace=workspace)
    conversation_id = conversation.id

    db_session.delete(workspace)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(Conversation, conversation_id) is None


# --- messages -----------------------------------------------------------------


def test_message_role_persists(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.USER
    )

    db_session.expire(message)
    fetched = db_session.get(Message, message.id)
    assert fetched is not None
    assert fetched.role == MessageRole.USER


def test_assistant_role_persists(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.ASSISTANT
    )

    db_session.expire(message)
    fetched = db_session.get(Message, message.id)
    assert fetched is not None
    assert fetched.role == MessageRole.ASSISTANT


def test_invalid_conversation_fk_is_rejected_for_messages(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    message = Message(
        conversation_id=uuid.uuid4(),
        workspace_id=workspace.id,
        role=MessageRole.USER,
        content="Orphan.",
    )
    db_session.add(message)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_conversation_cascades_to_messages(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.USER
    )
    message_id = message.id

    db_session.delete(conversation)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(Message, message_id) is None


# --- citations ------------------------------------------------------------


def test_citation_references_message_and_chunk(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    chunk = _make_chunk(db_session, workspace=workspace, document=document)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.ASSISTANT
    )

    citation = Citation(
        message_id=message.id,
        workspace_id=workspace.id,
        document_id=document.id,
        chunk_id=chunk.id,
        page=3,
        section="Introduction",
        rank=0,
    )
    db_session.add(citation)
    db_session.flush()

    fetched = db_session.get(Citation, citation.id)
    assert fetched is not None
    assert fetched.message_id == message.id
    assert fetched.chunk_id == chunk.id
    assert fetched.document_id == document.id
    assert fetched.page == 3
    assert fetched.section == "Introduction"
    assert fetched.rank == 0


def test_citation_page_and_section_are_nullable(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    chunk = _make_chunk(db_session, workspace=workspace, document=document)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.ASSISTANT
    )

    citation = Citation(
        message_id=message.id,
        workspace_id=workspace.id,
        document_id=document.id,
        chunk_id=chunk.id,
        rank=0,
    )
    db_session.add(citation)
    db_session.flush()

    fetched = db_session.get(Citation, citation.id)
    assert fetched is not None
    assert fetched.page is None
    assert fetched.section is None


def test_deleting_message_cascades_to_citations(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    chunk = _make_chunk(db_session, workspace=workspace, document=document)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.ASSISTANT
    )
    citation = Citation(
        message_id=message.id,
        workspace_id=workspace.id,
        document_id=document.id,
        chunk_id=chunk.id,
        rank=0,
    )
    db_session.add(citation)
    db_session.flush()
    citation_id = citation.id

    db_session.delete(message)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(Citation, citation_id) is None


def test_deleting_chunk_cascades_to_citations(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    chunk = _make_chunk(db_session, workspace=workspace, document=document)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.ASSISTANT
    )
    citation = Citation(
        message_id=message.id,
        workspace_id=workspace.id,
        document_id=document.id,
        chunk_id=chunk.id,
        rank=0,
    )
    db_session.add(citation)
    db_session.flush()
    citation_id = citation.id

    db_session.delete(chunk)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(Citation, citation_id) is None


def test_invalid_chunk_fk_is_rejected_for_citations(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    document = _make_document(db_session, workspace=workspace)
    conversation = _make_conversation(db_session, workspace=workspace)
    message = _make_message(
        db_session, workspace=workspace, conversation=conversation, role=MessageRole.ASSISTANT
    )

    citation = Citation(
        message_id=message.id,
        workspace_id=workspace.id,
        document_id=document.id,
        chunk_id=uuid.uuid4(),  # no such chunk
        rank=0,
    )
    db_session.add(citation)
    with pytest.raises(IntegrityError):
        db_session.flush()


# --- retrieval_events -------------------------------------------------------


def test_retrieval_event_stores_results_jsonb(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    results = [
        {"chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()), "score": 0.83, "rank": 0},
        {"chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()), "score": 0.61, "rank": 1},
    ]
    event = RetrievalEvent(
        workspace_id=workspace.id,
        query_text="What is the refund policy?",
        method="hybrid",
        results=results,
    )
    db_session.add(event)
    db_session.flush()

    db_session.expire(event)
    fetched = db_session.get(RetrievalEvent, event.id)
    assert fetched is not None
    assert fetched.results == results
    assert fetched.rewritten_query_text is None
    assert fetched.conversation_id is None
    assert fetched.message_id is None


def test_retrieval_event_preserves_original_query_alongside_rewritten(
    db_session: DbSession,
) -> None:
    workspace = _make_workspace(db_session)
    event = RetrievalEvent(
        workspace_id=workspace.id,
        query_text="it",
        rewritten_query_text="What is the refund policy for the product mentioned earlier?",
        method="hybrid",
        results=[],
    )
    db_session.add(event)
    db_session.flush()

    fetched = db_session.get(RetrievalEvent, event.id)
    assert fetched is not None
    assert fetched.query_text == "it"
    assert fetched.rewritten_query_text != fetched.query_text


def test_deleting_conversation_sets_retrieval_event_conversation_id_to_null(
    db_session: DbSession,
) -> None:
    workspace = _make_workspace(db_session)
    conversation = _make_conversation(db_session, workspace=workspace)
    event = RetrievalEvent(
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        query_text="q",
        method="dense",
        results=[],
    )
    db_session.add(event)
    db_session.flush()

    db_session.delete(conversation)
    db_session.flush()
    db_session.expire_all()

    fetched = db_session.get(RetrievalEvent, event.id)
    assert fetched is not None
    assert fetched.conversation_id is None


def test_deleting_workspace_cascades_to_retrieval_events(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    event = RetrievalEvent(workspace_id=workspace.id, query_text="q", method="dense", results=[])
    db_session.add(event)
    db_session.flush()
    event_id = event.id

    db_session.delete(workspace)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(RetrievalEvent, event_id) is None


def test_retrieval_event_timestamp_is_set_by_the_database(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    event = RetrievalEvent(workspace_id=workspace.id, query_text="q", method="dense", results=[])
    db_session.add(event)
    db_session.flush()

    fetched = db_session.get(RetrievalEvent, event.id)
    assert fetched is not None
    assert fetched.created_at is not None
