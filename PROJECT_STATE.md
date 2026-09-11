# PROJECT_STATE.md

**Last updated:** 2026-09-11
**Current phase:** Phase 0 — Project Initialization & Documentation

This is the authoritative, living snapshot of the project's real state. If
this file ever disagrees with the actual repository contents, the repository
wins — fix this file.

**Working tree vs. committed state:** as of this update, the documentation
set described below exists in the local working tree but has **not yet
been committed** (`git status` shows it as modified/untracked). Statuses
like `IMPLEMENTED` in the table below describe content that exists on disk
now; they are not a claim that it is in Git history yet. See
`CHANGELOG.md` for the same distinction.

## Status legend

`IMPLEMENTED` · `PARTIALLY IMPLEMENTED` · `PLANNED` · `PROPOSED` ·
`EXPERIMENTAL` · `DEPRECATED` · `BLOCKED`

## Current architecture

Nothing has been implemented yet beyond documentation and repository
scaffolding. The **target** architecture (modular-monolith FastAPI backend +
Next.js frontend + PostgreSQL/pgvector) is documented in
`docs/ARCHITECTURE.md` and recorded as ADRs in `docs/DECISIONS/`, but no
backend, frontend, database, or infrastructure code exists in this
repository yet.

## Component status

| Component | Status | Notes |
|---|---|---|
| Documentation architecture (`START_HERE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `PROJECT_STATE.md`, `HANDOFF.md`, `SOLVING.md`, `CHANGELOG.md`, `docs/*`) | IMPLEMENTED (in working tree; not yet committed) | Populated and corrected during Phase 0 initialization and its second-pass audit. |
| `docs/DECISIONS/` ADR log | IMPLEMENTED (in working tree; not yet committed) | Process + three ADRs recorded (modular monolith, Postgres/pgvector, authentication/session architecture). |
| `.gitignore` / `.gitattributes` / `.env.example` | IMPLEMENTED | Present from prior initialization commits; placeholders only, no real secrets. `.env.example` updated in working tree (not yet committed) with a reranker placeholder. |
| GitHub remote & issue plan | PARTIALLY IMPLEMENTED | Remote configured (`origin`); issue plan documented in `AGENTS.md` as a **planning baseline only** — the `#1`–`#43` numbers are planning references, not existing GitHub issues. |
| Backend application (`backend/`) | PLANNED | Directory does not exist yet. Target module layout documented in `docs/ARCHITECTURE.md`. |
| Frontend application (`frontend/`) | PLANNED | Directory does not exist yet. Target route/component layout documented in `docs/ARCHITECTURE.md`. |
| Database schema / migrations | PLANNED | Target entities documented in `docs/DATA_MODEL.md`; no migrations exist. |
| Authentication | PLANNED | Requirements documented in `docs/REQUIREMENTS.md`; no code. |
| Workspaces | PLANNED | Requirements documented; no code. |
| Document upload & ingestion pipeline | PLANNED | Pipeline states documented in `docs/RAG_DESIGN.md`; no code. |
| Retrieval (dense / BM25 / hybrid / rerank) | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Generation & citations | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Conversations / chat | PLANNED | No code. |
| Search interface | PLANNED | No code. |
| Voice (STT/TTS) | PLANNED | Explicitly scoped to come after text RAG works; no code. |
| Evaluation harness | PLANNED | Metrics and methodology documented in `docs/EVALUATION.md`; **no evaluation has been run, no numbers exist.** |
| Observability / audit logging | PLANNED | Requirements documented in `docs/SECURITY.md` / `docs/RAG_DESIGN.md`; no code. |
| Testing (unit/integration/E2E/security) | PLANNED | Strategy documented in `AGENTS.md` §3; no test suite exists yet. |
| CI/CD (`.github/workflows/`) | PLANNED | Directory does not exist yet; workflow described in `docs/DEPLOYMENT.md`. |
| Docker / deployment (`infra/`) | PLANNED | Directory does not exist yet; approach described in `docs/DEPLOYMENT.md`. |
| Skills system (`.agents/skills/`) | PARTIALLY IMPLEMENTED | Roster and process documented (`.agents/skills/README.md`); individual skill procedures not yet written. |

## Known limitations

- There is no runnable application. `README.md` setup instructions are
  intentionally deferred until there is something to run.
- No evaluation data or numbers exist. Any future mention of retrieval or
  generation quality metrics must come from an actual run recorded under
  `eval/results/` (once that directory exists) — never fabricated.
- GitHub issues `#1`–`#43` (see `AGENTS.md` §9) are a planning baseline
  only; they have not been created as actual GitHub issues yet, and none of
  these numbers should be read as referring to a real, existing issue.
- Authentication is architecturally resolved (see
  [ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md))
  but several implementation details (token lifetimes, refresh delivery
  mechanism, reuse-detection response) remain open until Authentication is
  actually implemented.

## Immediate priorities

1. Confirm documentation architecture is complete and internally consistent
   — a second-pass audit identified and corrected several cross-document
   inconsistencies, including the authentication model, the `sessions`
   data model, and the rate-limiting approach (see `HANDOFF.md`).
2. Begin **Architecture Documentation** refinement and **Frontend Design
   System** work (baseline planning references `#2`–`#3` in `AGENTS.md`
   §9 — these are not yet created as GitHub issues) before any backend
   implementation starts.
3. Stand up a FastAPI backend skeleton and PostgreSQL + pgvector locally.
   `AGENTS.md`'s baseline references `#11` for the pgvector setup
   specifically; the baseline has no dedicated "backend skeleton" line
   item distinct from `#4` ("Application Shell") — scope that explicitly
   when the corresponding issue is actually filed, rather than assuming
   `#4` covers it.

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5.
