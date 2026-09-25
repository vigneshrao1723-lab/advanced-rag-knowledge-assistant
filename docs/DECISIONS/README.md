# Architecture Decision Records (ADRs)

This directory records significant, hard-to-reverse architectural decisions
for the Advanced RAG Knowledge Intelligence Assistant — and, just as
importantly, the reasoning and alternatives behind them, so a future
contributor doesn't have to reconstruct "why did we do it this way?" from
scratch.

## When to write an ADR

Write one when a decision:

- Introduces, removes, or replaces a piece of infrastructure (a database, a
  queue, a cache, a new external service).
- Deviates from the modular-monolith architecture in
  [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).
- Selects a commercial provider for one of the provider abstractions
  (`EmbeddingProvider`, `Reranker`, `LLMProvider`, `SpeechToTextProvider`,
  `TextToSpeechProvider`, `StorageProvider`).
- Would be expensive or risky to reverse later.

Don't write one for routine implementation choices that are easily changed
(a function name, an internal helper's structure) — that's normal code
review, not an ADR.

## Process

1. Copy [`template.md`](template.md) to `NNNN-short-title.md` (next sequence
   number, kebab-case title).
2. Fill it in: context, decision, alternatives considered, consequences.
3. Get it reviewed (per `AGENTS.md` §6 — this is part of the normal
   PR/review workflow, not a separate approval process).
4. Once accepted, the ADR is treated as binding per `AGENTS.md` — code and
   other docs (especially `docs/ARCHITECTURE.md`) should not silently drift
   from it. Changing the decision means writing a new ADR that supersedes
   the old one, not editing history.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-modular-monolith-over-microservices.md) | Modular monolith over microservices | Accepted | 2026-09-11 |
| [0002](0002-postgresql-pgvector-initial-vector-store.md) | PostgreSQL + pgvector as the initial vector store | Accepted | 2026-09-11 |
| [0003](0003-authentication-session-architecture.md) | Authentication: short-lived access tokens with server-tracked sessions | Accepted | 2026-09-11 |
| [0004](0004-password-hashing-argon2id.md) | Password hashing: Argon2id via `argon2-cffi` | Accepted | 2026-09-12 |
| [0005](0005-httponly-cookie-csrf-authentication.md) | Browser authentication: HttpOnly cookies with double-submit CSRF | Accepted | 2026-09-14 |
| [0006](0006-redis-distributed-rate-limiting-abuse-protection.md) | Redis-backed distributed rate limiting + deterministic abuse protection | Accepted | 2026-09-14 |
| [0007](0007-local-providers-for-embedding-reranking-generation.md) | Local, deterministic providers for embedding, reranking, and generation (no commercial vendor yet) | Accepted | 2026-09-25 |

## Relationship to other memory types

An ADR is one of several distinct memory types this repository uses (see
`AGENTS.md` §5): **RULE** (persistent constraint), **SKILL** (reusable
procedure), **MCP** (external tool/data integration), **MEMORY**
(persistent project state), **ADR** (this — an architecture decision),
**HANDOFF** (immediate continuation state), **SOLVING** (hard-won technical
knowledge). Don't conflate them — an ADR records a decision, not a task
status or a how-to.
