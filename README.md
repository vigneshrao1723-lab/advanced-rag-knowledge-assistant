# Advanced RAG Knowledge Intelligence Assistant

> **Status: Issues #1–#7 implemented and merged.** A multi-user,
> voice-enabled RAG platform: authentication and workspaces, document
> upload and ingestion, hybrid (dense + lexical) retrieval with
> reranking, grounded generation with citations, a real product
> frontend (documents, chat), voice input/output as a mode within chat,
> and an evaluation/observability/security-hardening layer are all
> implemented, tested, and running end-to-end against real Postgres,
> Redis, and the real UI — no paid external API required. Issue #8
> (this document, plus final deployment/CI review) is in progress. See
> [`PROJECT_STATE.md`](PROJECT_STATE.md) for the authoritative,
> up-to-date snapshot of every component.

A multi-user, voice-enabled RAG (Retrieval-Augmented Generation) knowledge
platform, built with production-oriented engineering practices (see
[`AGENTS.md`](AGENTS.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)).
Users upload private documents into a workspace, ask questions through
text or voice, and receive citation-grounded answers — with full
visibility into which document, page, and section each answer's claims
actually came from.

## What this project does, today

```
USER
 ├── TEXT
 └── VOICE → STT (PocketSphinx, offline)
          ↓
   Hybrid Retrieval: Dense (pgvector) + Lexical (Postgres FTS) → RRF Fusion → Reranker
          ↓
   Top-K Evidence → Context Builder → LLM (grounded, citation-marked)
          ↓
   Answer + Citations
 ├── TEXT
 └── VOICE → TTS (espeak-ng, offline)
```

Every stage above is real and running — not a design sketch. Workspace
isolation is enforced at the SQL query level on every retrieval/
document/conversation lookup; retrieved document content is always
treated as untrusted data, never as instructions (tested against a
12-payload prompt-injection corpus); every embedding/reranking/
generation/speech provider is a local, deterministic, offline
implementation — no paid API key is required to run the full stack.
See [`docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md`](docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md)
and [`docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md`](docs/DECISIONS/0008-local-speech-to-text-and-text-to-speech-providers.md)
for why, and their honestly-documented accuracy trade-offs.

Supporting systems, also implemented: multi-user workspaces with
role-based membership, an ingestion pipeline (PDF/DOCX/TXT/Markdown/CSV
→ extract → clean → chunk → embed → index), audit logging, Redis-backed
distributed rate limiting with a deterministic abuse-detection layer,
and a real, persisted retrieval/generation evaluation harness comparing
multiple retrieval configurations and chunking strategies. Full design
detail lives in [`docs/RAG_DESIGN.md`](docs/RAG_DESIGN.md) and
[`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

## Quickstart

Requires Docker Desktop (or an equivalent Docker + Compose setup).

```bash
git clone <this-repository>
cd advanced-rag-knowledge-assistant
cp .env.example .env   # see "Environment variables" below before editing
docker compose -f infra/compose/docker-compose.yml up --build
```

This starts PostgreSQL (with `pgvector`), Redis, Mailpit (local SMTP
capture for password-reset emails), the backend (`http://localhost:8000`),
and the frontend (`http://localhost:3000`). The backend entrypoint
applies pending database migrations automatically on startup.

Then, in a browser at `http://localhost:3000`:

1. **Register** an account and **log in**.
2. **Create a workspace** (or accept the one auto-selected after
   creation) from the Workspace page.
3. **Upload a document** (PDF, DOCX, TXT, Markdown, or CSV, up to 50 MiB)
   from the Documents page. Processing runs synchronously — the page
   polls and shows the status (`UPLOADED` → ... → `READY`, or `FAILED`
   with a reason) every 3 seconds.
4. Once the document is `READY`, open **Chat**, start a new
   conversation, and **ask a question** about it. The answer appears
   with numbered citations pointing back to the source document(s).
5. Try **voice**: click "Ask by voice," speak your question, click
   again to stop and transcribe — the transcript, answer, and citations
   appear exactly as they would for a typed question. Click "Play
   answer" under any assistant message to hear it read back.

`.env.example` documents every environment variable this project reads;
`docker-compose.yml` supplies safe local-dev-only defaults for the ones
required to start (e.g. a placeholder `SECRET_KEY`) — override them via
a real `.env` file for anything beyond a throwaway local stack.

## Environment variables

The full, commented list lives in [`.env.example`](.env.example) — copy
it to `.env` and fill in real values for anything beyond local dev. The
only one you're likely to need to change immediately:

- `SECRET_KEY` — signs/verifies auth tokens. Generate a real value with
  `openssl rand -hex 32` for anything beyond a throwaway local stack;
  never commit a real value. `docker-compose.yml`'s default is a
  local-dev-only placeholder.

Everything else (email delivery, Redis, cookie/CORS behavior for a
cross-site deployment, trusted-proxy IP resolution) has a safe default
for local development and is documented inline in `.env.example` with
the reasoning behind each default. No LLM/embedding/reranker/STT/TTS
API key is required — every provider ships a local, offline
implementation (see "What this project does, today" above).

## Running tests

```bash
# Backend (from the backend/ directory, against a real reachable Postgres):
cd backend && uv run pytest -q            # unit + integration tests
uv run ruff check . && uv run mypy .      # lint + type check

# Frontend (from the frontend/ directory):
cd frontend && npm run test -- --run      # vitest unit/component tests
npm run lint && npx tsc --noEmit          # lint + type check
npm run build                             # production build check

# Browser end-to-end (from the frontend/ directory, against a running stack):
npx playwright install chromium           # once
npm run test:e2e
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for what each CI job runs
and how to reproduce it locally, including the `espeak-ng` system
dependency the voice tests need (already installed in the backend
Docker image; install it yourself — e.g. `apt-get install espeak-ng` —
to run those specific tests directly on a Linux host).

## Running the evaluation harness

```bash
cd backend && uv run python ../eval/scripts/run_retrieval_evaluation.py
```

Ingests a small, deterministic fixture document set through the real
pipeline, then compares 4 retrieval methods (dense-only, lexical-only,
hybrid, hybrid+reranked) across 2 chunking strategies, computing
Recall@K/Precision@K/MRR/nDCG/Hit Rate and citation-groundedness checks.
Writes `eval/results/retrieval_evaluation.json` and persists the run
configuration + metrics to the real `evaluation_runs`/
`evaluation_results` database tables (safely re-runnable — uses its own
throwaway workspace, cleaned up automatically). See
[`docs/EVALUATION.md`](docs/EVALUATION.md) for the real, committed
numbers this has actually produced, and the project's standing rule
against ever fabricating an evaluation number.

## How citations, retrieval, and security fit together

- **Citations** are generated from the exact evidence the retrieval
  pipeline surfaced for a given answer — never invented after the fact.
  Each citation records the source document, page/section, and its rank
  in the answer.
- **Workspace isolation** is enforced at the SQL query level on every
  document/chunk/conversation/message/citation lookup (`WHERE
  workspace_id = ...` in the query itself, never a post-hoc filter) —
  see [`docs/SECURITY.md`](docs/SECURITY.md) §"Retrieval workspace
  isolation".
- **Retrieved document content is untrusted data, never instructions.**
  A malicious or compromised document containing prompt-injection text
  ("ignore previous instructions," a fake system message, a request to
  reveal secrets, ...) is only ever quoted as evidence, never obeyed —
  tested against a 12-payload adversarial corpus at both the provider
  and full-HTTP-pipeline level. See
  [`docs/SECURITY.md`](docs/SECURITY.md) §"Prompt injection defense".
- **Voice input receives no elevated trust** — a transcribed question is
  validated and processed through the exact same path a typed one is,
  never a separate or more-trusted pipeline.

Full security model, audit logging, and rate-limiting design:
[`docs/SECURITY.md`](docs/SECURITY.md).

## Architecture

- **Backend:** Python, FastAPI, PostgreSQL + pgvector, SQLAlchemy,
  Pydantic, Redis — a **modular monolith** (explicitly not
  microservices; see [ADR 0001](docs/DECISIONS/0001-modular-monolith-over-microservices.md)).
- **Frontend:** Next.js, TypeScript, React, Tailwind CSS, shadcn/ui, Zod.
- **Dev tooling:** Git, GitHub Actions CI, Docker Compose.

Full rationale — including what is deliberately excluded (Kubernetes,
Kafka, Celery, Qdrant, multiple databases) and why — is documented in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/DECISIONS/`](docs/DECISIONS/).

## Development status

| Area | Status |
|---|---|
| Application foundation, CI/CD, Docker Compose | IMPLEMENTED (Issue #1) |
| Authentication, sessions, workspaces & RBAC | IMPLEMENTED (Issue #2) |
| Redis distributed rate limiting + abuse detection | IMPLEMENTED (ADR 0006) |
| Knowledge ingestion (upload → extract → clean → chunk → embed → index) | IMPLEMENTED (Issue #3) |
| Hybrid retrieval (dense + lexical + fusion + reranking) + grounded generation + citations | IMPLEMENTED (Issue #4) |
| Product frontend (documents, chat, citations) | IMPLEMENTED (Issue #5, primary flow) |
| Voice (STT/TTS) as a mode within chat | IMPLEMENTED (Issue #6) |
| Evaluation harness, observability, security hardening | IMPLEMENTED (Issue #7) |
| Finalization (this document, final deployment/CI review) | IN PROGRESS (Issue #8) |

Some lower-priority product-experience items remain deferred and
documented, not silently dropped: standalone document search (outside
chat), per-conversation/per-document deep-link routes, viewing a cited
chunk's raw source text, message feedback, and rename/delete for
conversations. See [`PROJECT_STATE.md`](PROJECT_STATE.md) for the
authoritative, current status of every component, including these.

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

Real GitHub issues `#1`–`#8` track the work: `#1` Application
Foundation, `#2` Authentication & Workspaces, `#3` Knowledge Ingestion,
`#4` Hybrid RAG Pipeline, `#5` Product Experience, `#6` Voice, `#7`
Evaluation, Security & Observability — all merged — and `#8` CI/CD,
Deployment & Finalization, in progress. See
[`PROJECT_STATE.md`](PROJECT_STATE.md#immediate-priorities) for current
status and the exact next step.

## License

Not yet decided.
