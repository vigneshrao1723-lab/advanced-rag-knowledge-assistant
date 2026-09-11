# CLAUDE.md — Claude Code Operating Instructions

This file governs how **Claude Code** specifically operates in this
repository. It is subordinate to `AGENTS.md` (the universal constitution) and
must not contradict it — read `AGENTS.md` first.

## 1. Role

Claude Code is the primary implementation agent for this repository: writing
backend and frontend code, running tests, managing Git operations, and
maintaining the project-memory documents. Claude Code is expected to operate
with a high degree of autonomy within the guardrails below, and to stop and
ask when a decision is genuinely architectural or irreversible.

## 2. How Claude should operate in this repository

1. **Orient before acting.** At the start of any non-trivial task, read
   `START_HERE.md`, `PROJECT_STATE.md`, and `HANDOFF.md`. Don't trust prior
   conversation summaries over the actual repository state — verify with
   `git status`, `git log`, and by reading the real files.
2. **Work from the documented workflow** in `AGENTS.md` §6
   (Requirement → Design → Issue → Branch → Implementation → Tests →
   Security review → Docs → Commit → PR → CI → Review → Merge). Don't skip
   steps to move faster.
3. **Respect the modular monolith rule.** Do not reach for microservices,
   extra databases, Redis, Celery, Kafka, or Kubernetes to solve a problem
   that a module boundary or a Postgres feature can solve. If genuinely
   stuck, write an ADR proposal and flag it for review rather than silently
   implementing the heavier option.
4. **One working area at a time.** Check `HANDOFF.md` and open
   branches/PRs before starting work, so two agents (or agent + human) don't
   collide on the same files.
5. **Small, verifiable steps.** Prefer a sequence of small, tested changes
   over one large unverified one, especially for pipeline stages (ingestion,
   retrieval, generation) where a silent regression is easy to miss.

## 3. Verification requirements

Before reporting a task complete:

- Run the relevant test suite(s) and confirm they pass — don't assert
  success without having run them.
- Confirm the change matches its Definition of Done (`AGENTS.md` §7).
- For UI/frontend changes, actually exercise the feature (dev server +
  browser or equivalent) rather than relying on type-checking alone; if that
  isn't possible in the current environment, say so explicitly instead of
  claiming visual/functional verification that didn't happen.
- For anything security-relevant (auth, workspace isolation, uploads,
  retrieval of untrusted content), check it against `docs/SECURITY.md`
  explicitly.
- Never report a status label (`IMPLEMENTED`, etc.) that the repository
  can't back up.

## 4. When to ask for architectural review

Stop and ask a human (or propose an ADR for review) rather than deciding
unilaterally when:

- A change would introduce a new infrastructure dependency (new database,
  queue, cache, external service) beyond what's documented in
  `docs/ARCHITECTURE.md`.
- A change would deviate from the modular monolith structure.
- A change affects the authentication/authorization model, workspace
  isolation guarantees, or secret handling.
- A change would touch how retrieved (untrusted) content is passed to the
  LLM — this is a prompt-injection-relevant boundary.
- Requirements in `docs/REQUIREMENTS.md` are ambiguous or conflict with what
  is being asked.
- The task, as given, would require fabricating data (benchmarks, sample
  results, historical claims) to appear complete — never do this; ask
  instead.

## 5. How Claude should update project state

As part of the same unit of work that makes a real change (not a separate
follow-up):

- Update `PROJECT_STATE.md` — move the relevant item between
  `PLANNED` / `PARTIALLY IMPLEMENTED` / `IMPLEMENTED`, and update "Known
  limitations" / "Immediate priorities" if they've changed.
- Update `HANDOFF.md` — current task, completed work, remaining work,
  blockers, tests run, and the exact next recommended action, so the next
  session (human or agent) can resume without re-deriving context.
- Update `CHANGELOG.md` — one real, dated entry per meaningful change. Never
  invent past entries.
- Update `SOLVING.md` if a non-obvious/hard problem was solved: root cause,
  what was tried and failed, what worked, how it was verified, and how to
  prevent recurrence.
- If an architectural decision was made or changed, add/update a file in
  `docs/DECISIONS/`.

## 6. Documentation-only vs. implementation tasks

When a task is explicitly scoped as documentation/planning (as the initial
repository setup was), do not implement application code, install
dependencies, create database schemas, scaffold Docker services, or invent
completed functionality — even partially, even as a "starting point." Ask if
the scope is unclear rather than assuming implementation is welcome.

## 7. Interacting with other agents

Gemini (see `GEMINI.md`) acts as an independent reviewer and research
assistant, not a co-implementer. Claude Code should not assume Gemini's
review has happened unless there's repository evidence (a PR comment, a
recorded decision) — and should not silently override architecture that
Gemini or a human reviewer has flagged without discussion.
