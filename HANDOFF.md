# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Feature-completion sprint (Issue #41)** — bringing the product from
"core scope done" (Issues #1–#8, closed) to feature-complete against
`docs/REQUIREMENTS_MATRIX.md`'s seven remaining items, in priority order:

1. **Collections — done.** Merged as `06b8c9e` (PR #43).
2. **Standalone search UI — done.** Merged as `45e5c85` (PR #44).
3. **Full document viewer + citation highlighting — done.** Merged as
   `4cfc546` (PR #45).
4. **Answer regeneration — done.** Merged as `6822b76` (PR #46).
5. **Document management (rename/delete/download/filter/search) —
   done.** Merged as `b642afc` (PR #47).
6. **Command palette — done this pass, uncommitted.** See "Completed
   this pass" below.
7. Recursive chunking strategy — not started. **The last item.**

`main` is at `b642afc`. Work for item 6 is on branch
`feat/command-palette`, fully implemented and verified, not yet
committed.

## Completed this pass (uncommitted, on `feat/command-palette`)

- `frontend/components/command-palette.tsx` — a global `Ctrl+K`/
  `Cmd+K` palette, mounted once in `components/layout/shell.tsx`
  (`AppShell`) so it's available from every authenticated page.
  Deliberately no new dependency (`cmdk` etc.). A visible trigger
  button (bottom-right, `aria-label="Open command palette"`) plus the
  keyboard shortcut; actions for every real route (Dashboard/
  Documents/Collections/Search/Chat/Settings/Workspace) and a dynamic
  "Switch workspace to…" action per other workspace (excludes the
  current one). `evaluations`/`analytics` deliberately excluded —
  both remain `PageStub`s, matching the main nav's own existing
  precedent of not linking to still-stubbed routes.
- Avoided a `setState`-in-`useEffect` ESLint violation (this project's
  config flags it) by resetting the selected-index directly at each
  place the palette opens or the query changes, instead of via a
  derived effect watching `[query, isOpen]`.
- Tests: 9 new component tests
  (`frontend/components/command-palette.test.tsx` — renders nothing
  unauthenticated, opens via trigger and via `Ctrl+K`, filters by
  query, arrow-key-then-Enter navigates, click navigates, `Escape`
  closes, switch-workspace fires with the right ID, current workspace
  excluded from switch targets).
- `docs/ARCHITECTURE.md` and `docs/REQUIREMENTS_MATRIX.md` §6 and
  `PROJECT_STATE.md` updated to record the command palette as
  `COMPLETE` with evidence. No backend *feature* change this slice, so
  `docs/API_CONTRACT.md`/`docs/SECURITY.md` were untouched.
- **Found and fixed a real, reproduced flaky backend test** during the
  routine full-suite sanity run:
  `test_feedback_on_a_user_message_is_rejected` picked "the user
  message" by list position (`.json()[0]["id"]`) rather than role,
  the same shared-transaction `created_at`-tie fragility already fixed
  twice this sprint in the regenerate tests — it had just never
  actually flaked before. Fixed by selecting by role instead. See
  `SOLVING.md`'s 2026-10-24 entry for the full root-cause writeup and
  why two similar-looking matches in `test_auth.py` were confirmed
  safe, not fixed.

## Explicitly NOT done (do not assume otherwise)

- Item 7 (recursive chunking strategy) — see
  `docs/REQUIREMENTS_MATRIX.md` for its acceptance criteria and
  next-slice plan. No code yet. **This is the last item in the
  seven-item sprint scope.**
- Production hosting target remains undecided — see
  `docs/PRODUCTION_READINESS.md`; not this sprint's concern per
  `CLAUDE.md` §4.

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment.

## Tests run (this pass, on `feat/command-palette`, after the command-palette implementation)

- Frontend: `eslint` (clean), `tsc --noEmit` (clean), `vitest run` —
  **113/113 passed** (104 baseline + 9 new), `next build` succeeds (17
  routes).
- Backend: ran as a sanity check even though no backend *feature* code
  changed this slice — `uv run ruff check .`/`uv run mypy .` (the
  literal CI commands) clean, `uv run pytest -q`: first run surfaced
  the real flaky test above (1 failed, 796 passed); after the fix,
  re-ran it 3 times in a loop for the one affected test (all green,
  since a positional-tie bug can't be confirmed fixed by one run
  alone) and then the full suite once more — **797 passed, 1 skipped**.
- Playwright E2E, against a freshly `docker compose up --build -d`
  (frontend-only rebuild) stack: **21/21 passed**, no regression.
- Real-browser verification beyond the automated suites (a standalone
  Playwright-core script): visible trigger button present; `Ctrl+K`
  opens the palette while a text input already has focus, and that
  input's typed content is verified completely unaffected afterward;
  filter → arrow-down → Enter navigates to the right route; an
  outside click closes it; `Escape` closes it; a real switch-workspace
  action actually switches the active workspace. All 9 steps passed.
  (One demo-script bug along the way, not a product bug: the first
  draft never actually created a second workspace before asserting a
  "switch workspace" action existed, so there was nothing to switch
  to — fixed in the script itself, not the component.)

## Exact next recommended action

1. Provenance sweep (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   commit, push, open a PR referencing Issue #41, confirm CI green
   (this PR touches only frontend files, but still run the full
   backend suite once as a sanity check that nothing was accidentally
   touched), merge.
2. Continue to item 7 (recursive chunking strategy) — the matrix
   already has the acceptance criteria and next-slice plan: a new
   `RecursiveChunker` class implementing the existing
   `ChunkingStrategy` protocol
   (`backend/app/ingestion/chunking.py`) — splits by a prioritized
   separator list (section → paragraph → sentence → word), falling
   back to the next separator only when a piece still exceeds the
   configured chunk size; deterministic, same `Chunk` metadata shape
   as `StructureAwareChunker`. Add it to
   `eval/scripts/run_retrieval_evaluation.py`'s comparison set
   (alongside the existing `structure_aware`/`fixed_size` strategies)
   and re-run the real evaluation — record genuine, non-fabricated
   comparative numbers in `eval/results/`, and update
   `docs/EVALUATION.md`. This does **not** change the production
   pipeline's default strategy (`StructureAwareChunker` stays default)
   — it's a new, selectable option, not a replacement.
3. **This is the last item in the feature-completion sprint's stated
   seven-item scope.** Once it merges, update
   `docs/REQUIREMENTS_MATRIX.md`'s summary and `PROJECT_STATE.md` to
   reflect that Issue #41 is fully closed, and consider whether
   Issue #41 itself should be closed on GitHub (with a PR-referenced
   closing comment, matching this project's established convention for
   closing Issues #1–#8) — then give a final report covering the whole
   sprint, not just the last slice.
