"""FastAPI application entrypoint.

Assembles the app: structured logging, request-ID propagation, centralized
error handling, and the `/api/v1` router. No feature logic (auth, ingestion,
retrieval, generation, voice) lives here — see `docs/ARCHITECTURE.md` for
where each module's responsibility lives as it's implemented.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.observability.access_log import AccessLogMiddleware
from app.observability.logging import configure_logging
from app.observability.request_id import RequestIDMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Advanced RAG Knowledge Assistant",
        version="0.1.0",
    )

    # Order matters: request ID must be assigned before anything logs.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(api_v1_router)

    return app


app = create_app()
