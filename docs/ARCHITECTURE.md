# Architecture

**Status:** PARTIALLY IMPLEMENTED — the Application Foundation (Issue #1)
implements the repository structure, backend skeleton, frontend shell, and
local Docker/CI infrastructure; Authentication & Workspaces (Issue #2) adds
the first real feature vertical slice (auth, sessions, workspace
CRUD/membership/roles) on top of it — see the module tree below. The
pipeline stages, provider abstractions, and remaining product functionality
(ingestion, retrieval, generation, voice, evaluation, etc.) remain
**PROPOSED / target** design; that is tracked as Issues #3–#8. See
[`PROJECT_STATE.md`](../PROJECT_STATE.md) for
real, current, per-component status.

## Architectural principles

1. **Modular monolith, not microservices.** One deployable FastAPI backend,
   internally organized into modules with clear boundaries. See
   [`docs/DECISIONS/0001-modular-monolith-over-microservices.md`](DECISIONS/0001-modular-monolith-over-microservices.md).
2. **PostgreSQL + pgvector is the only database/vector store** for the
   initial implementation. See
   [`docs/DECISIONS/0002-postgresql-pgvector-initial-vector-store.md`](DECISIONS/0002-postgresql-pgvector-initial-vector-store.md).
3. **No premature infrastructure.** Kubernetes, Kafka, Celery, Qdrant, and
   additional databases are explicitly excluded unless a documented,
   measured requirement justifies them via a new ADR. Rate limiting
   started this way too — in-process only — until horizontal scale-out
   became a real architectural requirement; that requirement is now
   documented in
   [ADR 0006](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md),
   which **designs** (but does not yet implement) Redis-backed distributed
   rate limiting and a deterministic abuse-detection layer, scoped
   narrowly to ephemeral rate-limit/abuse state — PostgreSQL remains the
   only durable datastore (ADR 0002). See
   [`docs/SECURITY.md`](SECURITY.md) §"Rate limiting approach" for current
   status.
4. **Provider abstraction** for swappable external capabilities:
   `EmbeddingProvider`, `Reranker`, `LLMProvider`, `SpeechToTextProvider`,
   `TextToSpeechProvider`, `StorageProvider`. No commercial provider is
   selected yet; this repository contains no such decision.
5. **Text RAG before voice.** Voice is a mode within chat, added after the
   text pipeline is proven, not a parallel system.
6. **Authentication is not purely stateless.** Short-lived, bearer-style
   access tokens are backed by server-tracked refresh/session records (in
   PostgreSQL, no separate session store) enabling per-device session
   listing and revocation. See
   [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md).
   Delivery to the browser is via `HttpOnly` cookies with CSRF protection,
   not an `Authorization` header — see
   [`docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md`](DECISIONS/0005-httponly-cookie-csrf-authentication.md).

## System flow

```
USER
 ├── TEXT
 └── VOICE → STT
          ↓
   Query Understanding
          ↓
   Query Processing / Rewrite
          ↓
   Dense Retrieval + BM25
          ↓
   Result Fusion
          ↓
     Reranker
          ↓
   Metadata Filtering
          ↓
    Top-K Evidence
          ↓
    Context Builder
          ↓
        LLM
          ↓
 Answer + Citations
 ├── TEXT
 └── VOICE → TTS
```

Supporting systems (cross-cutting, not pipeline stages): authentication,
authorization, multi-user workspaces, document management, collections,
conversations, search, evaluation, observability, audit logging, security
controls, testing, CI/CD, deployment.

## Target repository structure

```
advanced-rag-knowledge-assistant/
├── START_HERE.md
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── PROJECT_STATE.md
├── HANDOFF.md
├── SOLVING.md
├── CHANGELOG.md
├── README.md
├── .gitignore
├── .gitattributes
├── .env.example
├── docs/
│   ├── PROJECT_BRIEF.md
│   ├── REQUIREMENTS.md
│   ├── ARCHITECTURE.md
│   ├── API_CONTRACT.md
│   ├── DATA_MODEL.md
│   ├── SECURITY.md
│   ├── RAG_DESIGN.md
│   ├── EVALUATION.md
│   ├── DEPLOYMENT.md
│   └── DECISIONS/
├── backend/                     # IMPLEMENTED (Issues #1–#2)
│   ├── app/
│   │   ├── api/                 # HTTP routes per API_CONTRACT.md — health, auth, users, workspaces
│   │   ├── core/                # config, security (hashing/JWT), rate limiting, auth dependencies — implemented
│   │   ├── models/               # SQLAlchemy models per DATA_MODEL.md — users/sessions/workspaces/workspace_members implemented
│   │   ├── schemas/              # Pydantic request/response schemas — implemented (auth, user, workspace)
│   │   ├── repositories/         # data access layer — implemented (user/session/workspace/workspace_member)
│   │   ├── services/              # business logic orchestration — implemented (auth_service, workspace_service)
│   │   ├── ingestion/             # parse/clean/chunk/embed/index — PLANNED (Issue #3)
│   │   ├── retrieval/             # dense, BM25, fusion, rerank, filters — PLANNED (Issue #4)
│   │   ├── generation/            # context builder, LLM calls, citations — PLANNED (Issue #4)
│   │   ├── voice/                 # STT/TTS integration — PLANNED (Issue #6)
│   │   ├── evaluation/            # metrics, experiment runner — PLANNED (Issue #7)
│   │   └── observability/         # logging, tracing, metrics — implemented (structured logging, request IDs)
│   └── tests/                     # implemented (health/config/security/rate-limit/auth/workspaces coverage)
├── frontend/                     # IMPLEMENTED (Issues #1–#2)
│   ├── app/                       # Next.js routes — login/register/dashboard/settings/workspace implemented; documents/collections/chat/search/evaluations/analytics remain stubs (Issue #5)
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   ├── types/
│   └── tests/
├── eval/                          # PLANNED — does not exist yet (Issue #7)
│   ├── datasets/
│   ├── scripts/
│   └── results/
├── infra/                         # IMPLEMENTED (Issue #1 — local dev only; production packaging is Issue #8)
│   ├── docker/
│   └── compose/
├── .agents/
│   └── skills/                    # roster documented; individual skills PLANNED
└── .github/
    └── workflows/                 # IMPLEMENTED (Issue #1 — lint/typecheck/test/build/Docker-build CI)
```

Directories/modules marked IMPLEMENTED exist on disk and are verified working
(see `PROJECT_STATE.md`); those marked PLANNED are documented here for design
purposes only and their absence from the working tree is expected at this
phase.

## Backend module responsibilities (target)

| Module | Responsibility |
|---|---|
| `api/` | HTTP routing, request/response wiring, auth dependencies |
| `core/` | configuration, security primitives, shared dependencies |
| `models/` | SQLAlchemy ORM models |
| `schemas/` | Pydantic schemas for request/response validation |
| `repositories/` | data access — the only layer that talks to the DB directly |
| `services/` | business logic orchestrating repositories/providers |
| `ingestion/` | parsing, cleaning, chunking, embedding, indexing pipeline |
| `retrieval/` | dense retrieval, BM25, fusion, reranking, metadata filtering |
| `generation/` | context building, LLM invocation, citation generation |
| `voice/` | STT/TTS provider integration |
| `evaluation/` | retrieval/generation metrics, experiment tracking |
| `observability/` | structured logging, request IDs, latency/token metrics |

## Frontend UX direction

The application should **not** look like a generic admin dashboard. Design
direction: a ChatGPT-like conversational experience combined with
Notion-like knowledge organization, modern developer-tool clarity, and its
own visual identity appropriate for enterprise knowledge software.

Core UX story: **Upload knowledge → retrieve evidence → receive grounded
answer → inspect citations.**

### Target routes

```
/
/login
/register
/dashboard
/workspace
/documents
/documents/[id]
/collections
/collections/[id]
/chat/[id]
/search
/evaluations
/analytics
/settings
```

Requirements: responsive across desktop/tablet/mobile, accessible and
reusable components, explicit loading/empty/error/success/processing states,
and a command palette (`Ctrl+K`) with actions such as open document, new
chat, search, switch workspace, evaluations, settings.

## Provider abstractions

Interfaces to be defined in `backend/app/services/` (or a dedicated
`providers/` module, to be decided when implementation starts):

- `EmbeddingProvider`
- `Reranker`
- `LLMProvider`
- `SpeechToTextProvider`
- `TextToSpeechProvider`
- `StorageProvider`

No commercial vendor is selected for any of these yet. A selection becomes
real only once recorded as an ADR in `docs/DECISIONS/`. Development tooling
(e.g. Claude Code) is not the application's runtime LLM provider — the two
are unrelated.

## Related documents

- API surface: [`docs/API_CONTRACT.md`](API_CONTRACT.md)
- Data model: [`docs/DATA_MODEL.md`](DATA_MODEL.md)
- RAG pipeline detail: [`docs/RAG_DESIGN.md`](RAG_DESIGN.md)
- Security model: [`docs/SECURITY.md`](SECURITY.md)
- Deployment approach: [`docs/DEPLOYMENT.md`](DEPLOYMENT.md)
- Decisions: [`docs/DECISIONS/`](DECISIONS/)
