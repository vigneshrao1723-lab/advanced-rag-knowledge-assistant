"""Schema-only tests for GitHub Issue #7 (`evaluation_runs` /
`evaluation_results`). Exercises the real Postgres schema directly
through the ORM, following this project's established no-mock-datastore
convention (docs/DECISIONS/0002; `tests/conftest.py`'s `db_session`).
Mirrors `tests/test_conversation_schema.py`'s own structure and depth.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.db import engine
from app.models import EvaluationResult, EvaluationRun, Workspace


def _make_workspace(db_session: DbSession, name: str = "Test workspace") -> Workspace:
    workspace = Workspace(name=name)
    db_session.add(workspace)
    db_session.flush()
    return workspace


def _make_run(db_session: DbSession, *, workspace: Workspace | None) -> EvaluationRun:
    run = EvaluationRun(
        workspace_id=workspace.id if workspace else None,
        embedding_model="local-hashing",
        chunking_strategy="structure_aware",
        retrieval_method="hybrid_reranked",
        top_k=3,
        llm_provider="local-grounded-extractive",
        document_count=6,
        query_count=7,
    )
    db_session.add(run)
    db_session.flush()
    return run


# --- table existence ---------------------------------------------------------


@pytest.mark.parametrize("table_name", ["evaluation_runs", "evaluation_results"])
def test_table_exists(db_session: DbSession, table_name: str) -> None:
    inspector = sa.inspect(engine)
    assert table_name in inspector.get_table_names()


# --- evaluation_runs -----------------------------------------------------


def test_evaluation_run_references_workspace(db_session: DbSession) -> None:
    workspace = _make_workspace(db_session)
    run = _make_run(db_session, workspace=workspace)

    fetched = db_session.get(EvaluationRun, run.id)
    assert fetched is not None
    assert fetched.workspace_id == workspace.id


def test_evaluation_run_workspace_id_is_nullable(db_session: DbSession) -> None:
    run = _make_run(db_session, workspace=None)

    fetched = db_session.get(EvaluationRun, run.id)
    assert fetched is not None
    assert fetched.workspace_id is None


def test_deleting_workspace_sets_evaluation_run_workspace_id_to_null(
    db_session: DbSession,
) -> None:
    # Deliberately SET NULL, not CASCADE -- an evaluation run must
    # outlive the (often throwaway) workspace it was computed against,
    # see app/models/evaluation_run.py's docstring.
    workspace = _make_workspace(db_session)
    run = _make_run(db_session, workspace=workspace)

    db_session.delete(workspace)
    db_session.flush()
    db_session.expire_all()

    fetched = db_session.get(EvaluationRun, run.id)
    assert fetched is not None
    assert fetched.workspace_id is None


def test_invalid_workspace_fk_is_rejected_for_evaluation_runs(db_session: DbSession) -> None:
    run = EvaluationRun(
        workspace_id=uuid.uuid4(),
        embedding_model="local-hashing",
        chunking_strategy="structure_aware",
        retrieval_method="dense",
        top_k=3,
        llm_provider="local-grounded-extractive",
        document_count=1,
        query_count=1,
    )
    db_session.add(run)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_evaluation_run_optional_fields_are_nullable(db_session: DbSession) -> None:
    run = _make_run(db_session, workspace=None)

    fetched = db_session.get(EvaluationRun, run.id)
    assert fetched is not None
    assert fetched.chunk_size is None
    assert fetched.chunk_overlap is None
    assert fetched.reranker is None


def test_evaluation_run_timestamp_is_set_by_the_database(db_session: DbSession) -> None:
    run = _make_run(db_session, workspace=None)

    fetched = db_session.get(EvaluationRun, run.id)
    assert fetched is not None
    assert fetched.created_at is not None


# --- evaluation_results ----------------------------------------------------


def test_evaluation_result_references_run(db_session: DbSession) -> None:
    run = _make_run(db_session, workspace=None)
    result = EvaluationResult(evaluation_run_id=run.id, metric_name="recall@3", metric_value=1.0)
    db_session.add(result)
    db_session.flush()

    fetched = db_session.get(EvaluationResult, result.id)
    assert fetched is not None
    assert fetched.evaluation_run_id == run.id
    assert fetched.metric_name == "recall@3"
    assert fetched.metric_value == 1.0


def test_invalid_run_fk_is_rejected_for_evaluation_results(db_session: DbSession) -> None:
    result = EvaluationResult(
        evaluation_run_id=uuid.uuid4(), metric_name="recall@3", metric_value=1.0
    )
    db_session.add(result)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_evaluation_run_cascades_to_evaluation_results(db_session: DbSession) -> None:
    run = _make_run(db_session, workspace=None)
    result = EvaluationResult(evaluation_run_id=run.id, metric_name="mrr", metric_value=0.5)
    db_session.add(result)
    db_session.flush()
    result_id = result.id

    db_session.delete(run)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(EvaluationResult, result_id) is None


def test_evaluation_result_timestamp_is_set_by_the_database(db_session: DbSession) -> None:
    run = _make_run(db_session, workspace=None)
    result = EvaluationResult(evaluation_run_id=run.id, metric_name="mrr", metric_value=0.5)
    db_session.add(result)
    db_session.flush()

    fetched = db_session.get(EvaluationResult, result.id)
    assert fetched is not None
    assert fetched.created_at is not None
