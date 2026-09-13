# PROJECT_STATE.md

**Last updated:** 2026-09-13
**Current phase:** GitHub Issue #2 — Authentication & Workspaces
(repository: `vigneshrao1723-lab/advanced-rag-knowledge-assistant`, branch
`issue-2-authentication-workspaces`)

This is the authoritative, living snapshot of the project's real state. If
this file ever disagrees with the actual repository contents, the repository
wins — fix this file.

**Committed baseline vs. current uncommitted implementation:** the
documentation/project-memory system (`START_HERE.md`, `AGENTS.md`, etc.,
plus `docs/DECISIONS/0001`–`0003`) and the entire Issue #1 Application
Foundation (`backend/`, `frontend/`, `infra/`, `.github/workflows/` as they
stood then) are committed and merged to `main` (PR #9). Everything added or
changed for **Issue #2 — Authentication & Workspaces** (the auth/workspace
backend code, the new frontend auth/workspace pages, `docs/DECISIONS/0004`,
the CI workflow's new Postgres service block, and this update to
`PROJECT_STATE.md`/`HANDOFF.md`/`CHANGELOG.md`/`docs/API_CONTRACT.md`)
exists only in the local working tree on branch
`issue-2-authentication-workspaces` and has **not yet been committed,
pushed, or merged** (`git status` is the ground truth). Statuses like
`IMPLEMENTED` below describe content that exists on disk and has been
verified to run/pass now; they are not a claim about Git history — see
`CHANGELOG.md` for the same distinction.

## Status legend

`IMPLEMENTED` · `PARTIALLY IMPLEMENTED` · `PLANNED` · `PROPOSED` ·
`EXPERIMENTAL` · `DEPRECATED` · `BLOCKED`

## Current architecture

The Application Foundation (Issue #1, merged) provides the FastAPI backend
skeleton, Next.js frontend, PostgreSQL + pgvector, Docker Compose, and CI.
Authentication & Workspaces (Issue #2, this phase) adds the first real
feature vertical slice on top of it: registration/login/logout/refresh/
session management and workspace CRUD/membership/roles, enforced
server-side end to end. Ingestion, retrieval, generation, chat, search, and
voice still do not exist.

## Component status

| Component | Status | Notes |
|---|---|---|
| Documentation architecture (`START_HERE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `PROJECT_STATE.md`, `HANDOFF.md`, `SOLVING.md`, `CHANGELOG.md`, `docs/*`) | IMPLEMENTED (baseline committed on `main`) | `PROJECT_STATE.md`, `HANDOFF.md`, `CHANGELOG.md`, and `docs/API_CONTRACT.md` have further uncommitted edits in the working tree reconciling them with the Issue #2 implementation below. |
| `docs/DECISIONS/` ADR log | IMPLEMENTED (0001–0003 committed on `main`; 0004 in working tree, not yet committed) | Four ADRs: modular monolith, Postgres/pgvector, authentication/session architecture, and (new, Issue #2) password hashing algorithm. |
| `.gitignore` / `.gitattributes` / `.env.example` | IMPLEMENTED | Placeholders only, no real secrets. `.env.example` has further uncommitted edits (Issue #2): `SECRET_KEY` is now documented as required, plus `ACCESS_TOKEN_EXPIRE_MINUTES`/`REFRESH_TOKEN_EXPIRE_DAYS`. |
| GitHub remote & issues | IMPLEMENTED | Remote configured (`origin` → `vigneshrao1723-lab/advanced-rag-knowledge-assistant`). Real, filed GitHub issues `#1`–`#8` exist (confirmed via `gh issue list`): `#1` Application Foundation (merged), `#2` Authentication & Workspaces (this phase), `#3` Knowledge Ingestion, `#4` Hybrid RAG Pipeline, `#5` Product Experience, `#6` Voice, `#7` Evaluation/Security/Observability, `#8` CI/CD/Deployment/Finalization. Separate from these real issues, `AGENTS.md` §9 also documents a finer-grained `#1`–`#43` **internal planning baseline** for task breakdown — the two numbering schemes don't map 1:1; don't confuse them. |
| Backend application (`backend/`) | IMPLEMENTED (Issue #1 baseline committed on `main`; Issue #2 auth/workspace additions in working tree, not yet committed) | Config, structured logging, request-ID middleware, centralized error handling, SQLAlchemy + Alembic, health/readiness — plus (Issue #2) auth/workspace services, repositories, schemas, API routes. Verified: `ruff check` clean, `mypy --strict` clean (54 files), `pytest` 69/69 passing (real Postgres). |
| Frontend application (`frontend/`) | IMPLEMENTED (Issue #1 baseline committed on `main`; Issue #2 auth/workspace pages in working tree, not yet committed) | Next.js 16 + TypeScript, Tailwind v4, shadcn/ui. `chat/collections/documents/evaluations/search` remain stub routes (later issues); `login/register/dashboard/settings/workspace` are now real, backed by `lib/auth-context.tsx` + `lib/workspace-context.tsx` + `lib/api-client.ts`. Verified: `eslint` clean, `tsc --noEmit` clean, `vitest` 22/22 passing, `next build` succeeds. |
| Database schema / migrations | PARTIALLY IMPLEMENTED | Migration `0001` enables `pgvector` (Issue #1); `0002` adds `users`, `sessions`, `workspaces`, `workspace_members` (Issue #2), verified applied (and reversible — downgrade/re-upgrade tested) against the real container. Remaining `docs/DATA_MODEL.md` entities (`documents`, `document_chunks`, `collections`, etc.) land with the features that need them. |
| Authentication | IMPLEMENTED (in working tree; not yet committed) | Registration, login, logout, Argon2id password hashing ([ADR 0004](docs/DECISIONS/0004-password-hashing-argon2id.md)), JWT access tokens + PostgreSQL-backed sessions with refresh rotation and reuse-detection revocation (ADR 0003), session/device listing and revocation, per-endpoint rate limiting. `backend/app/{core/security.py,core/rate_limit.py,services/auth_service.py,api/v1/auth.py}`. |
| Workspaces | IMPLEMENTED (in working tree; not yet committed) | CRUD, membership, four-role authorization matrix (OWNER/ADMIN/MEMBER/VIEWER — see `docs/API_CONTRACT.md`), server-side `require_workspace_role` dependency enforced on every workspace-scoped route, last-owner protection. `backend/app/{services/workspace_service.py,api/v1/workspaces.py,core/dependencies.py}`. Frontend: `/register`, `/login`, `/dashboard`, `/settings`, `/workspace` are real (no longer stubs). |
| Document upload & ingestion pipeline | PLANNED | Pipeline states documented in `docs/RAG_DESIGN.md`; no code. |
| Retrieval (dense / BM25 / hybrid / rerank) | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Generation & citations | PLANNED | Documented in `docs/RAG_DESIGN.md`; no code. |
| Conversations / chat | PLANNED | No code. |
| Search interface | PLANNED | No code. |
| Voice (STT/TTS) | PLANNED | Explicitly scoped to come after text RAG works; no code. |
| Evaluation harness | PLANNED | Metrics and methodology documented in `docs/EVALUATION.md`; **no evaluation has been run, no numbers exist.** |
| Observability / audit logging | PARTIALLY IMPLEMENTED | Structured logging, request-ID propagation, and a JSON access log exist (`app/observability/`); no persistent audit-log table or retention policy yet — that's a later issue. |
| Testing (unit/integration/E2E/security) | PARTIALLY IMPLEMENTED | Backend: 69 pytest tests, including real-database integration tests (registration→DB, login→session, refresh rotation/reuse-detection, logout, workspace CRUD/membership/roles) and explicit cross-workspace-isolation/IDOR security tests (`tests/test_auth.py`, `tests/test_workspaces.py`) run against a real Postgres via SQLAlchemy's "join an external transaction" pattern (`tests/conftest.py`). Frontend: 22 vitest tests (forms, auth state, nav, workspace switching/permission-sensitive UI). No E2E browser suite yet (Playwright not introduced — out of scope for this issue). |
| CI/CD (`.github/workflows/`) | IMPLEMENTED (Issue #1 baseline committed on `main`; Issue #2 additions in working tree, not yet committed) | `.github/workflows/ci.yml`: backend job now additionally provisions a real `pgvector/pgvector:pg16` service container and runs Alembic migrations before lint/typecheck/pytest (Issue #2 — needed for the new integration/security tests). Not yet run on GitHub Actions for these changes (no push yet) — verified locally instead. |
| Docker / deployment (`infra/`) | IMPLEMENTED (Issue #1 baseline committed on `main`; Issue #2 `SECRET_KEY` wiring in working tree, not yet committed) | `infra/docker/backend.Dockerfile`, `infra/docker/frontend.Dockerfile`, `infra/compose/docker-compose.yml`. Verified: both images rebuilt with the new backend dependencies (argon2-cffi, pyjwt), full stack starts healthy, migrations `0001`+`0002` apply, and a live registration→login→workspace-create→cross-workspace-isolation flow was exercised via curl against the running containers. |
| Skills system (`.agents/skills/`) | PARTIALLY IMPLEMENTED | Roster and process documented (`.agents/skills/README.md`); individual skill procedures not yet written. |

## Known limitations

- Authentication and workspace management are real, but ingestion,
  retrieval, generation, chat, search, and voice do not exist yet.
  `README.md` setup instructions are still deferred until an end user has
  something to actually do once logged in.
- No evaluation data or numbers exist. Any future mention of retrieval or
  generation quality metrics must come from an actual run recorded under
  `eval/results/` (once that directory exists) — never fabricated.
- Real GitHub issues `#1`–`#8` exist and are open (verified via
  `gh issue list --repo vigneshrao1723-lab/advanced-rag-knowledge-assistant`).
  `AGENTS.md` §9 separately documents a `#1`–`#43` internal planning
  baseline for finer task breakdown — those numbers are planning
  references only and don't correspond to real issues; don't confuse them
  with the real `#1`–`#8`.
- ADR 0003's previously-open implementation details are now resolved:
  access tokens expire in 15 minutes, refresh tokens in 30 days (both
  configurable), both are delivered in the JSON response body (not
  cookies — see `docs/API_CONTRACT.md`), and reuse of a rotated-out refresh
  token revokes that one session (not all of the user's sessions). Password
  hashing is Argon2id ([ADR 0004](docs/DECISIONS/0004-password-hashing-argon2id.md)).
- The frontend stores access/refresh tokens in `localStorage`
  (`frontend/lib/auth-storage.ts`) — a pragmatic choice for this issue's
  scope, not a claim that XSS-hardening (CSP, etc.) is in place. Revisit if
  a stronger threat model is required.
- Rate limiting (`backend/app/core/rate_limit.py`) is in-process only,
  correct for the current single-`uvicorn`-process deployment
  (`infra/docker/backend.Dockerfile` runs no `--workers`); it would need
  revisiting (a new ADR) if the backend is ever scaled to multiple
  processes/instances.
- No email verification, password reset, or full profile-editing exists —
  only registration, login, and `GET /users/me`. Out of this issue's scope;
  not yet scheduled against a specific future issue.
- No browser-based E2E suite (e.g. Playwright) exists yet — the
  register→login→create-workspace→switch→logout flow is covered by backend
  integration tests and frontend component tests, not a real browser E2E
  run.
- The backend's CORS policy (`CORS_ALLOWED_ORIGINS`) defaults to
  `http://localhost:3000` for local development only; it has not been
  reviewed for any non-local deployment target, since none is decided yet.

## Immediate priorities

1. Review and commit the Authentication & Workspaces work (backend,
   frontend, migration, CI update, ADR 0004, and this documentation
   update) — currently all uncommitted in the working tree on
   `issue-2-authentication-workspaces`.
2. Push the branch and open a PR against `main` referencing GitHub Issue
   #2, so CI (including the new Postgres-backed integration tests) actually
   runs on GitHub Actions for the first time; confirm it's green before
   merging.
3. After Issue #2 merges, begin GitHub Issue #3 (Knowledge Ingestion).

## How to keep this file honest

Any PR that changes what's implemented must update the relevant row(s) in
the table above as part of the same change — see `CLAUDE.md` §5 and
`AGENTS.md` §5.
