# 72-Hour Delivery Plan — Advanced RAG Knowledge Assistant

**Baseline:** `main` at `1797b7f` (2026-10-01 state recorded in project docs; re-check live GitHub before relying on any count).  
**Deadline:** 72 hours from kickoff.  
**Operating rule:** no architecture rewrite; keep the modular monolith and real backend APIs. Protect the existing green test baseline.

## Verified project position from the latest handoff

- Backend: FastAPI, PostgreSQL + pgvector, Redis, Alembic; document ingestion to READY; hybrid retrieval (dense + lexical, RRF, reranking); grounded answers with citations and source inspection; text and offline voice paths; workspace-scoped access controls, auth/session/CSRF, rate limiting and abuse detection.
- Frontend: Next.js 16 + React + TypeScript + Tailwind v4 + shadcn/Radix/Lucide; real login/register/recovery, dashboard, workspace, documents, chat, citations/source inspection, voice, feedback, conversation rename/delete.
- Last reported verification: backend 744 passed + 1 intentional skip; frontend 76/76; Playwright 20/20; ruff/mypy/eslint/TypeScript/build clean; migration 0009 reversible; full local Docker Compose stack healthy. Re-run these from the current checkout before final sign-off.
- Remaining explicit gaps: collections; standalone retrieval search; command palette; full document viewer with contextual highlighting; response regenerate/retry; document CRUD beyond list/get/upload/process; recursive chunking strategy; production host and production-specific deployment configuration. Avoid promising these as complete.

## 72-hour plan

### Hours 0–6 — Re-baseline and freeze scope
- Pull latest `main`; verify clean worktree, current SHA, migrations, Docker services and environment.
- Run backend lint/typecheck/tests, frontend lint/typecheck/tests/build, Playwright, Alembic upgrade check.
- Capture failures as baseline vs new regression. Do not change production code until the current baseline is understood.
- Confirm all nav links lead to real routes; remove or clearly mark unavailable routes rather than shipping 404s.
- Make a small visual inventory of public home, auth, dashboard, documents, chat, workspace and settings.

### Hours 6–24 — High-impact frontend design pass
- Establish one design system: restrained ink/indigo/teal palette, consistent spacing, typography, radii, focus rings, card elevation and semantic status colors.
- Replace the stale foundation-only homepage with a product landing page that explains the workflow, shows the actual capabilities, links to sign-in/register and surfaces backend readiness without exposing environment/debug details.
- Improve shared navigation and responsive behavior first; then auth screens, dashboard and workspace selector.
- Ensure loading, empty, error, disabled, success and destructive-confirmation states are intentional.
- Use existing components/dependencies first; do not add a large UI library during the deadline.

### Hours 24–42 — Product workflows and backend integration
- Documents: clear upload dropzone, supported formats/size guidance from actual backend config, processing state/progress wording, retry/failure messages, document list and empty state.
- Chat: polished conversation list, search filter, message composer, voice mode, citation chips/source panel, feedback, rename/delete confirmation, error/retry affordances. Keep citations visibly tied to answer evidence.
- Dashboard: workspace context and clear next action; avoid fabricated metrics or fake analytics.
- Verify every interaction calls the existing API and reflects persisted state; do not add mock success states.
- Backend changes only for verified UI-blocking defects or security/data integrity issues; keep them in focused, tested slices.

### Hours 42–54 — Accessibility, responsive QA and high-value gaps
- Test narrow mobile, tablet and desktop; keyboard-only navigation; focus visibility; labels; contrast; reduced motion; screen-reader names.
- Fix top user-visible bugs and broken links. Prefer accessibility and reliable core flow over adding collections or command palette late.
- If all core workflows are stable, implement at most one small additional feature only if its API/data model already exists and it can be tested end-to-end; otherwise document it as deferred.

### Hours 54–66 — Regression and security gate
- Backend: full suite, ruff, mypy.
- Frontend: Vitest, ESLint, TypeScript, production build.
- E2E: Playwright on a freshly rebuilt Docker Compose stack; test register/login, workspace, upload/process/READY, ask/citations/source inspection, feedback, rename/delete, logout/session behavior.
- Recheck cross-workspace IDOR boundaries, CSRF, cookie-only auth, upload validation/path traversal, prompt injection and error redaction.
- Verify Alembic migration upgrade/downgrade/upgrade and Compose health/readiness.

### Hours 66–72 — Release preparation
- Fix only release-blocking defects; rerun focused tests then full impacted suites.
- Update README, screenshots, setup/demo commands, architecture diagram, limitations and known provider constraints.
- Update `PROJECT_STATE.md`, `HANDOFF.md`, `CHANGELOG.md`, `SOLVING.md`, API/security/deployment docs only where the actual implementation changed.
- Verify GitHub PR/CI/main state, no untracked work, no secrets, no debug UI, no broken routes.
- Record a truthful final scorecard and list the production hosting decision as pending until a human selects a provider.

## Visual direction

**Product feeling:** calm, credible, evidence-first AI workspace — closer to a polished knowledge-work tool than a generic chatbot.

- Typography: existing Geist; clear display heading and compact labels.
- Colors: deep ink/slate base, indigo primary, teal evidence accent, warm neutral surfaces; reserve red/amber for actual error/warning states.
- Layout: generous whitespace, readable max-width, responsive grid, simple borders, restrained shadows.
- Interaction: visible hover/focus states, subtle motion only, no decorative animation that harms performance.
- Trust: show citations/source inspection, workspace isolation and local-provider/offline capability accurately; never claim unsupported security certification or production readiness.
- Reuse current Next.js, Tailwind, shadcn/Radix and Lucide dependencies; avoid dependency churn.

## Definition of done

1. Homepage accurately represents the product and offers working login/register paths.
2. No visible navigation link points to an unavailable page.
3. Core workflows are usable on mobile and desktop with complete loading/empty/error/success states.
4. UI uses real API data and never fabricates analytics or successful operations.
5. All existing test suites and build checks pass on the final commit.
6. Documentation matches the code and honestly records deferred scope and deployment decisions.
