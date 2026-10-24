# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Feature-completion sprint (Issue #41) — complete.** All seven items
are merged into `main`:

1. Collections — merged as `06b8c9e` (PR #43).
2. Standalone search UI — merged as `45e5c85` (PR #44).
3. Full document viewer + citation highlighting — merged as `4cfc546`
   (PR #45).
4. Answer regeneration — merged as `6822b76` (PR #46).
5. Document management (rename/delete/download/filter/search) —
   merged as `b642afc` (PR #47).
6. Command palette — merged as `f1426bc` (PR #48).
7. Recursive chunking strategy — merged as `4a17a38` (PR #49).

`main`/`origin/main` are at `4a17a38`. No feature branch is currently
checked out; local `main` is up to date with `origin/main`, working
tree clean.

## Completed this pass

Item 7 (recursive chunking) landed: `RecursiveChunker`
(`backend/app/ingestion/chunking.py`) — a third, evaluation-comparison-
only chunking strategy, 15 new unit tests, wired into
`eval/scripts/run_retrieval_evaluation.py`'s 3-way comparison and
re-run for real against Postgres (genuine results in
`eval/results/retrieval_evaluation.json`/`docs/EVALUATION.md`). Full
backend regression clean (812 passed, 1 skipped). PR #49 verified
green on all 4 required CI checks (backend, frontend, Docker build,
Playwright E2E) and merged. See `CHANGELOG.md`'s "committed" entry for
full detail.

This closes out the entire feature-completion sprint. All of
`docs/REQUIREMENTS_MATRIX.md` §1–7 are now `COMPLETE` with evidence.

## Explicitly NOT done (do not assume otherwise)

- **Production hosting target** — deliberately undecided. Per
  `CLAUDE.md` §4, selecting/paying for infrastructure is a human
  decision, not something to invent. Local Docker Compose remains the
  fully-verified, fully-supported way to run this project. See
  `docs/PRODUCTION_READINESS.md`/`docs/DEPLOYMENT.md`.
- Whether to close GitHub Issue #41 on GitHub itself — not yet done as
  of this entry; should happen with a PR-referenced closing comment,
  matching the Issues #1–#8 convention, once this file's "next action"
  below is carried out.

## Blockers

None for anything in this repository's control. The only open item
(production hosting) is blocked on an owner decision, not on any
technical or testing gap.

## Tests run (most recent pass, item 7 / PR #49)

- Backend: `uv run ruff check .` / `uv run mypy .` (literal CI
  commands, run inside the rebuilt Docker image) both clean (162
  source files). `uv run pytest -q` (full suite): **812 passed, 1
  skipped** — no regression (+15 over the prior 797 baseline, exactly
  matching the new recursive-chunker tests).
- Evaluation script: executed for real against Postgres (host-run,
  `DATABASE_URL` pointed at the compose stack's published `5432`
  port); exit 0; 12 `evaluation_runs` persisted; results file rewritten
  with genuine, non-fabricated numbers.
- Frontend/Playwright: unchanged this item (no frontend file touched);
  CI's frontend and Playwright jobs still ran and passed on PR #49 as
  a sanity check.
- GitHub Actions CI on PR #49: all 4 required checks green (backend
  lint/typecheck/tests; frontend lint/typecheck/tests/build; Docker
  build check; Playwright E2E).

## Exact next recommended action

1. Decide whether to close GitHub Issue #41 now that all seven tracked
   items are merged — if so, close it with a comment referencing PRs
   #43–#49, matching the established convention from closing Issues
   #1–#8.
2. The single highest-priority remaining action for this project as a
   whole is the **production hosting decision** (`docs/DEPLOYMENT.md`
   "Target deployment environment", `docs/PRODUCTION_READINESS.md`) —
   this requires the project owner, per `CLAUDE.md` §4, and is not
   something to decide or implement unilaterally.
3. No other implementation work is currently queued. Local Docker
   Compose (`infra/compose/docker-compose.yml`) is the verified way to
   run the full stack today.
