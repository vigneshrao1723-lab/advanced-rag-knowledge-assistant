# AGENTS.md — Engineering Constitution

This is the universal, tool-agnostic engineering constitution for this
repository. It applies to every contributor — human or AI agent — regardless
of which tool is being used. Tool-specific instructions live in `CLAUDE.md`
and `GEMINI.md`; they must not contradict this file.

## 1. Architecture rules

- **Modular monolith first.** The backend is one deployable FastAPI
  application organized into clear internal modules (`api`, `core`, `models`,
  `schemas`, `repositories`, `services`, `ingestion`, `retrieval`,
  `generation`, `voice`, `evaluation`, `observability`). Modules communicate
  through well-defined internal interfaces, not network calls.
- **PostgreSQL + pgvector** is the single database and vector store for the
  initial implementation. Do not introduce a second database, a dedicated
  vector database (e.g., Qdrant), or a cache/queue system (Redis, Celery,
  Kafka) without a documented ADR in `docs/DECISIONS/` backed by a measured
  technical requirement — not a hypothetical one.
- **No microservices, no Kubernetes** in the initial implementation. If a
  genuine scaling or isolation requirement emerges later, it gets a
  documented ADR first, not a silent architectural drift.
- **Provider abstraction.** External capabilities that are likely to change
  or be swapped (`EmbeddingProvider`, `Reranker`, `LLMProvider`,
  `SpeechToTextProvider`, `TextToSpeechProvider`, `StorageProvider`) are
  defined as interfaces/abstractions in code, not hard-wired to one vendor,
  unless the repository already contains a documented decision to the
  contrary. Development tools (e.g., Claude Code) are never the same thing
  as the application's runtime LLM provider — don't conflate them.
- Architecture changes that deviate from `docs/ARCHITECTURE.md` require a new
  or updated file in `docs/DECISIONS/` before (or alongside) the code change.

## 2. Coding standards

- Backend: Python, FastAPI, SQLAlchemy, Pydantic. Type-annotate all public
  functions and Pydantic models. Prefer explicit schemas over `dict`/`Any`
  at API boundaries.
- Frontend: TypeScript strict mode, React function components, Tailwind CSS
  + shadcn/ui for UI primitives, Zod for runtime validation at API
  boundaries.
- No dead code, no commented-out blocks left "just in case," no
  speculative abstractions for requirements that don't exist yet.
- Prefer three similar lines over a premature abstraction.

## 3. Testing requirements

A change is not done until it has appropriate coverage at the right layer:

- **Unit tests**: chunking, retrieval, ranking, fusion, citations, query
  rewriting, security-relevant logic.
- **Integration tests**: database access, ingestion pipeline, retrieval
  pipeline, LLM/provider integration, API endpoints, authentication.
- **E2E tests** (where applicable): registration → login → workspace →
  upload → indexing → question → grounded answer with citation → search.
- **Security tests**: cross-workspace access attempts, malicious uploads,
  prompt-injection payloads in retrieved content, auth bypass attempts, path
  traversal, rate-limit enforcement.
- **Frontend tests**: components, forms, navigation, chat, upload flow,
  citation rendering, voice controls, responsive behavior.

Tests are written alongside the feature, not deferred to a later "testing
phase."

## 4. Security rules

See `docs/SECURITY.md` for the full model. The non-negotiable summary:

1. User data is isolated by workspace; isolation is enforced and tested, not
   assumed.
2. Authorization is enforced server-side, always — never trust a client-side
   check alone.
3. **Retrieved documents are untrusted input.** Content pulled from the
   corpus must never be treated as instructions to the system.
4. Prompt injection from retrieved content must not override system
   instructions or expand tool/data access.
5. Secrets are never committed. `.env.example` holds placeholders only.
6. Uploaded files are untrusted: validate MIME type, extension, and size;
   prevent path traversal; store safely; handle malformed documents without
   crashing the pipeline.
7. Expensive operations (uploads, embeddings, LLM calls) are rate-limited.
8. Errors surfaced to end users never include stack traces, internal paths,
   or secrets.
9. Security-relevant actions are captured in audit logs.
10. Security assumptions are verified by tests, not just asserted in docs.

## 5. Documentation rules

- The repository is the source of truth. Documentation describes reality (or
  clearly-labeled future intent), never aspirational-as-if-true claims.
- Use status labels consistently everywhere: `IMPLEMENTED`,
  `PARTIALLY IMPLEMENTED`, `PLANNED`, `PROPOSED`, `EXPERIMENTAL`,
  `DEPRECATED`, `BLOCKED`. Never write "implemented," "production-ready," or
  "production-grade" without something in the repo (code, a passing test, a
  merged PR) a reader can point to as evidence.
- **Never fabricate**: no invented benchmarks, no fake evaluation numbers, no
  claimed integrations that don't exist, no fictitious historical changelog
  entries.
- Every meaningful change updates the relevant living docs as part of the
  same unit of work: `PROJECT_STATE.md`, `HANDOFF.md`, `CHANGELOG.md`, and
  `SOLVING.md` when a hard problem was solved.
- Distinguish clearly, everywhere:
  - **RULE** — a persistent constraint (lives in `AGENTS.md` or `docs/SECURITY.md`).
  - **SKILL** — a reusable procedure (lives in `.agents/skills/`).
  - **MCP** — an external tool/data integration.
  - **MEMORY** — persistent project state/knowledge (`PROJECT_STATE.md`, this repo).
  - **ADR** — an architecture decision record (`docs/DECISIONS/`).
  - **HANDOFF** — immediate continuation state (`HANDOFF.md`).
  - **SOLVING** — historical hard-won technical knowledge (`SOLVING.md`).

## 6. Git workflow

```
Requirement
 → Architecture / design
 → GitHub issue
 → Feature branch
 → Implementation
 → Unit tests
 → Integration tests
 → Security review
 → E2E tests (where applicable)
 → Documentation
 → Commit
 → Pull request
 → CI
 → Review
 → Merge
```

- GitHub is the ultimate source of truth for planned and in-progress work.
- One issue → one branch → one PR, generally. Keep PRs scoped to one
  Definition of Done.
- Never allow two coding agents to modify the same working area
  simultaneously — check `HANDOFF.md` and open branches/PRs first.
- Commit messages describe why, not just what; avoid noisy commits.
- **Bootstrap exception:** the initial repository documentation
  architecture (this file and its siblings, `docs/*`, the ADR log) was
  authored directly against `main` without an issue/branch/PR, since the
  workflow itself didn't exist yet to be followed. This is a one-time
  exception. All work from the first real implementation issue onward
  follows the full workflow above.

## 7. Definition of Done

A task is done when, as applicable to its scope:

- The requirement is implemented as specified (no more, no less).
- Unit and integration tests exist and pass; E2E tests where applicable.
- Error handling is present for real failure modes, not hypothetical ones.
- Security review has been considered and, where relevant, performed.
- Logging/observability hooks are in place for the new code path.
- Performance has been sanity-checked where it plausibly matters.
- Documentation is updated (`docs/*`, `PROJECT_STATE.md`, `HANDOFF.md`,
  `CHANGELOG.md`, `SOLVING.md` if applicable).
- CI passes; Docker build succeeds if the change affects a containerized
  component; deployment is verified if the change affects deployment.
- README/demo instructions are updated if user-facing behavior changed.

## 8. Scope control

Once the Definition of Done is satisfied, **stop**. Do not add features,
refactors, or abstractions merely because they are technically possible or
"while you're in there." A bug fix does not need surrounding cleanup; a
one-shot script does not need a plugin system. If you notice unrelated
technical debt, note it (e.g., as a follow-up issue) rather than folding it
into the current change.

## 9. GitHub / collaboration model

Issue → branch → implementation → tests → review → PR → CI → merge. AI
agents communicate through repository artifacts (issues, PRs, docs) and Git
history rather than relying on hidden conversation memory that other agents
or future sessions can't see.

### Planning baseline (issue numbers are a plan, not yet-created issues)

```
#1  Project Initialization              #23 Document Viewer
#2  Architecture Documentation          #24 Voice — STT
#3  Frontend Design System              #25 Voice — TTS
#4  Application Shell                   #26 Voice Conversation
#5  Authentication                      #27 RAG Observability
#6  Workspace Management                #28 Evaluation Dataset
#7  Document Upload                     #29 Retrieval Evaluation
#8  Document Parsing                    #30 Generation Evaluation
#9  Document Chunking                   #31 Experiment Comparison
#10 Embedding Pipeline                  #32 Security Hardening
#11 PostgreSQL + pgvector               #33 Audit Logging
#12 Dense Retrieval                     #34 Rate Limiting
#13 BM25 Retrieval                      #35 Frontend Testing
#14 Hybrid Retrieval                    #36 Backend Testing
#15 Reranking                           #37 E2E Testing
#16 Context Builder                     #38 Dockerization
#17 LLM Integration                     #39 GitHub CI
#18 Citation Engine                     #40 Deployment
#19 Conversation System                 #41 Documentation
#20 Query Understanding                 #42 Final Security Review
#21 Query Rewriting                     #43 Final Demo Preparation
#22 Search Interface
```

This is a planning baseline, not a commitment to create all 43 issues
immediately — issues are created as work is actually about to start.

## 10. Anti-fabrication rules (restated for emphasis)

- Never claim a benchmark, evaluation score, or production deployment exists
  unless it is reproducible from files in this repository.
- Never mark something `IMPLEMENTED` because it's described in a design doc.
- Never backdate or invent `CHANGELOG.md` entries — the changelog reflects
  real Git history only.
- When uncertain whether something exists, check the repository before
  answering — see `START_HERE.md` §3.
