"""Context builder — assembles ranked retrieval candidates into a
prompt-ready evidence block, per docs/REQUIREMENTS.md "Generation":
"evidence ranking, duplicate removal, token-budget management."

Character counts, not tokens, bound the budget — matching this
project's own established convention (`app/ingestion/chunking.py`'s
`ChunkingConfig`), since no tokenizer is tied to a specific model choice
here either.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.retrieval.types import RetrievalCandidate

_DEFAULT_MAX_CONTEXT_CHARS = 4000


@dataclass(frozen=True)
class ContextBlock:
    """One piece of evidence included in the built context, tagged with
    the 1-based citation marker (`[1]`, `[2]`, ...) referencing it in
    `BuiltContext.text`."""

    marker: int
    candidate: RetrievalCandidate


@dataclass(frozen=True)
class BuiltContext:
    text: str
    blocks: list[ContextBlock]


def build_context(
    candidates: list[RetrievalCandidate], *, max_chars: int = _DEFAULT_MAX_CONTEXT_CHARS
) -> BuiltContext:
    """`candidates` must already be ranked best-first (e.g.
    `hybrid_search()`'s output) -- this function packs them in that
    order until `max_chars` is reached, never re-ranks.

    Duplicate removal: an exact-content duplicate (the same chunk
    appearing via more than one retrieval path, or two distinct chunks
    that happen to contain identical text) is included only once.

    Token-budget management: candidates are packed greedily until the
    next one would exceed `max_chars`, then packing stops -- except the
    very first eligible candidate is always included (truncated to fit)
    even if it alone exceeds the budget, so a single long, highly
    relevant chunk never results in an empty context when real evidence
    exists.
    """
    seen_content: set[str] = set()
    blocks: list[ContextBlock] = []
    parts: list[str] = []
    total_chars = 0
    marker = 1

    for candidate in candidates:
        content = candidate.content.strip()
        if not content or content in seen_content:
            continue

        block_text = f"[{marker}] {content}"
        if blocks and total_chars + len(block_text) > max_chars:
            break
        if not blocks and len(block_text) > max_chars:
            block_text = block_text[:max_chars]

        seen_content.add(content)
        blocks.append(ContextBlock(marker=marker, candidate=candidate))
        parts.append(block_text)
        total_chars += len(block_text)
        marker += 1

    return BuiltContext(text="\n\n".join(parts), blocks=blocks)


__all__ = ["BuiltContext", "ContextBlock", "build_context"]
