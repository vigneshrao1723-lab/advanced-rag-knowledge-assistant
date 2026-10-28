"""LLM generation provider abstraction (docs/ARCHITECTURE.md "Provider
abstractions"; ADR 0009 for the real-model provider).

Two implementations: `LocalGroundedExtractiveProvider` (deterministic,
quotes evidence -- kept for tests/CI/offline evaluation) and
`OpenAICompatibleLLMProvider` (a real language model behind any
OpenAI-style `/chat/completions` server). The rest of this docstring
describes the extractive provider's original contract.

Mirrors `EmbeddingProvider`/`Reranker`'s shape exactly: a `Protocol`, one
concrete implementation today, and a settings-driven factory.
`LocalGroundedExtractiveProvider` is deterministic and offline (no
external API/key) — no commercial vendor selected yet, so the whole
pipeline stays testable/demoable without a paid LLM API. It does not
paraphrase or synthesize; it returns the ranked evidence itself, quoted
and citation-marked, which is grounded *by construction* (there is
nothing in its output that didn't come from the provided evidence) and
immune to prompt injection *by construction* (it never interprets
`context` as anything other than inert text to quote — see this
package's own `__init__.py` docstring for the full reasoning). A real
hosted provider is a genuinely different, more capable component
(fluent synthesis, real reasoning) — swapping one in is additive
(implement `LLMProvider`, branch in `get_llm_provider()`), not a
rewrite, but it is also the one place in this pipeline that would need
its own, careful prompt-injection-resistant implementation (structurally
separating the system/instruction channel from the evidence channel,
per docs/SECURITY.md), not inherited for free from this one.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.generation.prompts import (
    ChatTurn,
    build_user_message,
    history_to_messages,
)

logger = logging.getLogger("app.generation")

# Public (not `_`-prefixed) and exported: `app.evaluation.metrics`'s
# `is_extractive_answer_grounded()` needs the exact same string to
# recognize this provider's own no-evidence shape without duplicating
# the literal.
NO_EVIDENCE_ANSWER = (
    "I don't have enough information in the available documents to answer this question."
)


class LLMUnavailableError(Exception):
    """The configured answer-generation model cannot be used right now.

    `code` is a stable machine-readable reason, `message` is safe to show
    to the end user: it never contains the API key, the request body or the
    provider's raw response (docs/SECURITY.md "Errors and information
    disclosure")."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LLMProvider(Protocol):
    model_name: str
    model_version: str
    # True for a real language model that writes its own explanation and
    # cites `[n]` markers; False for the extractive provider, whose answer
    # *is* the evidence and cites every block it quotes.
    is_generative: bool

    def generate(
        self,
        *,
        system_prompt: str,
        context: str,
        query: str,
        history: Sequence[ChatTurn] = (),
    ) -> str:
        """`system_prompt`, `context` (untrusted, retrieved content --
        already formatted with `[n]` citation markers by
        `app.generation.context_builder.build_context()`), and `query`
        are three structurally separate arguments, never concatenated
        into one string by this interface -- see the module docstring
        for why that separation is a real security property, not just a
        style choice. `history` is earlier turns of the same
        conversation, oldest first."""
        ...


class LocalGroundedExtractiveProvider:
    """Deterministic, offline. Returns the provided evidence verbatim,
    still carrying its `[n]` citation markers, framed as an answer --
    never inventing content beyond what `context` already contains. An
    empty `context` (no evidence retrieved) returns a fixed, honest
    "I don't have enough information" answer rather than fabricating one.

    NOT an intelligent assistant: it cannot explain anything. Production
    configuration should use `OpenAICompatibleLLMProvider`.
    """

    model_name = "local-extractive"
    model_version = "v1"
    is_generative = False

    def generate(
        self,
        *,
        system_prompt: str,
        context: str,
        query: str,
        history: Sequence[ChatTurn] = (),
    ) -> str:
        if not context.strip():
            return NO_EVIDENCE_ANSWER
        return f"Based on the available documents:\n\n{context}"


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _clean_model_output(text: str) -> str:
    """Reasoning models (Qwen3, DeepSeek-R1, ...) may emit a <think> block;
    it is not part of the answer."""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _safe_excerpt(response: httpx.Response, limit: int = 160) -> str:
    """A short, single-line piece of the provider's error body for the
    *server log* only (never shown to the user, never includes headers)."""
    return " ".join(response.text.split())[:limit]


class OpenAICompatibleLLMProvider:
    """A real language model behind an OpenAI-style chat-completions API.

    Works unchanged with a local Ollama (`http://ollama:11434/v1`),
    llama.cpp's `llama-server`, LM Studio, vLLM, or a hosted provider that
    exposes the same API. Nothing is sent anywhere except `base_url`.
    """

    is_generative = True
    model_version = "openai-compatible"

    def __init__(self, settings: Settings) -> None:
        self._base_url = (settings.llm_base_url or "").rstrip("/")
        self._model = settings.llm_model or ""
        self._api_key = settings.llm_api_key
        self._timeout = settings.llm_timeout_seconds
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_output_tokens
        self._history_turns = settings.llm_history_turns
        self.model_name = self._model or "unconfigured"

    # -- configuration ---------------------------------------------------
    def _require_configured(self) -> None:
        if not self._base_url or not self._model:
            raise LLMUnavailableError(
                "not_configured",
                "No AI model is configured. Set LLM_BASE_URL and LLM_MODEL (for the bundled "
                "local setup, start Ollama and pull a model - see docs/AI_SETUP.md).",
            )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    # -- generation ------------------------------------------------------
    def generate(
        self,
        *,
        system_prompt: str,
        context: str,
        query: str,
        history: Sequence[ChatTurn] = (),
    ) -> str:
        self._require_configured()
        messages = [
            {"role": "system", "content": system_prompt},
            *history_to_messages(history, self._history_turns),
            {"role": "user", "content": build_user_message(context=context, query=query)},
        ]
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=httpx.Timeout(self._timeout, connect=5.0),
            )
        except httpx.TimeoutException as exc:
            logger.warning("llm_timeout", extra={"model": self._model, "error": type(exc).__name__})
            raise LLMUnavailableError(
                "timeout",
                "The AI model took too long to answer. A larger model on a CPU can be slow; "
                "try again, or use a smaller model (docs/AI_SETUP.md).",
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "llm_unreachable", extra={"model": self._model, "error": type(exc).__name__}
            )
            raise LLMUnavailableError(
                "unreachable",
                "The AI model server cannot be reached. Start it (for the bundled setup: "
                "`docker compose --profile llm up -d ollama`) or check LLM_BASE_URL - see "
                "docs/AI_SETUP.md.",
            ) from exc

        answer = self._parse_response(response)
        logger.info(
            "llm_generation",
            extra={
                "model": self._model,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "prompt_chars": sum(len(m["content"]) for m in messages),
                "answer_chars": len(answer),
            },
        )
        return answer

    def _parse_response(self, response: httpx.Response) -> str:
        status = response.status_code
        if status in (401, 403):
            raise LLMUnavailableError(
                "unauthorized",
                "The AI provider rejected the credentials. Check LLM_API_KEY.",
            )
        if status == 404:
            logger.warning("llm_not_found", extra={"detail": _safe_excerpt(response)})
            raise LLMUnavailableError(
                "model_not_found",
                f"The AI model '{self._model}' was not found on the model server. For Ollama run "
                f"`ollama pull {self._model}`; otherwise check LLM_MODEL and LLM_BASE_URL.",
            )
        if status == 429:
            raise LLMUnavailableError(
                "rate_limited", "The AI provider is rate-limiting requests. Try again shortly."
            )
        if status >= 400:
            logger.warning(
                "llm_provider_error", extra={"status": status, "detail": _safe_excerpt(response)}
            )
            raise LLMUnavailableError(
                "provider_error", f"The AI model server returned an error (HTTP {status})."
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError(
                "bad_response", "The AI model server returned an unexpected response."
            ) from exc
        if not isinstance(content, str) or not _clean_model_output(content):
            raise LLMUnavailableError("bad_response", "The AI model returned an empty answer.")
        return _clean_model_output(content)

    # -- status (capabilities endpoint) ------------------------------------
    def check_availability(self) -> tuple[str, str]:
        """(`status`, `message`) with status `ready` or one of the
        `LLMUnavailableError` codes. Cheap: lists models, never generates."""
        try:
            self._require_configured()
        except LLMUnavailableError as exc:
            return exc.code, exc.message
        try:
            response = httpx.get(
                f"{self._base_url}/models", headers=self._headers(), timeout=httpx.Timeout(4.0)
            )
        except httpx.HTTPError:
            return "unreachable", "The AI model server cannot be reached."
        if response.status_code in (401, 403):
            return "unauthorized", "The AI provider rejected the credentials."
        if response.status_code >= 400:
            # Some servers do not implement /models; do not claim failure.
            return "ready", "The model server is reachable (model list unavailable)."
        try:
            ids = {item.get("id") for item in response.json().get("data", [])}
        except (ValueError, AttributeError):
            return "ready", "The model server is reachable."
        if ids and self._model not in ids and f"{self._model}:latest" not in ids:
            return (
                "model_not_found",
                f"The model '{self._model}' is not installed on the model server.",
            )
        return "ready", "The AI model is ready."


def get_llm_provider() -> LLMProvider:
    """Settings-driven (`LLM_PROVIDER`). Never switches provider on its
    own: if the configured model is down, calls fail with a clear
    `LLMUnavailableError` instead of quietly returning raw excerpts."""
    settings = get_settings()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(settings)
    return LocalGroundedExtractiveProvider()


__all__ = [
    "ChatTurn",
    "LLMProvider",
    "LLMUnavailableError",
    "LocalGroundedExtractiveProvider",
    "NO_EVIDENCE_ANSWER",
    "OpenAICompatibleLLMProvider",
    "get_llm_provider",
]
