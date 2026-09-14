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

from pydantic import model_validator
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

    # Required as of Issue #2: signs/verifies access tokens (app/core/security.py).
    # No fake default — config loading fails loudly if it's missing, per
    # docs/SECURITY.md "Secret management".
    secret_key: str

    # Access tokens are short-lived and validated without a DB round-trip
    # (ADR 0003); refresh tokens are long-lived but revocable server-side.
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Cookie configuration (ADR 0005) — deployment-aware, never assumed.
    # Do NOT hardcode these for "frontend and backend share a site": some
    # deployments genuinely need a cross-site cookie (frontend and backend
    # on different registrable domains), which requires `SameSite=None` +
    # `Secure` + explicit CORS. The default here (`lax`, no explicit
    # domain) is the secure choice for same-site deployments (including
    # local dev) and must be deliberately overridden, never silently
    # weakened, for a cross-site deployment.
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # None = host-only cookie (safest default: exact host only). Set to a
    # parent domain (e.g. ".example.com") only for deployments that
    # genuinely share a parent domain across frontend/backend subdomains.
    cookie_domain: str | None = None
    # None = auto-derive (True in production, or whenever SameSite=None
    # since browsers reject `SameSite=None` without `Secure`). Set
    # explicitly to force Secure in a non-"production"-labeled environment
    # that still serves over HTTPS (e.g. staging).
    cookie_secure: bool | None = None

    @model_validator(mode="after")
    def _validate_cookie_security(self) -> "Settings":
        if self.cookie_samesite == "none" and self.cookie_secure is False:
            raise ValueError(
                "cookie_secure cannot be false when cookie_samesite is 'none' — "
                "browsers reject SameSite=None cookies without Secure."
            )
        return self

    @model_validator(mode="after")
    def _validate_email_provider_for_production(self) -> "Settings":
        # "console" prints password-reset tokens (and any future
        # security-relevant email) to process stdout instead of sending
        # them — in virtually every real deployment (Docker, Kubernetes,
        # systemd, a PaaS) stdout is captured into log aggregation, which
        # would put a raw reset token directly into logs. Fail loudly at
        # startup rather than let a forgotten EMAIL_PROVIDER=smtp silently
        # degrade production to this fallback.
        if self.is_production and self.email_provider == "console":
            raise ValueError(
                "email_provider cannot be 'console' in production — this would print "
                "raw password-reset tokens to stdout, where they are typically captured "
                "by log aggregation. Set EMAIL_PROVIDER=smtp with SMTP_HOST configured."
            )
        return self

    @property
    def cookie_secure_resolved(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production or self.cookie_samesite == "none"

    # Password recovery / email (Issue #2 extended scope).
    # Used to build the reset-password link emailed to the user — the
    # *frontend's* origin, not the backend's.
    frontend_url: str = "http://localhost:3000"
    password_reset_token_expire_minutes: int = 60

    # "console" prints the email to stdout instead of sending it — a
    # last-resort fallback, not a real send. Local dev uses "smtp" pointed
    # at Mailpit (infra/compose/docker-compose.yml); production points it
    # at a real SMTP provider/relay. Never hardcode a specific vendor.
    email_provider: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "noreply@example.com"
    smtp_use_tls: bool = False

    # Reserved for future issues — not consumed by any code path yet.
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
