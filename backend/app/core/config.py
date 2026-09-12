"""Application configuration.

Settings are loaded from environment variables (and a local `.env` file in
development). Variable names match `.env.example` at the repository root.

Only `DATABASE_URL` is required to start the application in this issue's
scope (Application Foundation) — it's the only setting any running code path
actually consumes yet. The remaining variables from `.env.example` are
declared here (typed, optional) so config loading has a single, honest
source of truth as later issues start consuming them; they are not given
fake defaults, and code must not silently proceed as if they were set once
it actually depends on them.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Required: the only datastore for the initial implementation (ADR 0002).
    database_url: str

    # The frontend runs on a different origin (port) than the backend even in
    # local development, so the browser enforces CORS on every request the
    # frontend's fetch calls make. Comma-separated list of allowed origins.
    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    # Reserved for future issues — not consumed by any code path yet.
    secret_key: str | None = None
    llm_api_key: str | None = None
    embedding_api_key: str | None = None
    reranker_api_key: str | None = None
    storage_provider: str | None = None
    storage_bucket: str | None = None
    stt_api_key: str | None = None
    tts_api_key: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
