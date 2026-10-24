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
   done this pass, uncommitted.** See "Completed this pass" below.
6. Command palette — not started.
7. Recursive chunking strategy — not started.

`main` is at `6822b76`. Work for item 5 is on branch
`feat/document-management`, fully implemented and verified, not yet
committed.

## Completed this pass (uncommitted, on `feat/document-management`)

- `PATCH`/`DELETE`/`GET .../download` on
  `/workspaces/{id}/documents/{id}`
  (`document_service.rename_document()`/`delete_document()`/
  `download_document()`), plus `?status=`/`?q=` filter/search on the
  list endpoint. `document_repository.rename()`/`delete()` (new);
  `list_for_workspace()` extended with optional, backward-compatible
  `status`/`filename_query` params. `StorageProvider.delete()` already
  existed — didn't need to be built. Delete removes the database row
  first, then best-effort-deletes the storage file (logged on
  failure, never surfaced as a user-facing error). Download's
  `Content-Disposition` filename is sanitized (CR/LF/`"` stripped) —
  the first endpoint in this API to put user-controlled text directly
  into a response header.
- **Citation-retention decision, made and documented**:
  `citations.document_id`/`chunk_id` already have `ON DELETE CASCADE`
  — deleting a document removes its chunks and any citations pointing
  at them. Kept as-is rather than migrating two foreign keys: a
  citation to a now-gone document/chunk would only be dead UI, and
  chat message *content* was never at risk either way (no FK from
  `messages` to `documents` exists at all). Full reasoning in
  `docs/API_CONTRACT.md`'s new "Document delete" section.
- Real rename (inline)/delete (confirm)/download (`<a download>`)
  controls plus a filename-search box and a status `<select>` on
  `frontend/app/documents/page.tsx`.
- Tests: 17 new backend (`tests/test_document_management.py` —
  rename/delete/download each with not-found/cross-workspace/
  VIEWER-role checks, empty-filename rejection, header-injection
  sanitization, status-filter/filename-search checks, and a direct
  cascade-vs-message-content verification), 5 new frontend.
- **Found and fixed a real regression in the formal Playwright
  suite** (not just my own new tests): the status-filter `<select>`'s
  `<option>READY</option>` collided with
  `e2e/documents-chat.spec.ts`'s existing `page.getByText("READY")` —
  a strict-mode violation. Fixed by scoping that query to the document
  row.
- `docs/API_CONTRACT.md`, `docs/SECURITY.md`,
  `docs/REQUIREMENTS_MATRIX.md` §5, and `PROJECT_STATE.md` updated to
  record document management as `COMPLETE` with evidence.

## Explicitly NOT done (do not assume otherwise)

- Items 6–7 above (command palette, recursive chunking) — see
  `docs/REQUIREMENTS_MATRIX.md` for each one's acceptance criteria and
  planned next slice. Neither has any code yet.
- Production hosting target remains undecided — see
  `docs/PRODUCTION_READINESS.md`; not this sprint's concern per
  `CLAUDE.md` §4.

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment.

## Tests run (this pass, on `feat/document-management`, after the document-management implementation)

- Backend: `uv run ruff check .` (clean, 162 files), `uv run mypy .`
  (the literal CI command) clean. `uv run pytest -q` — **797 passed,
  1 skipped** (780 baseline + 17 new).
- Frontend: `eslint` (clean), `tsc --noEmit` (clean), `vitest run` —
  **104/104 passed** (99 baseline + 5 new document-management tests;
  two pre-existing tests in this file needed a query-scope fix for the
  new status-filter `<select>`'s "READY" option, not a count change).
  `next build` succeeds (17 routes).
- Playwright E2E, against a freshly `docker compose up --build -d`
  stack: **21/21 passed** — only after fixing the real
  `documents-chat.spec.ts` regression described above; it failed
  before that fix.
- Real-browser verification beyond the automated suites (a standalone
  Playwright-core script): register → workspace → upload → rename →
  search by the new name (and confirm a no-match search shows the
  right empty state) → filter by status (both a match and a
  non-match) → download (confirmed real byte-for-byte file content,
  not just a 200) → delete → confirm back to the empty state. All 10
  steps passed.

## Exact next recommended action

1. Provenance sweep (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   commit, push, open a PR referencing Issue #41, confirm CI green
   (run the literal CI commands locally first), merge.
2. Continue to item 6 (command palette) — the matrix already has the
   acceptance criteria and next-slice plan: a `Ctrl+K`/`Cmd+K`-
   triggered palette (plus a visible, accessible trigger for
   discoverability) with actions that already exist today (new chat,
   switch workspace, settings, documents, collections, search) —
   purely frontend, zero backend change. Must be scoped to not fire
   while a text input/textarea already has focus (the chat composer,
   auth forms) — test that explicitly.
3. Then item 7 (recursive chunking) — a new `RecursiveChunker` class
   implementing the existing `ChunkingStrategy` protocol
   (`backend/app/ingestion/chunking.py`), added to
   `eval/scripts/run_retrieval_evaluation.py`'s comparison set, with a
   real (never fabricated) evaluation re-run recorded in
   `eval/results/`.
4. Each as its own small, independently tested, separately merged PR.
   After item 7, the matrix's full seven-item scope is done — give a
   final report covering all of it, not just the last slice.
