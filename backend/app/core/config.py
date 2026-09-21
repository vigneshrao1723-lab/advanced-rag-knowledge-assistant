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

    # Redis (ADR 0006) — optional: every `enforce_*_rate_limit` dependency
    # (app/core/rate_limit.py) attempts the Redis-backed distributed
    # limiter first when this is set, and falls back to the in-process
    # `FixedWindowRateLimiter` when it isn't (ADR 0006 §13 — see
    # `rate_limit.py`'s module docstring for the exact "unconfigured vs.
    # unreachable" distinction). No hardcoded connection target:
    # deployment-aware, like `database_url`.
    redis_url: str | None = None
    # Short, explicit timeouts (ADR 0006 §13: "on the order of tens of
    # milliseconds") so a degraded-but-not-down Redis cannot make a
    # request hang; a timeout is handled identically to a connection
    # failure by the caller (app/core/redis_client.py).
    redis_socket_timeout_seconds: float = 0.05
    redis_socket_connect_timeout_seconds: float = 0.05

    @model_validator(mode="after")
    def _validate_redis_timeouts(self) -> "Settings":
        if self.redis_socket_timeout_seconds <= 0:
            raise ValueError("redis_socket_timeout_seconds must be > 0.")
        if self.redis_socket_connect_timeout_seconds <= 0:
            raise ValueError("redis_socket_connect_timeout_seconds must be > 0.")
        return self

    # Trusted-proxy IP resolution (ADR 0006 §9a). Empty by default — the
    # safe, secure-by-default choice: `X-Forwarded-For`/`Forwarded` are
    # ignored unconditionally and the resolved client IP is always the
    # direct TCP peer, exactly matching today's `client_ip()` behavior,
    # until an operator explicitly configures the CIDR ranges of their own
    # reverse proxy/load balancer. Comma-separated CIDR ranges (IPv4/IPv6).
    trusted_proxy_cidrs: str = ""

    @property
    def trusted_proxy_cidrs_list(self) -> list[str]:
        return [cidr.strip() for cidr in self.trusted_proxy_cidrs.split(",") if cidr.strip()]

    # HMAC key for Redis email-derived identifiers (ADR 0006 §14/§22 —
    # resolved here as an implementation-time decision, recorded with its
    # rationale rather than left open): `None` (the default) reuses
    # `secret_key` rather than requiring a new secret to be provisioned
    # for a threat model (Redis-key dictionary-matching resistance) that
    # doesn't need key separation from JWT signing to be effective — both
    # are already server-only secrets never exposed to a client. Set this
    # explicitly only if a deployment specifically wants to rotate the
    # rate-limit HMAC key independently of `secret_key`.
    rate_limit_hash_key: str | None = None

    @property
    def rate_limit_hash_key_resolved(self) -> str:
        return self.rate_limit_hash_key or self.secret_key

    # Document storage (Issue #3, Slice 3.2 — `StorageProvider` abstraction,
    # app/services/storage_provider.py). "local" is the only implementation
    # today — a filesystem directory, for local dev/CI. `storage_bucket`
    # stays reserved for a future object-storage provider; never hardcode a
    # specific vendor, matching `email_provider`'s pattern.
    storage_provider: Literal["local"] = "local"
    storage_local_root: str = "./data/documents"
    storage_bucket: str | None = None

    # Document upload (Issue #3, Slice 3.3). Enforced while streaming the
    # upload (bounded reads), never by buffering the whole body first.
    max_upload_size_bytes: int = 50 * 1024 * 1024

    # Reserved for future issues — not consumed by any code path yet.
    llm_api_key: str | None = None
    embedding_api_key: str | None = None
    reranker_api_key: str | None = None
    stt_api_key: str | None = None
    tts_api_key: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
