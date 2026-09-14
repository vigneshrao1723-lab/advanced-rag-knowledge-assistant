# Advanced RAG Knowledge Intelligence Assistant

> **Status: Application Foundation (Issue #1) and Authentication &
> Workspaces (Issue #2) implemented.** A FastAPI backend, Next.js frontend,
> PostgreSQL + pgvector, Docker Compose, and CI exist, and users can now
> register, log in, manage sessions/devices, and create/manage workspaces
> with role-based membership — with no ingestion, retrieval, generation, or
> voice yet; that is real, tracked future work under Issues #3–#8. See
> [`PROJECT_STATE.md`](PROJECT_STATE.md) for the authoritative, up-to-date
> snapshot of what is implemented vs. planned.

A multi-user, voice-enabled RAG (Retrieval-Augmented Generation) knowledge
platform, **designed** with production-oriented engineering practices (see
[`AGENTS.md`](AGENTS.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md))
— this is a description of the target design, not a claim that the current
repository is production-ready. Once built, it will let users upload
private knowledge, retrieve information through hybrid semantic + lexical
search, and receive citation-grounded answers through text or voice — with
full visibility into the retrieval pipeline behind every answer.

## What this project is

The core user flow, once built, will be:

```
USER
 ├── TEXT
 └── VOICE → STT
          ↓
   Query Understanding → Query Rewrite
          ↓
   Dense Retrieval + BM25 → Fusion → Reranker → Metadata Filtering
          ↓
   Top-K Evidence → Context Builder → LLM
          ↓
   Answer + Citations
 ├── TEXT
 └── VOICE → TTS
```

Supporting systems include authentication, multi-user workspaces, document
management, an ingestion pipeline, collections, conversations, search,
retrieval/generation evaluation, observability, audit logging, and security
controls. Full detail lives in [`docs/RAG_DESIGN.md`](docs/RAG_DESIGN.md) and
[`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

## Target architecture (Application Foundation implemented; product logic not yet implemented)

- **Backend:** Python, FastAPI, PostgreSQL + pgvector, SQLAlchemy, Pydantic —
  a **modular monolith** (explicitly not microservices).
- **Frontend:** Next.js, TypeScript, React, Tailwind CSS, shadcn/ui, Lucide,
  Recharts, Zod.
- **Dev tooling:** Git, GitHub, Docker Desktop + WSL2, Claude Code, VS Code.

Full rationale — including what is deliberately excluded (Kubernetes, Kafka,
Redis, Celery, Qdrant, multi-database setups) and why — is documented in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DECISIONS/`](docs/DECISIONS/).

## Development status

| Area | Status |
|---|---|
| Project documentation & architecture | IMPLEMENTED |
| Repository scaffold (`.gitignore`, `.env.example`, remote) | IMPLEMENTED |
| Backend application (Issue #1 — foundation only, no feature logic) | IMPLEMENTED |
| Frontend application (Issue #1 — shell + stub routes only) | IMPLEMENTED |
| Database schema | PARTIALLY IMPLEMENTED — `users`/`sessions`/`workspaces`/`workspace_members` exist (Issue #2); document/RAG entities don't yet |
| Authentication / workspaces | IMPLEMENTED — Issue #2 |
| Ingestion / retrieval / generation pipeline | PLANNED — Issues #3–#4 |
| Voice (STT/TTS) | PLANNED — Issue #6 |
| Evaluation harness | PLANNED — Issue #7 |
| CI/CD | IMPLEMENTED — Issue #1 |
| Deployment (local Docker Compose) | IMPLEMENTED — Issue #1; production deployment is Issue #8 |

This table names Issue #1's foundation as implemented; it is not a claim
that any product feature (auth, ingestion, retrieval, generation, voice) is
built. See [`PROJECT_STATE.md`](PROJECT_STATE.md) for the authoritative,
current status of every component.

## Getting started (for contributors and AI agents)

Read [`START_HERE.md`](START_HERE.md) first — it defines the mandatory reading
order and repository rules. A runnable stack exists (see
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the local Docker Compose
setup): you can register, log in, and create/manage workspaces, but there
is no knowledge-base functionality (upload, chat, search) yet. Full
end-user setup/run instructions will replace this section as the remaining
product functionality (Issues #3–#8) lands.

## Documentation map

| File | Purpose |
|---|---|
| [`START_HERE.md`](START_HERE.md) | Onboarding for any human or AI agent joining this repo |
| [`AGENTS.md`](AGENTS.md) | Engineering constitution: standards, rules, workflow |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code operating instructions for this repo |
| [`GEMINI.md`](GEMINI.md) | Gemini reviewer/research-assistant instructions |
| [`PROJECT_STATE.md`](PROJECT_STATE.md) | Current, authoritative project snapshot |
| [`HANDOFF.md`](HANDOFF.md) | Short-term continuation state between sessions |
| [`SOLVING.md`](SOLVING.md) | Hard-problem log (root causes, fixes, lessons) |
| [`CHANGELOG.md`](CHANGELOG.md) | Chronological record of real changes |
| [`docs/`](docs/) | Architecture, requirements, security, RAG design, evaluation, deployment |
| [`docs/DECISIONS/`](docs/DECISIONS/) | Binding architecture decision records (ADRs) |
| [`.agents/skills/`](.agents/skills/README.md) | Roster of reusable agent procedures (skills) and the memory-type taxonomy |

## Roadmap

Real GitHub issues `#1`–`#8` track the work (`#1` Application Foundation and
`#2` Authentication & Workspaces — implemented; `#3` Knowledge Ingestion;
`#4` Hybrid RAG Pipeline; `#5` Product Experience; `#6` Voice; `#7`
Evaluation, Security & Observability; `#8` CI/CD, Deployment &
Finalization). See
[`PROJECT_STATE.md`](PROJECT_STATE.md#immediate-priorities) for current
status and the exact next step.

## License

Not yet decided.
