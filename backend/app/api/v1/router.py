"""Aggregates every `/api/v1/*` router.

Feature routers (auth, workspaces, documents, ...) are added here as their
issues are implemented — only `health` exists as of Issue #1.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
