# START HERE

This file is the mandatory entry point for **any** human or AI agent (Claude
Code, Gemini, or otherwise) working in this repository. Read it before
touching any file.

## 1. What this repository is, right now

This is the **Advanced RAG Knowledge Intelligence Assistant** repository. As
of this writing it contains **documentation and project scaffolding only** —
no backend, no frontend, no database, no CI, no deployed infrastructure. The
target system is described in `docs/`, but describing a system is not
evidence that it exists. Treat the actual files on disk as ground truth, not
this document's description of the target.

## 2. Mandatory reading order

Read in this order before making changes:

1. **`START_HERE.md`** (this file) — rules of the road.
2. **`AGENTS.md`** — the engineering constitution: coding standards,
   architecture rules, testing requirements, security rules, documentation
   rules, Git workflow, and scope-control rules. This is the highest-authority
   behavioral document in the repo.
3. **`PROJECT_STATE.md`** — what currently exists, what's in progress, what's
   planned. This is the fastest way to learn the *real* current state.
4. **`HANDOFF.md`** — the specific task in flight right now, if any, and the
   exact next recommended action.
5. Agent-specific instructions: **`CLAUDE.md`** if you are Claude Code,
   **`GEMINI.md`** if you are Gemini.
6. Relevant files under **`docs/`** for the area you're about to touch
   (`docs/ARCHITECTURE.md`, `docs/RAG_DESIGN.md`, `docs/SECURITY.md`, etc.),
   including **`docs/DECISIONS/`** — architecture decisions there are
   binding; don't silently drift from one, propose a new ADR instead.
7. **`.agents/skills/`** if a reusable procedure exists for the kind of
   work you're about to do (review, security audit, evaluation, etc.).
8. **`SOLVING.md`** if you're debugging something hard — check whether this
   problem (or one like it) has already been solved and documented.

## 3. How to determine current state (don't trust memory or prose)

Before claiming anything is implemented, verify it directly:

- `git log --oneline -20` and `git status` for real history and working-tree
  state.
- `find . -path ./.git -prune -o -print` (or equivalent) for what directories
  and files actually exist.
- Read the actual source files, not just their names — a file existing does
  not mean it's implemented, and a `TODO`/stub is not "done."
- Check `PROJECT_STATE.md` for the maintained status table, but treat it as
  potentially stale if it disagrees with what you observe in the repo — fix
  the doc if so.

## 4. Repository rules (non-negotiable)

- **The repository is the source of truth**, not conversation history, not
  assumptions, not this prompt's description of the target system.
- **Never fabricate**: no invented benchmarks, no claimed "production-ready"
  status, no completed features that don't exist in code, no evaluation
  numbers that weren't actually measured.
- **Use status labels consistently**: `IMPLEMENTED`, `PARTIALLY IMPLEMENTED`,
  `PLANNED`, `PROPOSED`, `EXPERIMENTAL`, `DEPRECATED`, `BLOCKED`. Never say
  "implemented" or "production-ready" without repository evidence a reader
  can independently verify (a file, a passing test, a merged PR).
- **Modular monolith, not microservices.** PostgreSQL + pgvector is the
  initial and only database/vector store. Do not introduce Kubernetes, Kafka,
  Redis, Celery, Qdrant, or additional databases without a documented ADR in
  `docs/DECISIONS/` justified by a measured requirement.
- **Text RAG before voice.** Voice is a mode within Chat, not a separate
  application, and comes after the text pipeline works.
- **Scope control**: once a task's Definition of Done (see `AGENTS.md`) is
  satisfied, stop. Don't add features because they're technically possible.

## 5. How to continue work safely

1. Read `HANDOFF.md` for the exact in-flight task and next action.
2. Confirm the working tree is clean (`git status`) before starting; if not,
   investigate before touching anything — don't discard unfamiliar changes.
3. Make the smallest change that satisfies the current task's Definition of
   Done, following the workflow in `AGENTS.md`
   (Requirement → Design → Issue → Branch → Implementation → Tests →
   Security review → Docs → Commit → PR → CI → Review → Merge).
4. Update `PROJECT_STATE.md`, `HANDOFF.md`, and `CHANGELOG.md` as part of the
   change, not as an afterthought. Update `SOLVING.md` if you solved something
   non-obvious.
5. Never work on the same area as another agent simultaneously — check
   `HANDOFF.md` and open branches first.

## 6. What NOT to do in this repository (until explicitly instructed)

- Do not scaffold `backend/` or `frontend/` application code speculatively.
- Do not install dependencies or add lockfiles.
- Do not create Docker services, database migrations, or CI workflows ahead
  of the corresponding documented, planned work item.
- Do not commit secrets — `.env.example` holds placeholders only.
- Do not silently rewrite architecture decisions recorded in
  `docs/DECISIONS/` — propose a new ADR instead.
