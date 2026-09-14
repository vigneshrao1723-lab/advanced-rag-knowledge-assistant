"""Email delivery abstraction (docs/ARCHITECTURE.md "Provider abstractions").

`auth_service`/`password_reset_service` depend on `EmailProvider`, never on
a concrete vendor. `SMTPEmailProvider` is vendor-neutral: any real provider
that offers an SMTP endpoint (or an SMTP relay in front of an HTTP API)
works without code changes — only `.env` configuration changes. Local
development points it at Mailpit (`infra/compose/docker-compose.yml`),
which captures mail locally instead of sending it anywhere, with a web UI
and REST API to inspect it (used by Playwright to read the reset-password
email in E2E tests — see docs/DEPLOYMENT.md).

`ConsoleEmailProvider` is a last-resort fallback only, for an environment
with no SMTP host configured at all (e.g. a bare `pytest` run) — it prints
to stdout, deliberately bypassing the structured JSON application logger,
so a console-provider "send" is never mistaken for or mixed into real
application logs.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger("app.email")


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, text_body: str) -> None: ...


class ConsoleEmailProvider:
    def send(self, *, to: str, subject: str, text_body: str) -> None:
        print(
            "--- EMAIL (console provider — not actually sent) ---\n"
            f"To: {to}\nSubject: {subject}\n\n{text_body}\n"
            "--- END EMAIL ---"
        )


class SMTPEmailProvider:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        use_tls: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._use_tls = use_tls

    def send(self, *, to: str, subject: str, text_body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_email
        message["To"] = to
        message.set_content(text_body)

        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(message)

        # Never log the recipient's full address or the email body (which
        # may contain a reset link/token) — only enough to confirm a send
        # happened, per docs/SECURITY.md.
        logger.info("email_sent", extra={"to_domain": to.rsplit("@", 1)[-1]})


def get_email_provider() -> EmailProvider:
    settings = get_settings()
    if settings.email_provider == "console":
        return ConsoleEmailProvider()

    if not settings.smtp_host:
        raise RuntimeError(
            "EMAIL_PROVIDER=smtp requires SMTP_HOST to be configured."
        )
    return SMTPEmailProvider(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_email=settings.smtp_from_email,
        use_tls=settings.smtp_use_tls,
    )
