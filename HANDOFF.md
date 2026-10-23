# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Feature-completion sprint (Issue #41)** — bringing the product from
"core scope done" (Issues #1–#8, closed) to feature-complete against
`docs/REQUIREMENTS_MATRIX.md`'s seven remaining items, in priority order:

1. **Collections — done this pass, uncommitted.** See "Completed this
   pass" below.
2. Standalone search UI — not started.
3. Full document viewer + citation highlighting — not started.
4. Answer regeneration/retry — not started.
5. Document management beyond list/get/upload/process (delete/rename/
   download/filter) — not started.
6. Command palette — not started.
7. Recursive chunking strategy — not started.

`main` is at `faef86b` (PRs #37–#40 and #42 merged; #41 is the tracking
issue, still open). Work for item 1 is on branch `feat/collections`,
fully implemented and verified, not yet committed.

## Completed this pass (uncommitted, on `feat/collections`)

- `backend/alembic/versions/0010_add_collections.py`,
  `app/models/collection.py`, `app/models/collection_document.py`,
  `app/repositories/collection_repository.py`,
  `app/repositories/collection_document_repository.py`,
  `app/services/collection_service.py`, `app/api/v1/collections.py`,
  router registration, two new `AuditEvent` entries
  (`COLLECTION_CREATED`/`COLLECTION_DELETED`), a small addition to
  `document_repository.py` (`list_by_ids_for_workspace`).
- `frontend/lib/schemas.ts`/`api-client.ts` (Collection types + API
  client functions), `frontend/app/collections/page.tsx` (real list/
  create/delete, replacing the `PageStub`), `frontend/app/collections/[id]/page.tsx`
  (real detail: rename, delete, add/remove documents via a native
  `<select>`, replacing the `PageStub`), `components/layout/nav.tsx`
  (added the Collections link).
- Tests: `backend/tests/test_collections.py` (15 tests — creation,
  listing with document counts, workspace isolation, VIEWER-cannot-
  mutate, cross-workspace document-add rejection via 404, idempotent
  add, remove, update, delete without deleting the document itself),
  `frontend/app/collections/page.test.tsx` +
  `frontend/app/collections/[id]/page.test.tsx` (9 tests).
- `docs/REQUIREMENTS_MATRIX.md` §1 and `PROJECT_STATE.md` updated to
  record Collections as `COMPLETE` with evidence.

## Explicitly NOT done (do not assume otherwise)

- Items 2–7 above (search, document viewer, regenerate/retry, document
  management, command palette, recursive chunking) — see
  `docs/REQUIREMENTS_MATRIX.md` for each one's acceptance criteria and
  planned next slice. None have any code yet.
- The Collections UI does **not** add a "filter Documents by collection"
  control on the Documents page — the original acceptance criteria
  named this as optional, and it wasn't built; a collection's documents
  are browsed from the collection's own detail page instead. Documented
  as a deliberate, minor scope reduction in the matrix, not an
  oversight.
- Document delete still doesn't exist (item 5) — a document can only be
  removed *from a collection*, not deleted outright, today.
- Production hosting target remains undecided — see
  `docs/PRODUCTION_READINESS.md`; not this sprint's concern per
  `CLAUDE.md` §4.

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment.

## Tests run (this pass, on `feat/collections`, after the Collections implementation)

- Backend: `uv run ruff check .` (clean, 106 files), `uv run mypy app`
  (clean), `uv run pytest -q` — **759 passed, 1 skipped** (744 baseline
  + 15 new collection tests; the 1 skip is the documented `.env.example`
  host-only regression test).
- Frontend: `eslint` (clean), `tsc --noEmit` (clean), `vitest run` —
  **91/91 passed** (82 baseline + 9 new), `next build` succeeds (17
  routes, `/collections` static, `/collections/[id]` dynamic).
- Playwright E2E, against a freshly `docker compose up --build -d`
  stack: **21/21 passed** (no regression from the new feature).
- Real-browser verification beyond the automated suites (a standalone
  Playwright-core script, not part of the formal test suite): register
  → create workspace → upload a document → create a collection → open
  its detail page → add the document → **reload the page and confirm
  the association persisted** → remove the document → rename the
  collection → delete it. All 11 steps passed.

## Exact next recommended action

1. Provenance sweep (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   commit the Collections work on `feat/collections`, push, open a PR
   referencing Issue #41, confirm CI green (all 4 required jobs,
   including `docker-build` since a new migration is involved — Alembic
   upgrade/downgrade/upgrade was already verified locally against real
   Postgres), merge.
2. Update `docs/REQUIREMENTS_MATRIX.md`'s priority list to confirm item
   1 is done, then start item 2 (standalone search UI) — the matrix
   already has its acceptance criteria and next-slice plan written out:
   a retrieval-only (no generation) endpoint reusing
   `app/retrieval/service.py::hybrid_search()`, plus a real `/search`
   page replacing its `PageStub`.
3. Continue through items 3–7 in the matrix's stated priority order,
   each as its own small, independently tested, separately merged PR —
   do not batch multiple items into one PR. If the available time/
   effort doesn't cover all seven, update the matrix and this file to
   say exactly which remain, honestly, rather than implying more is
   done than actually is.
