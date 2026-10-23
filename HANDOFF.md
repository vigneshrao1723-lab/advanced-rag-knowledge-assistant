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
4. **Answer regeneration — done this pass, uncommitted.** See
   "Completed this pass" below.
5. Document management beyond list/get/upload/process (delete/rename/
   download/filter) — not started.
6. Command palette — not started.
7. Recursive chunking strategy — not started.

`main` is at `4cfc546`. Work for item 4 is on branch
`feat/regenerate-response`, fully implemented and verified, not yet
committed.

## Completed this pass (uncommitted, on `feat/regenerate-response`)

- `POST /workspaces/{id}/conversations/{id}/messages/{id}/regenerate`
  (MEMBER+): `backend/app/api/v1/conversations.py`,
  `conversation_service.regenerate_message()`. Finds the preceding
  `USER` message (`message_repository.get_preceding_user_message()`,
  new), re-runs the same `_run_retrieval_and_generation()` helper
  `post_message()` uses, replaces the assistant message's content in
  place (`message_repository.update_content()`, new — clears prior
  feedback) and its citations
  (`citation_repository.delete_for_message()`, new, immediately before
  `bulk_create()` persists fresh ones — a generation failure happens
  before either call, so the prior answer is never touched). Same rate
  limit as posting a message.
- A "Regenerate" button (`RotateCcw` icon) on each assistant message in
  `frontend/app/chat/page.tsx` (renamed the `MessageBubble` callback
  prop from `onFeedbackChanged` to `onMessageUpdated` since it's now
  shared by feedback and regenerate — same "replace this message by
  id" behavior either way, just a more accurate name).
- Tests: 8 new backend (`tests/test_conversations.py`: fresh grounded
  answer + citations with message id/history-length unchanged,
  feedback cleared, regenerating a `USER` message is `404`,
  nonexistent message `404`, cross-workspace `404`, VIEWER `403`,
  unauthenticated `401`, rate limit enforced), 1 new frontend test.
- `docs/API_CONTRACT.md`, `docs/SECURITY.md`,
  `docs/REQUIREMENTS_MATRIX.md` §4, and `PROJECT_STATE.md` updated to
  record regenerate as `COMPLETE` with evidence.

## Explicitly NOT done (do not assume otherwise)

- Items 5–7 above (document management, command palette, recursive
  chunking) — see `docs/REQUIREMENTS_MATRIX.md` for each one's
  acceptance criteria and planned next slice. None have any code yet.
- Production hosting target remains undecided — see
  `docs/PRODUCTION_READINESS.md`; not this sprint's concern per
  `CLAUDE.md` §4.

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment.

## Tests run (this pass, on `feat/regenerate-response`, after the regenerate implementation)

- Backend: `uv run ruff check .` (clean), `uv run mypy .` — **the
  literal CI command, checked before pushing this time** (see
  `SOLVING.md`'s 2026-10-23 entry from the prior pass) — clean.
  `uv run pytest -q` — **780 passed, 1 skipped** (772 baseline + 8 new).
- Frontend: `eslint` (clean), `tsc --noEmit` (clean), `vitest run` —
  **99/99 passed** (98 baseline + 1 new), `next build` succeeds.
- Playwright E2E, against a freshly `docker compose up --build -d`
  stack: **21/21 passed**, no regression.
- Real-browser verification beyond the automated suites (a standalone
  Playwright-core script): register → workspace → upload/process a
  document → ask a question in chat → rate the answer "good" → click
  Regenerate → confirm the new answer is still grounded in the real
  document and the prior rating was cleared (`aria-pressed` false
  again). All 8 steps passed. (One demo-script bug along the way, not
  a product bug: the script initially skipped the "New conversation"
  click the chat page needs before a composer renders, then read the
  feedback button's `aria-pressed` attribute immediately after
  clicking instead of waiting for the async update — both fixed in the
  script itself.)

## Exact next recommended action

1. Provenance sweep (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   commit, push, open a PR referencing Issue #41, confirm CI green
   (check the literal CI commands locally first), merge.
2. Continue to item 5 (document management beyond list/get/upload/
   process) — the matrix already has the acceptance criteria and
   next-slice plan: `StorageProvider.delete()` (new) → `DELETE
   .../documents/{id}` (decide and implement an explicit
   citation-retention policy — keep historical citations pointing at a
   deleted document rather than cascading message deletion, so a past
   chat answer's history doesn't disappear because its source document
   was later removed) → `PATCH .../documents/{id}` (rename) → `GET
   .../documents/{id}/download` → UI buttons → tests. This is the one
   remaining item flagged as needing the most care (storage cleanup +
   an explicit, documented decision about what happens to citations),
   not just mechanical wiring like items 1–4.
3. Continue through items 6–7 in the matrix's stated priority order,
   each as its own small, independently tested, separately merged PR.
   If the available time/effort doesn't cover all seven, update the
   matrix and this file to say exactly which remain, honestly.
