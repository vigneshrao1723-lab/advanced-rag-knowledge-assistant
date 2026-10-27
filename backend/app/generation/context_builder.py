"""Context builder — assembles ranked retrieval candidates into a
prompt-ready evidence block, per docs/REQUIREMENTS.md "Generation":
"evidence ranking, duplicate removal, token-budget management."

Character counts, not tokens, bound the budget — matching this
project's own established convention (`app/ingestion/chunking.py`'s
`ChunkingConfig`), since no tokenizer is tied to a specific model choice
here either.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
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
    # Same blocks, each headed with its source (file, page, section) --
    # what a generative model reads. `text` (unlabelled) stays exactly as
    # before because the extractive provider's answer *is* `text`.
    labeled_text: str = ""


def _source_header(candidate: RetrievalCandidate, filename: str | None) -> str:
    parts = [filename or "document"]
    if candidate.page is not None:
        parts.append(f"page {candidate.page}")
    if candidate.section:
        parts.append(candidate.section)
    return "Source: " + ", ".join(parts)


def _labeled_block(block: ContextBlock, *, self_labels: Mapping[uuid.UUID, str]) -> str:
    header = _source_header(block.candidate, self_labels.get(block.candidate.document_id))
    return f"[{block.marker}] ({header})\n{block.candidate.content.strip()}"


def build_context(
    candidates: list[RetrievalCandidate],
    *,
    max_chars: int = _DEFAULT_MAX_CONTEXT_CHARS,
    source_labels: Mapping[uuid.UUID, str] | None = None,
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

    labels = source_labels or {}
    return BuiltContext(
        text="\n\n".join(parts),
        blocks=blocks,
        labeled_text="\n\n".join(_labeled_block(b, self_labels=labels) for b in blocks),
    )


__all__ = ["BuiltContext", "ContextBlock", "build_context"]
