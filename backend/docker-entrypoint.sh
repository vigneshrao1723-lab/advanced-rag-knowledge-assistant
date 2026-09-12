#!/bin/sh
# Local-development convenience only: applies pending Alembic migrations
# before starting the API, so `docker compose up` alone yields a working,
# ready backend without a separate manual migration step.
set -eu

uv run alembic upgrade head

exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
