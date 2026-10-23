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
3. **Full document viewer + citation highlighting — done this pass,
   uncommitted.** See "Completed this pass" below.
4. Answer regeneration/retry — not started.
5. Document management beyond list/get/upload/process (delete/rename/
   download/filter) — not started.
6. Command palette — not started.
7. Recursive chunking strategy — not started.

`main` is at `45e5c85`. Work for item 3 is on branch
`feat/document-viewer`, fully implemented and verified, not yet
committed.

## Completed this pass (uncommitted, on `feat/document-viewer`)

- `GET /workspaces/{id}/documents/{id}/chunks` (plural — ordered,
  additive to the existing single-chunk endpoint):
  `backend/app/api/v1/documents.py`,
  `document_service.list_document_chunks()`.
- Real `frontend/app/documents/[id]/page.tsx` (renders a document's
  full extracted content in order, `?chunk=` highlight-and-scroll-to),
  replacing the `PageStub`.
- Wired the chat citation chip (`CitationSource` in
  `app/chat/page.tsx`) with a "View in document" link.
- **Found and fixed a real gap via live-browser verification**: the
  Documents list page had no link from a filename to anything — the
  viewer was only reachable via a chat citation. Added a link from
  each row (`app/documents/page.tsx`).
- **Found and fixed a real robustness gap**: the highlight-and-scroll
  effect called `scrollIntoView()` unconditionally, which doesn't
  exist in jsdom (surfaced as a test crash) and isn't guaranteed in
  every environment — made it optionally-chained.
- Tests: 5 new backend (`tests/test_document_listing.py` — ordered
  chunks, empty list for an unprocessed document, not-found,
  cross-workspace isolation, VIEWER-can-list), 4 new frontend tests in
  a new `app/documents/[id]/page.test.tsx`; the chat-page and
  documents-list test files got new assertions added to existing
  tests (the "View in document" link's `href`, the filename link's
  `href`) rather than new test cases.
- `docs/API_CONTRACT.md`, `docs/REQUIREMENTS_MATRIX.md` §3, and
  `PROJECT_STATE.md` updated to record the document viewer as
  `COMPLETE` with evidence.

## Explicitly NOT done (do not assume otherwise)

- Items 4–7 above (regenerate/retry, document management, command
  palette, recursive chunking) — see `docs/REQUIREMENTS_MATRIX.md` for
  each one's acceptance criteria and planned next slice. None have any
  code yet.
- Search results (item 2) still don't link to the document viewer,
  even though the viewer now exists — noted in the matrix as a
  reasonable follow-up, not required by `docs/REQUIREMENTS.md` as
  written, and not done in this pass either (kept this slice focused
  on the viewer itself plus the chat citation link it was explicitly
  scoped for).
- Production hosting target remains undecided — see
  `docs/PRODUCTION_READINESS.md`; not this sprint's concern per
  `CLAUDE.md` §4.

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment.

## Tests run (this pass, on `feat/document-viewer`, after the document-viewer implementation)

- Backend: `uv run ruff check .` (clean), `uv run mypy .` — **the full
  CI command, not a narrower local approximation** (see `SOLVING.md`'s
  2026-10-23 "mypy app vs mypy ." entry for why this distinction now
  matters) — clean. `uv run pytest -q` — **772 passed, 1 skipped** (767
  baseline + 5 new).
- Frontend: `eslint` (clean), `tsc --noEmit` (clean), `vitest run` —
  **98/98 passed** (94 baseline + 4 new, all in the new
  `app/documents/[id]/page.test.tsx` file; the chat-page and
  documents-list additions extended two *existing* tests with new
  assertions rather than adding new `it()` cases, so they don't change
  the total), `next build` succeeds (17 routes, `/documents/[id]`
  dynamic).
- Playwright E2E, against a freshly `docker compose up --build -d`
  stack: **21/21 passed**, no regression.
- Real-browser verification beyond the automated suites (a standalone
  Playwright-core script): register → workspace → upload/process a
  document → **click it from the Documents list and see its real
  extracted content in the viewer** → ask a question in chat → open
  the citation → click "View in document" → land on the viewer with
  the cited chunk visibly highlighted. All 9 steps passed.

## Exact next recommended action

1. Provenance sweep (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   commit, push, open a PR referencing Issue #41, confirm CI green
   (run the literal CI commands locally first, not an approximation —
   see the mypy lesson above), merge.
2. Continue to item 4 (answer regeneration/retry) — the matrix already
   has the acceptance criteria and next-slice plan:
   `citation_repository.delete_for_message()` (new) →
   `conversation_service.regenerate_message()` (new — finds the
   preceding user message, re-runs the same
   `_run_retrieval_and_generation()` helper `post_message()` uses,
   replaces the assistant message's content/citations in place, clears
   any prior feedback) → `POST .../messages/{message_id}/regenerate`
   (MEMBER+, same rate limit as posting a message) → a "Regenerate"
   button on each assistant message in the chat UI → tests.
3. Continue through items 5–7 in the matrix's stated priority order,
   each as its own small, independently tested, separately merged PR.
   If the available time/effort doesn't cover all seven, update the
   matrix and this file to say exactly which remain, honestly.
