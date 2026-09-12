"""Liveness and readiness checks.

Per docs/API_CONTRACT.md, `/api/v1/health` is one of the two namespaces
(alongside `/api/v1/auth`) that never requires a session.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.db import check_database_connection

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: str


class ReadinessChecks(BaseModel):
    database: str


class ReadinessResponse(BaseModel):
    status: str
    checks: ReadinessChecks


@router.get("", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """The process is up. Does not touch the database."""
    return LivenessResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def readiness(response: Response) -> ReadinessResponse:
    """The process is up *and* its dependencies are reachable.

    Performs a real database round-trip — never asserts readiness it hasn't
    checked.
    """
    database_ok = check_database_connection()
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if database_ok else "not_ready",
        checks=ReadinessChecks(database="ok" if database_ok else "unreachable"),
    )
