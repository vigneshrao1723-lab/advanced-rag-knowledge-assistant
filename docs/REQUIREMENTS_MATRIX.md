# Requirements Matrix — Remaining Product Scope

**Status:** living tracker. **Tracking issue:** [GitHub Issue #41](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/41)
("Feature completion sprint — Collections, Search, Document Viewer,
Regenerate, Document Management, Command Palette, Recursive
Chunking"). Issues #1–#8
are closed and cover the product's core, demonstrated scope (see
`PROJECT_STATE.md`) — this document and issue track the explicitly
deferred remainder named in `docs/REQUIREMENTS.md`/`docs/ARCHITECTURE.md`/
`docs/DATA_MODEL.md`/`docs/API_CONTRACT.md`.

This document records evidence, not opinion: every "Status" below is
backed by a concrete file/line reference or test result, re-verified by
reading the actual code — not inferred from a route name, a doc
aspiration, or a placeholder page's existence. A `PageStub` route or an
empty API surface is recorded as **MISSING**, never **PARTIAL** or
**COMPLETE**.

## Status legend

`MISSING` — no code implements this. `PARTIAL` — some real, working code
exists but the user-facing workflow is not complete end-to-end.
`COMPLETE` — the user-facing workflow works end-to-end, tested.
`BLOCKED` — requires an owner decision before implementation can proceed.

---

## 1. Collections

**Status: COMPLETE.**

- **Evidence:** `backend/alembic/versions/0010_add_collections.py`
  (`collections`/`collection_documents`, verified
  upgrade/downgrade/upgrade round-trip against real Postgres),
  `app/models/collection.py`, `app/models/collection_document.py`,
  `app/repositories/collection_repository.py`,
  `app/repositories/collection_document_repository.py`,
  `app/services/collection_service.py`,
  `app/api/v1/collections.py` (list/create/get/update/delete +
  add/remove document, all workspace-role-gated and workspace-scoped —
  cross-workspace access returns `404`, verified by test). 15 new
  backend tests (`backend/tests/test_collections.py`): creation,
  listing with document counts, workspace isolation, VIEWER-cannot-
  mutate, cross-workspace document-add rejection, idempotent add,
  remove, update, delete (and that deleting a collection does not
  delete its documents). `frontend/app/collections/page.tsx` and
  `collections/[id]/page.tsx` are real pages (create/list/rename/
  delete, add/remove documents via a native `<select>`), replacing
  both `PageStub`s; added to `components/layout/nav.tsx`. 9 new
  frontend tests. **Verified end-to-end in a real browser** (not just
  unit tests): register → create workspace → upload a document →
  create a collection → open its detail page → add the document →
  reload the page and confirm the association persisted → remove the
  document → rename the collection → delete it — all 11 steps passed
  against the real running stack.
- **Acceptance criteria:** met — see evidence above.
- **Dependencies/risks:** None encountered. Document delete (item 5,
  still `PARTIAL`) does not yet exist, so a collection's documents can
  only currently be removed from the *collection*, not deleted outright
  — no change needed here when that lands, since `collection_documents`
  rows cascade-delete via `ON DELETE CASCADE` on `document_id`
  automatically.
- **Effort/priority:** Delivered. Was **Priority 1** in the sprint's
  stated order.
- **Next slice:** none — done. (The Documents page filtering by
  collection, mentioned in the original acceptance criteria as
  optional, was not built — collections are browsed from their own
  page today, not as a Documents-page filter. This is a genuine, minor
  scope reduction from the original criteria, not an oversight: nothing
  in `docs/REQUIREMENTS.md` requires it specifically, and the
  collection detail page already shows a collection's documents.)

## 2. Standalone search UI

**Status: COMPLETE.**

- **Evidence:** `GET /workspaces/{id}/search?q=...` (VIEWER+,
  `backend/app/api/v1/search.py`, `app/services/search_service.py`) —
  calls `hybrid_search()` directly, never `app.generation`, and records
  a `RetrievalEvent` with `conversation_id`/`message_id` both `null`.
  Rate-limited (`enforce_search_rate_limit()`, same Tier A shape as
  `conversation_message`). Real `frontend/app/search/page.tsx` (query
  input, loading/error/empty/no-results states, ranked result list with
  filename, page/section, score, snippet), replacing the `PageStub`;
  added to the nav. 8 new backend tests (ranked results with source
  info, empty-workspace, cross-workspace isolation, auth-required,
  VIEWER-can-search, empty-query-rejected, `RetrievalEvent` recorded
  with null conversation/message, rate limit enforced), 3 new frontend
  tests. `docs/API_CONTRACT.md`/`docs/SECURITY.md` updated with the new
  endpoint's contract and isolation/rate-limit evidence (also backfilled
  the same for item 1/Collections, missed in that PR).
- **Acceptance criteria:** met — see evidence above. One minor
  deliberate simplification: results don't yet link to the source
  document/chunk, since the document viewer (item 3, still `PARTIAL`)
  doesn't exist yet to link to; the result card shows filename/page/
  section/snippet as plain text instead. Revisit once item 3 ships.
- **Dependencies/risks:** None encountered. One behavior worth noting
  explicitly, verified via a live-browser check, not assumed: dense/
  lexical retrieval (`app/retrieval/dense.py`/`lexical.py`) has no
  absolute relevance threshold — it always returns the top-K
  *best-available* matches, even for a query unrelated to every
  document in the workspace, if at least one `READY` document exists.
  The "no results" empty state is correctly reachable (and tested —
  `test_search_with_no_documents_returns_empty_results`), but only when
  a workspace has zero `READY` documents, not merely "no good
  conceptual match" — this is a pre-existing property of the retrieval
  module this feature reuses unchanged, not a defect introduced here.
- **Effort/priority:** Delivered. Was **Priority 2**.
- **Next slice:** none for the core feature. Once item 3 (document
  viewer) exists, consider linking each result to its source chunk in
  context — not required by `docs/REQUIREMENTS.md` "Search" as written,
  but a natural follow-up.

## 3. Full document viewer with contextual citation highlighting

**Status: COMPLETE.**

- **Evidence:** `GET /workspaces/{id}/documents/{id}/chunks` (plural,
  VIEWER+, `backend/app/api/v1/documents.py`,
  `document_service.list_document_chunks()`) returns every chunk of a
  document in `chunk_index` order — additive to, never replacing, the
  existing singular per-chunk source-inspection endpoint. Real
  `frontend/app/documents/[id]/page.tsx` renders a document's full
  extracted content block-by-block (page/section labels + text),
  replacing the `PageStub`; accepts a `?chunk=` query param to highlight
  and scroll to a specific chunk. The Documents list page
  (`app/documents/page.tsx`) now links each filename to its viewer —
  this link didn't exist before this slice and was found missing only
  by actually clicking through the feature in a real browser, not by
  code review alone. The chat citation chip (`CitationSource` in
  `app/chat/page.tsx`) now has a "View in document" link to
  `/documents/{document_id}?chunk={chunk_id}`, built from
  `CitationRead.document_id`/`chunk_id`. 5 new backend tests
  (`tests/test_document_listing.py`: ordered chunks, empty list for an
  unprocessed document, not-found, cross-workspace isolation,
  VIEWER-can-list), 4 new frontend tests in a new
  `app/documents/[id]/page.test.tsx` (renders chunks in order,
  processing message when empty, 404 for a missing document,
  highlights the `?chunk=` target); the chat-page and documents-list
  test files got new assertions added to existing tests (the "View in
  document" link's `href`, the filename link's `href`) rather than new
  test cases. **Verified
  end-to-end in a real browser**, not just unit tests: upload a
  document → open it from the Documents list and see its real extracted
  content → ask a question in chat → open the citation → click "View in
  document" → land on the viewer with the cited chunk visibly
  highlighted.
- **Acceptance criteria:** met — see evidence above. Works identically
  for every supported format since all go through the same
  `document_chunks` table (no per-format rendering needed — this
  project never renders the original PDF/DOCX binary, only its
  extracted text, consistent with `docs/RAG_DESIGN.md`).
- **Dependencies/risks:** None encountered, beyond the Documents-list
  linking gap caught during live verification (fixed in this same
  slice, not deferred).
- **Effort/priority:** Delivered. Was **Priority 3**.
- **Next slice:** none. A natural follow-up once item 2 (search, done)
  and this item are both complete: link each search result to its
  source chunk the same way citations do — noted in item 2's own entry,
  not required by `docs/REQUIREMENTS.md` as written.

## 4. Answer regeneration/retry

**Status: COMPLETE.**

- **Evidence:** `POST /workspaces/{id}/conversations/{id}/messages/{id}/regenerate`
  (MEMBER+, `backend/app/api/v1/conversations.py`,
  `conversation_service.regenerate_message()`) — finds the preceding
  `USER` message (`message_repository.get_preceding_user_message()`,
  new), re-runs the exact same `_run_retrieval_and_generation()` helper
  `post_message()` uses, then replaces the assistant message's content
  in place (`message_repository.update_content()`, new — same row, no
  new message, clearing any prior feedback) and its citations
  (`citation_repository.delete_for_message()`, new, called immediately
  before `bulk_create()` persists the fresh ones, both within the same
  transaction as the content update — a failure during generation
  happens *before* either delete/update call, so the prior answer is
  never touched on failure). Same rate limit as posting a message
  (`conversation_message` operation). A "Regenerate" button
  (`RotateCcw` icon) on each assistant message in
  `frontend/app/chat/page.tsx`. 8 new backend tests
  (`tests/test_conversations.py`: fresh grounded answer + citations
  with the message id/history-length unchanged, feedback cleared,
  regenerating a `USER` message is `404`, nonexistent message `404`,
  cross-workspace `404`, VIEWER `403`, unauthenticated `401`, rate
  limit enforced), 1 new frontend test. **Verified end-to-end in a real
  browser**: ask a question → rate the answer → click Regenerate →
  confirm the answer is still grounded in the real document and the
  prior rating was cleared.
- **Acceptance criteria:** met — see evidence above.
- **Dependencies/risks:** One real test-environment gotcha hit and
  fixed, not a production bug: within a single test's shared Postgres
  transaction, `created_at`'s `now()` default is frozen for the whole
  transaction, so the user/assistant messages `_post_message()` creates
  moments apart tied on `created_at`, which broke
  `get_preceding_user_message()`'s strict `<` comparison in tests (and,
  separately, revealed that relying on list *position* rather than
  *role* to pick "the user message" in an older sibling test pattern is
  fragile under the same tie). Fixed by forcing a distinct earlier
  timestamp in the affected tests, matching
  `test_document_listing.py`'s established precedent for this exact
  class of issue — real, separate HTTP requests in production get
  genuinely distinct transaction timestamps; only the shared-transaction
  test fixture ties them.
- **Effort/priority:** Delivered. Was **Priority 4**.
- **Next slice:** none.

## 5. Document management beyond list/get/upload/process

**Status: COMPLETE.**

- **Evidence:** `PATCH`/`DELETE`/`GET .../download` on
  `/workspaces/{id}/documents/{id}` (`backend/app/api/v1/documents.py`,
  `document_service.rename_document()`/`delete_document()`/
  `download_document()`), plus `GET .../documents?status=...&q=...`
  filter/search (`document_repository.list_for_workspace()` extended
  with optional `status`/`filename_query` params, backward-compatible
  with every existing caller). Retry-after-`FAILED` already worked
  before this slice (`_REPROCESSABLE_STATUSES` includes `FAILED`) —
  not new scope, just confirmed still correct. Real UI: rename
  (inline, Pencil icon), delete (Trash2 icon + confirm), download
  (native `<a download>`, no JS fetch/blob dance needed), a filename
  search box, and a status `<select>` on
  `frontend/app/documents/page.tsx`. 17 new backend tests
  (`tests/test_document_management.py`: rename/delete/download each
  with not-found/cross-workspace/VIEWER-role checks, an empty-filename
  rejection, a header-injection-sanitization check, status-filter and
  filename-search checks, and — the most important one — a direct
  verification that deleting a document cascades its chunks/citations
  but a chat message's own text content survives unaffected), 5 new
  frontend tests. **Verified end-to-end in a real browser**: upload →
  rename → search by the new name → filter by status → download
  (confirmed real byte-for-byte content) → delete → confirm back to
  the empty state.
- **Acceptance criteria:** met — see evidence above, including the
  citation-retention decision below.
- **Citation-retention decision, made and documented, not left
  implicit** (`docs/API_CONTRACT.md`'s "Document delete" section): on
  closer inspection of the real schema (not assumed from this item's
  own earlier, pre-implementation note above), `citations.document_id`
  and `citations.chunk_id` already have `ON DELETE CASCADE` — deleting
  a document removes its chunks, and removes any citation rows that
  pointed at those chunks. **Chat message *content* is never affected
  either way** — there is no foreign key from `messages` to `documents`
  at all, so this was never actually a risk to message history, only
  to citation *rows*. Keeping a citation alive after its source
  document and chunk are both gone would only produce a dead UI
  element (nothing left to view), so the existing cascade was kept
  rather than migrating two foreign keys to `SET NULL` for no real
  benefit. Directly tested:
  `test_delete_document_cascades_chunks_and_citations_but_preserves_message_content`.
- **Dependencies/risks:** None encountered.
  `StorageProvider.delete()` turned out to already exist (declared on
  the `Protocol` and implemented by `LocalStorage` since Issue #3) —
  this item's own earlier note assumed otherwise without checking.
- **Effort/priority:** Delivered. Was **Priority 5**.
- **Next slice:** none.

## 6. Command palette

**Status: MISSING.**

- **Evidence:** No `cmdk` dependency in `frontend/package.json`, no
  component matching `CommandPalette`/`command-palette` anywhere in
  `frontend/` (confirmed by `grep`). `docs/ARCHITECTURE.md` specifies
  `Ctrl+K` with actions: open document, new chat, search, switch
  workspace, evaluations, settings.
- **Acceptance criteria:** `Ctrl+K`/`Cmd+K` opens a searchable palette
  listing the actions above; works from any authenticated page;
  keyboard-navigable (arrow keys + Enter), closes on `Escape` or an
  outside click/selection; has a visible, accessible trigger as well
  (not keyboard-shortcut-only, for discoverability and
  non-keyboard/mobile users); does not trap focus incorrectly or break
  existing page keyboard shortcuts (e.g. the chat composer).
  Correctness of each action depends on items 1/2 above already
  existing (e.g. "search" as a palette action only makes sense once
  `/search` is real) — so this is sequenced after them.
- **Dependencies/risks:** Purely additive frontend work, zero backend
  change, zero risk to existing RAG/auth correctness. The only real
  risk is a global keyboard-shortcut listener interfering with existing
  input fields (the chat composer, auth forms) — must be scoped to not
  fire while a text input/textarea already has focus for a conflicting
  key, and tested for that explicitly.
- **Effort/priority:** Small (self-contained, no backend). **Priority 6**
  (explicitly sequenced last among the frontend items since several of
  its actions depend on 1–3 existing first).
- **Next slice:** add a small, dependency-free or `cmdk`-based palette
  component → wire the actions that already exist today (new chat,
  switch workspace, settings, documents) → extend with search/
  evaluations links once those slices land → tests (keyboard nav,
  focus-trap-avoidance, accessible labels).

## 7. Recursive chunking strategy

**Status: PARTIAL** (the extensibility point exists; the strategy does
not).

- **Evidence:** `backend/app/ingestion/chunking.py` defines
  `ChunkingStrategy` as a `Protocol` (line 163) specifically so a future
  strategy can be swapped in without changing callers, and already has
  two concrete implementations: `StructureAwareChunker` (the real
  pipeline's strategy) and `FixedSizeChunker` (an evaluation-comparison
  baseline only, used by `eval/scripts/run_retrieval_evaluation.py`,
  never by the production ingestion pipeline). No `RecursiveChunker` or
  anything matching `recursive` as a class exists (confirmed by
  `grep -rn "recursive" backend/app/` returning only the `Protocol`
  docstring's forward-reference comment).
- **Acceptance criteria:** A `RecursiveChunker` implementing the same
  `ChunkingStrategy` protocol — splits recursively by a prioritized
  list of separators (e.g. section → paragraph → sentence → word),
  falling back to the next separator only when a piece still exceeds
  the configured chunk size, matching the common "recursive character
  splitting" definition `docs/RAG_DESIGN.md` names it alongside
  fixed-size/structure-aware. Deterministic (same input/config →
  byte-identical output, matching `StructureAwareChunker`'s own tested
  guarantee). Preserves the same `Chunk` metadata shape
  (`chunk_index`/`page`/`section`/`content`). Added to the evaluation
  script's comparison set (now 3 strategies) so its retrieval quality
  is measured, never asserted without a real run.
- **Dependencies/risks:** None blocking. Purely additive — does not
  change the production pipeline's default strategy
  (`StructureAwareChunker` stays the default; this is a new, selectable
  option, not a replacement). Risk is isolated to getting the
  recursive-split boundary logic correct and genuinely deterministic,
  verified by tests, same as the existing chunkers.
- **Effort/priority:** Small-medium (one new class + tests + an
  evaluation-script wiring change; no schema/migration/API change
  needed since chunking strategy is an internal pipeline detail today,
  not a per-document user choice). **Priority 7** (explicitly last —
  lowest user-facing value of the seven, as it's an internal
  evaluation/architecture completeness item, not a visible product
  feature).
- **Next slice:** `RecursiveChunker` class + unit tests (determinism,
  boundary cases) → add to
  `eval/scripts/run_retrieval_evaluation.py`'s strategy set → re-run the
  real evaluation and record genuine (not fabricated) comparative
  numbers in `eval/results/` → update `docs/EVALUATION.md`.

## 8. Production deployment

**Status: BLOCKED on an owner decision** — correctly so, not a gap to
close by this agent. See `docs/PRODUCTION_READINESS.md` in full for the
verified-vs-unverified breakdown, hosting-approach trade-offs, and the
exact human decisions/credentials needed. Nothing in this sprint should
select a paid provider, provision paid infrastructure, or invent
production credentials — per `CLAUDE.md` §4 and this master prompt's own
Phase 5 instruction. This item's "next slice" is a human decision
recorded as a new ADR, not code.

---

## Priority order for Phase 3 (unchanged from the sprint's own ordering,
validated against the above — no dependency forces a reordering)

1. Collections
2. Standalone search
3. Full document viewer + citation highlighting
4. Answer regeneration/retry
5. Missing document-management operations
6. Command palette
7. Recursive chunking

## How to keep this matrix honest

Update the relevant section's Status/Evidence the moment a slice's PR
merges — cite the real file/endpoint/test, not an intention. Never move
an item to `COMPLETE` because a page or route exists; it must be a
working, tested, end-to-end user workflow. See `PROJECT_STATE.md` for
the condensed current-state table this matrix feeds into once each item
ships.
