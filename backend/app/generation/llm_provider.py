"""LLM generation provider abstraction (docs/ARCHITECTURE.md "Provider
abstractions").

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

from typing import Protocol

# Public (not `_`-prefixed) and exported: `app.evaluation.metrics`'s
# `is_extractive_answer_grounded()` needs the exact same string to
# recognize this provider's own no-evidence shape without duplicating
# the literal.
NO_EVIDENCE_ANSWER = (
    "I don't have enough information in the available documents to answer this question."
)


class LLMProvider(Protocol):
    model_name: str
    model_version: str

    def generate(self, *, system_prompt: str, context: str, query: str) -> str:
        """`system_prompt`, `context` (untrusted, retrieved content —
        already formatted with `[n]` citation markers by
        `app.generation.context_builder.build_context()`), and `query`
        are three structurally separate arguments, never concatenated
        into one string by this interface — see the module docstring
        for why that separation is a real security property, not just a
        style choice."""
        ...


class LocalGroundedExtractiveProvider:
    """Deterministic, offline. Returns the provided evidence verbatim,
    still carrying its `[n]` citation markers, framed as an answer —
    never inventing content beyond what `context` already contains. An
    empty `context` (no evidence retrieved) returns a fixed, honest
    "I don't have enough information" answer rather than fabricating
    one.
    """

    model_name = "local-extractive"
    model_version = "v1"

    def generate(self, *, system_prompt: str, context: str, query: str) -> str:
        if not context.strip():
            return NO_EVIDENCE_ANSWER
        return f"Based on the available documents:\n\n{context}"


def get_llm_provider() -> LLMProvider:
    """`LocalGroundedExtractiveProvider` is the only implementation
    today — this gains a branch on a future `Settings.llm_provider`
    value (matching `get_embedding_provider()`'s pattern) when a second,
    real implementation is actually added, not before."""
    return LocalGroundedExtractiveProvider()


__all__ = [
    "LLMProvider",
    "LocalGroundedExtractiveProvider",
    "NO_EVIDENCE_ANSWER",
    "get_llm_provider",
]
