# 0009. Real answer generation through an OpenAI-compatible provider

**Status:** Accepted
**Date:** 2026-10-27

## Context

Owner acceptance testing of `86a385a` found the product cannot explain
anything: asking about a program in an uploaded PDF returned the extracted
text. The cause is architectural, not a bug: `get_llm_provider()` always
returned `LocalGroundedExtractiveProvider`, which by design only quotes the
retrieved passages ([ADR 0007](0007-local-providers-for-embedding-reranking-generation.md)).
No language model existed in the system, and `llm_api_key` was a reserved,
unused setting.

Constraints from the owner: hybrid architecture (documents and retrieval stay
local; AI and speech providers are configurable), a free local configuration
must work, hosted providers only by explicit configuration, no mandatory paid
service, nothing sent to a third party silently. Hardware on the development
machine: 7.6 GiB RAM in WSL2, NVIDIA RTX 3050 (4 GB VRAM), no model installed.

`CLAUDE.md` §4 requires care when changing how retrieved (untrusted) content
reaches the LLM; this ADR records that boundary.

## Decision

1. Add `OpenAICompatibleLLMProvider`, selected with `LLM_PROVIDER=openai_compatible`,
   speaking the de-facto standard `/chat/completions` API with `LLM_BASE_URL`,
   `LLM_MODEL`, optional `LLM_API_KEY`. One adapter covers a local Ollama
   (the documented, free default), llama.cpp, LM Studio, vLLM and hosted
   providers. No vendor is hardcoded.
2. Keep `LocalGroundedExtractiveProvider` (`LLM_PROVIDER=extractive`, the
   code default) for tests, CI and offline evaluation. It is **not** presented
   as an assistant: when it is active the UI says so.
3. **No silent fallback.** If the configured model is unreachable,
   misconfigured, slow or returns garbage, the request fails with
   `503 llm_unavailable` and an actionable message. The user's question is
   withdrawn (no orphan message), an existing answer is never overwritten, and
   the UI restores the typed text. Raw excerpts are never substituted.
4. With no usable evidence, the fixed "not enough information" answer is
   returned **without calling the model**.
5. **Prompt boundary.** The system message holds only our rules plus style hints
   derived from the *user's own question*. Evidence is untrusted: it is placed
   only in the user message inside an explicit `<<<EVIDENCE … EVIDENCE>>>` block,
   labelled by source, with delimiter look-alikes in document text neutralised;
   the rules tell the model that evidence may contain instructions and must
   never be obeyed. The model has no tools, network access or secrets, and its
   output is rendered as inert text (a Markdown renderer with no HTML
   pass-through). Residual risk: a persuasive injection can still make the
   model answer badly; it cannot cause an action.
6. For a generative answer, citations are limited to the evidence blocks the
   model cited (`[n]`, original numbering preserved), falling back to the top
   three if it cited none.
7. Conversation history (last `LLM_HISTORY_TURNS` turns, truncated) is sent so
   follow-ups work.
8. `GET /api/v1/system/capabilities` reports model readiness so the UI can warn
   before the first question. It never exposes URLs, keys or raw provider errors.
9. Secrets: the API key is sent only as a bearer header, never logged, never
   included in error messages, and never in `.env.example`.

## Alternatives considered

- **Bundle `llama-cpp-python` in the backend image** — one fewer service, but a
  large native build in the image, no GPU on the default build, and it ties the
  web process to model memory. A separate Ollama service is the standard,
  swappable, GPU-friendly arrangement.
- **A vendor SDK (OpenAI/Anthropic/Gemini)** — would hard-wire a paid hosted
  dependency, which the owner ruled out. The OpenAI-compatible API reaches
  hosted providers anyway, by configuration.
- **Make the extractive provider "smarter"** — it cannot explain code; any
  template would be pretending.
- **Silent fallback to excerpts when the model is down** — rejected: it is
  precisely the failure the owner reported, hidden.

## Consequences

- Real explanations need a model: the free path is `docs/AI_SETUP.md`
  (≈1.9 GB download for `qwen2.5:3b-instruct`). A 3B model is useful for
  explaining short programs but is weaker than hosted models; a larger local
  model (`qwen2.5:7b-instruct`, 4.7 GB) is slow on this GPU.
- Answer quality, hallucination rate and injection resistance now depend on the
  chosen model and must be evaluated per model; the extractive-era "grounded by
  construction" metric no longer applies to generative answers.
- Latency rises from milliseconds to seconds (CPU) or a few seconds (GPU).
  Requests run synchronously, as before; a streaming endpoint is a possible
  follow-up.
- Using a hosted provider sends the question, recent history and retrieved
  passages to that provider. That is an explicit configuration choice and is
  documented in `docs/AI_SETUP.md`.
- Revisit if a real embedding model is added (the relevance and retrieval
  choices in `docs/RAG_DESIGN.md` assume the local hashing embedder).
