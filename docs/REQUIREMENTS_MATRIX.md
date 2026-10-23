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

**Status: MISSING.**

- **Evidence:** No `collections`/`collection_documents` table, model,
  migration, repository, service, or API route exists anywhere in
  `backend/app/`. `frontend/app/collections/page.tsx` and
  `collections/[id]/page.tsx` are `PageStub`s only.
  `docs/DATA_MODEL.md` already specifies the intended schema
  (`collections` workspace-scoped, `collection_documents` many-to-many
  join — both marked `PROPOSED`).
- **Acceptance criteria:** A user can create/rename/delete a collection
  within a workspace; add/remove documents from a collection; list a
  workspace's collections and a collection's documents; all operations
  enforce workspace role (`MEMBER`+ to mutate, `VIEWER`+ to read) and
  are workspace-scoped (cross-workspace access returns `404`, matching
  every other resource in this codebase). The Collections UI replaces
  its stub with real create/list/detail/delete, and the Documents page
  can optionally filter by collection.
- **Dependencies/risks:** None blocking — follows the exact same
  pattern as `Workspace`/`WorkspaceMember` (an owning entity + a
  role/membership-style join table). Low risk: purely additive schema,
  no change to existing tables.
- **Effort/priority:** Medium (new migration, model ×2, repository ×2,
  service, API routes, 2 frontend pages, nav entry, tests). **Priority
  1** (per the sprint's own stated order).
- **Next slice:** Migration + `Collection`/`CollectionDocument` models →
  repository/service/API (`POST/GET/PATCH/DELETE
  /workspaces/{id}/collections`, `POST/DELETE
  /workspaces/{id}/collections/{id}/documents/{document_id}`) → replace
  both frontend stubs → tests.

## 2. Standalone search UI

**Status: MISSING** (retrieval itself is real; there is no standalone,
non-chat entry point to it).

- **Evidence:** `app/retrieval/service.py::hybrid_search()` is real,
  tested, and already used by the chat flow
  (`conversation_service.py::_run_retrieval_and_generation`). No
  `/api/v1/search` or `/api/v1/workspaces/{id}/search` route exists —
  `grep` across `backend/app/api/v1/` confirms no `search` router.
  `frontend/app/search/page.tsx` is a `PageStub`.
- **Acceptance criteria:** A user can type a query and see ranked
  evidence snippets (document, page, section, score, retrieval method)
  **without** triggering generation — i.e. retrieval only, matching
  `docs/REQUIREMENTS.md` "Search" ("distinct from chat"). Loading,
  empty (no query yet), no-results, and error states. Each result links
  to the source document/chunk (reusing the existing source-inspection
  endpoint).
- **Dependencies/risks:** Low — this is largely a thin new endpoint
  wrapping the already-tested `hybrid_search()` plus a new page. Main
  design decision: whether to log search queries as a new
  `RetrievalEvent` (consistent with chat) — yes, for observability
  parity, reusing the existing table rather than inventing a new one.
- **Effort/priority:** Small-medium. **Priority 2.**
- **Next slice:** `GET /workspaces/{id}/search?q=...` (VIEWER+, calls
  `hybrid_search()` directly, no generation) → `/search` page (input,
  results list, states) → tests.

## 3. Full document viewer with contextual citation highlighting

**Status: PARTIAL** (source inspection exists; a document-wide viewer
does not).

- **Evidence:** `GET /workspaces/{id}/documents/{id}/chunks/{chunk_id}`
  (`backend/app/api/v1/documents.py:65-86`) and the frontend
  `CitationSource` component already let a user view **one cited
  chunk's** text in a `<blockquote>` from the chat page. There is no
  endpoint or page that renders a **whole document** with its chunks in
  order and highlights the cited one in context —
  `frontend/app/documents/[id]/page.tsx` is a `PageStub`.
- **Acceptance criteria:** Navigating to `/documents/[id]` (e.g. from a
  citation) renders the document's extracted content as ordered
  sections/chunks, scrolls to and visually highlights the chunk a
  citation pointed at, and works for every supported format's extracted
  text (PDF/DOCX/TXT/MD/CSV all go through the same `document_chunks`
  table, so one viewer design covers all of them — no per-format
  rendering needed, since this project never renders the original
  PDF/DOCX binary, only its extracted text, consistent with
  `docs/RAG_DESIGN.md`).
- **Dependencies/risks:** Needs a new endpoint returning a document's
  chunks in order (`GET /workspaces/{id}/documents/{id}/chunks`, plural
  — the existing singular one stays for the exact-chunk case). Low
  risk — read-only, additive.
- **Effort/priority:** Medium (new endpoint + a real page with
  highlight-and-scroll-to behavior + deep-linking from chat citations).
  **Priority 3.**
- **Next slice:** `GET .../documents/{id}/chunks` (ordered, VIEWER+) →
  `/documents/[id]` page (renders chunks, accepts a `?chunk=` query
  param to highlight/scroll) → wire the chat citation chip's "view in
  document" link → tests.

## 4. Answer regeneration/retry

**Status: MISSING.**

- **Evidence:** No `regenerate` concept anywhere in
  `backend/app/services/conversation_service.py` or
  `app/api/v1/conversations.py` (confirmed by reading both files in
  full). `docs/API_CONTRACT.md` explicitly documents this as "not yet
  implemented... deliberately deferred."
- **Acceptance criteria:** From an assistant message, a user can
  request regeneration; the system re-runs retrieval+generation for the
  same preceding user question and replaces that assistant message's
  content and citations with a fresh answer; any prior feedback on the
  old answer is cleared (it no longer describes the current content);
  a failure during regeneration leaves the prior answer intact (never
  deletes-then-fails). Workspace/role/IDOR tested like every other
  mutation in this codebase.
- **Dependencies/risks:** Needs to find "the preceding user message"
  for a given assistant message — straightforward via
  `created_at`/ordering within the same conversation, no schema change
  needed. Needs a citation-replacement path
  (`citation_repository` currently has no `delete_for_message` — must
  add one). Low risk otherwise; reuses the exact
  `_run_retrieval_and_generation()` helper `post_message()` already
  uses.
- **Effort/priority:** Small-medium (one new repository method, one new
  service function, one new endpoint, one new UI button). **Priority
  4** (explicit, deliberate reasoning in the existing docs for why this
  was deferred relative to effort — now in scope per this sprint).
- **Next slice:** `citation_repository.delete_for_message()` →
  `conversation_service.regenerate_message()` → `POST
  .../messages/{message_id}/regenerate` (MEMBER+, same rate limit as
  posting a message) → a "Regenerate" button on each assistant message
  in the chat UI → tests.

## 5. Document management beyond list/get/upload/process

**Status: PARTIAL.**

- **Evidence:** Upload/list/get/process exist
  (`backend/app/api/v1/documents.py`). **Retry-after-`FAILED` already
  works** — `document_service.py`'s `_REPROCESSABLE_STATUSES` includes
  `FAILED`, and `POST .../process` is the same endpoint used for both a
  first attempt and a retry; the frontend documents page already has a
  working "Retry" button (`frontend/app/documents/page.tsx:152-197`).
  **Missing:** delete, rename, download the original file, and any
  filter/sort/search over the document list (`list_documents()` takes
  no query parameters at all).
- **Acceptance criteria:** A user can delete a document (removing its
  `document_chunks` rows and its stored file via `StorageProvider`,
  and — since citations reference `document_id` — deciding and
  implementing a safe citation-on-delete policy: keep historical
  citations pointing at a now-deleted document rather than cascading
  message deletion, since a chat answer's history shouldn't disappear
  because its source document was later removed); rename a document's
  display name; download the original uploaded file; filter the
  document list by status and search by filename.
- **Dependencies/risks:** Delete is the one genuinely risk-bearing item
  here — it touches storage cleanup (`StorageProvider.delete()` doesn't
  exist yet either) and the citation foreign key's delete behavior
  needs an explicit, documented decision (not an unconsidered cascade).
  This is squarely an implementation decision, not an architectural one
  — no new infrastructure, no auth/isolation-model change — so it does
  not require owner sign-off under `CLAUDE.md` §4, but the exact
  citation-retention behavior should be stated plainly in
  `docs/API_CONTRACT.md` once built, not left implicit.
- **Effort/priority:** Medium (delete needs the most care; rename and
  download are small). **Priority 5.**
- **Next slice:** `StorageProvider.delete()` → `DELETE
  .../documents/{id}` (decide + implement the citation-retention
  policy) → `PATCH .../documents/{id}` (rename) → `GET
  .../documents/{id}/download` → UI buttons → tests.

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
