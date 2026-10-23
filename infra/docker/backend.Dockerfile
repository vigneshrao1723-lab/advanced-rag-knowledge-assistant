# Local-development backend image. Production packaging is Issue #8's
# concern (docs/DEPLOYMENT.md "Target CI/CD" / "Target deployment
# environment") — this Dockerfile only needs to run the app for
# `docker compose up` and CI's build-check.

FROM python:3.13-slim

# `espeak-ng`: the offline TTS backend `app/voice/tts_provider.py`
# (Issue #6) shells out to as a subprocess — no model download, no
# network call, no paid API.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project

COPY . .
RUN uv sync
RUN chmod +x docker-entrypoint.sh

# Pre-create the local document-storage root (app/core/config.py's
# storage_local_root, app/services/storage_provider.py) so it exists,
# owned by appuser, before infra/compose/docker-compose.yml mounts a
# named volume over it -- Docker initializes a fresh named volume from
# whatever already exists at that path in the image, ownership
# included; without this, a brand-new volume is created owned by root,
# which the non-root appuser below can't write into.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data/documents \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
