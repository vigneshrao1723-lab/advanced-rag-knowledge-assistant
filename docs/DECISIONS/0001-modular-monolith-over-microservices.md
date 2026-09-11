# 0001. Modular monolith over microservices

**Status:** Accepted
**Date:** 2026-09-11

## Context

This project has a multi-stage pipeline (ingestion, retrieval, generation,
voice, evaluation) that could plausibly be decomposed into separate services
communicating over a network. The project is starting from zero, with no
existing scale, traffic, or team-topology pressure that would justify that
decomposition today.

## Decision

The initial implementation is a **modular monolith**: a single deployable
FastAPI backend, internally organized into clearly bounded modules (`api`,
`core`, `models`, `schemas`, `repositories`, `services`, `ingestion`,
`retrieval`, `generation`, `voice`, `evaluation`, `observability` — see
[`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)). Modules communicate through
in-process interfaces, not network calls. A single Next.js frontend consumes
the backend's HTTP API.

Microservices, Kubernetes, and message-queue-based decomposition (e.g.,
Kafka) are explicitly **not** part of the initial architecture.

## Alternatives considered

- **Microservices from day one** — rejected. Without a measured scaling or
  team-isolation need, this multiplies operational complexity (service
  discovery, network failure modes, distributed tracing, deployment
  coordination) for no corresponding benefit, and would slow down the first
  working version considerably.
- **Serverless functions per pipeline stage** — rejected for the same
  reason, plus added complexity around shared state (embeddings, chunk
  metadata) that a monolith gets for free via a shared database session.

## Consequences

- Faster initial development: one codebase, one deployment, one test suite
  to run end-to-end.
- Module boundaries (`ingestion/`, `retrieval/`, `generation/`, etc.) must
  be kept clean in code even though they're not physically separated — this
  is a discipline requirement, not enforced by network boundaries.
- If a genuine scaling bottleneck or isolation requirement is measured later
  (not hypothesized), splitting out a specific module into its own service
  is possible without a full rewrite, precisely because the module
  boundaries are already clean. That split would require a new ADR
  superseding or amending this one, backed by the measured evidence.
