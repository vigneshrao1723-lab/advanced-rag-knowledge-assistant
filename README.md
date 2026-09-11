# Advanced RAG Knowledge Intelligence Assistant

> **Status: Documentation / Initialization phase.** No application code exists
> yet. This repository currently contains project documentation, architecture
> decisions, and planning artifacts only. See [`PROJECT_STATE.md`](PROJECT_STATE.md)
> for the authoritative, up-to-date snapshot of what is implemented vs. planned.

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

## Target architecture (not yet implemented)

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
| Backend application | PLANNED — not started |
| Frontend application | PLANNED — not started |
| Database schema | PLANNED — not started |
| Ingestion / retrieval / generation pipeline | PLANNED — not started |
| Voice (STT/TTS) | PLANNED — not started |
| Evaluation harness | PLANNED — not started |
| CI/CD | PLANNED — not started |
| Deployment | PLANNED — not started |

No functionality described above should be read as already built. See
[`PROJECT_STATE.md`](PROJECT_STATE.md) for status of individual components as
work begins.

## Getting started (for contributors and AI agents)

Read [`START_HERE.md`](START_HERE.md) first — it defines the mandatory reading
order and repository rules. There is no runnable application yet, so there is
no setup/run procedure to document here. This section will be replaced with
real setup instructions once the backend and frontend scaffolds exist.

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

See the issue plan in [`AGENTS.md`](AGENTS.md#github--collaboration-model) and
[`PROJECT_STATE.md`](PROJECT_STATE.md#immediate-priorities) for the intended
sequencing of work, starting with architecture documentation and the frontend
design system before any backend implementation begins.

## License

Not yet decided.
