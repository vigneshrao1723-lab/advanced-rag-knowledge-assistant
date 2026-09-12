from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.db import check_database_connection


def test_liveness_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reflects_real_database_connectivity(client: TestClient) -> None:
    """No mocking: assert the endpoint reports whatever the database
    connection actually does, whichever way that goes in this environment.
    """
    db_is_actually_reachable = check_database_connection()

    response = client.get("/api/v1/health/ready")
    body = response.json()

    if db_is_actually_reachable:
        assert response.status_code == 200
        assert body == {"status": "ready", "checks": {"database": "ok"}}
    else:
        assert response.status_code == 503
        assert body == {"status": "not_ready", "checks": {"database": "unreachable"}}


def test_request_id_is_generated_and_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_request_id_from_client_is_propagated(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["X-Request-ID"] == "test-request-id"


def test_unknown_route_returns_consistent_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert "request_id" in body["error"]
    # Never leaks internals such as file paths or tracebacks.
    assert "Traceback" not in response.text
