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
2. **Standalone search UI — done this pass, uncommitted.** See
   "Completed this pass" below.
3. Full document viewer + citation highlighting — not started.
4. Answer regeneration/retry — not started.
5. Document management beyond list/get/upload/process (delete/rename/
   download/filter) — not started.
6. Command palette — not started.
7. Recursive chunking strategy — not started.

`main` is at `06b8c9e`. Work for item 2 is on branch
`feat/standalone-search`, fully implemented and verified, not yet
committed.

## Completed this pass (uncommitted, on `feat/standalone-search`)

- `backend/app/api/v1/search.py`, `app/services/search_service.py`,
  `app/schemas/search.py`, router registration
  (`app/api/v1/router.py`), a new `search` rate-limit operation/
  dimension in `app/core/rate_limit.py`
  (`enforce_search_rate_limit()`, same Tier A shape as
  `conversation_message`).
- `frontend/lib/schemas.ts`/`api-client.ts` (Search types + API client
  function), `frontend/app/search/page.tsx` (real query/results page,
  replacing the `PageStub`), `components/layout/nav.tsx` (added the
  Search link).
- Tests: `backend/tests/test_search.py` (8 tests — ranked results with
  source info, empty-workspace, cross-workspace isolation, auth
  required, VIEWER-can-search, empty-query rejected, `RetrievalEvent`
  recorded with null conversation/message, rate limit enforced),
  `frontend/app/search/page.test.tsx` (3 tests).
- **Doc catch-up**: `docs/API_CONTRACT.md` and `docs/SECURITY.md` now
  document both the new search endpoint *and* collections (Issue #41
  priority 1) — the collections PR (#43) missed updating these two
  files; fixed in this pass rather than left stale.
- `docs/REQUIREMENTS_MATRIX.md` §2 and `PROJECT_STATE.md` updated to
  record standalone search as `COMPLETE` with evidence.

## Explicitly NOT done (do not assume otherwise)

- Items 3–7 above (document viewer, regenerate/retry, document
  management, command palette, recursive chunking) — see
  `docs/REQUIREMENTS_MATRIX.md` for each one's acceptance criteria and
  planned next slice. None have any code yet.
- Search results do **not** link to the source document/chunk yet —
  the document viewer (item 3) doesn't exist to link to. Each result
  shows filename/page/section/snippet as plain text. Revisit once item
  3 ships (documented in the matrix as a deliberate, minor
  simplification, not an oversight).
- Collections still don't filter retrieval/search to one collection —
  they're organization only today (see the matrix's item 1 note).
- Production hosting target remains undecided — see
  `docs/PRODUCTION_READINESS.md`; not this sprint's concern per
  `CLAUDE.md` §4.

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment. One CI run on PR #43 was unusually slow (an
`espeak-ng` apt install and a Playwright-browser-install step each
took several extra minutes) but passed cleanly — infra slowness that
day, not a regression; nothing to act on.

## Tests run (this pass, on `feat/standalone-search`, after the search implementation)

- Backend: `uv run ruff check .` (clean, 109 files), `uv run mypy app`
  (clean), `uv run pytest -q` — **767 passed, 1 skipped** (759 baseline
  + 8 new search tests; the 1 skip is the documented `.env.example`
  host-only regression test).
- Frontend: `eslint` (clean), `tsc --noEmit` (clean), `vitest run` —
  **94/94 passed** (91 baseline + 3 new), `next build` succeeds (17
  routes, `/search` static).
- Playwright E2E against a freshly `docker compose up --build -d`
  stack: **21/21 passed**, no regression (the formal suite doesn't
  cover search yet, since it predates this feature).
- Real-browser verification beyond the automated suites (a standalone
  Playwright-core script): register → workspace → upload and process a
  document → search for it by a relevant question → confirm the
  correct filename, a real content snippet, and a score are shown →
  search an unrelated/gibberish query → confirmed the retrieval module
  still returns that same document as the "best available" match
  rather than an empty result (expected — see the matrix's note on
  retrieval having no absolute relevance threshold, not a bug in this
  feature).

## Exact next recommended action

1. Provenance sweep (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   commit, push, open a PR referencing Issue #41, confirm CI green,
   merge (small, well-tested, non-visual-risk — consistent with this
   project's autonomous-merge pattern).
2. Continue to item 3 (full document viewer + citation highlighting) —
   the matrix already has its acceptance criteria and next-slice plan:
   a new `GET .../documents/{id}/chunks` (ordered, VIEWER+) endpoint,
   a real `/documents/[id]` page rendering chunks in order with
   highlight-and-scroll-to behavior, wired from chat citations (and,
   as a natural follow-up noted above, from search results too).
3. Continue through items 4–7 in the matrix's stated priority order,
   each as its own small, independently tested, separately merged PR.
   If the available time/effort doesn't cover all seven, update the
   matrix and this file to say exactly which remain, honestly.
