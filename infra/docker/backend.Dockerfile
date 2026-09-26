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

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
