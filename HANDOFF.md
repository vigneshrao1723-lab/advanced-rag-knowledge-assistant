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
6. **Command palette — done.** Merged as `f1426bc` (PR #48).
7. **Recursive chunking strategy — done this pass, uncommitted.** See
   "Completed this pass" below. **This is the last item.**

`main` is at `f1426bc`. Work for item 7 is on branch
`feat/recursive-chunking`, fully implemented and verified, not yet
committed.

## Completed this pass (uncommitted, on `feat/recursive-chunking`)

- `backend/app/ingestion/chunking.py` — new `RecursiveChunker` class
  implementing the existing `ChunkingStrategy` protocol: splits
  recursively by a fixed, universal separator priority list (paragraph
  → line → sentence → word → hard character cut), falling back to the
  next separator only when a piece still exceeds `max_chunk_size`.
  Deliberately document-type-agnostic — the distinguishing property
  versus `StructureAwareChunker`, which adapts its paragraph-detection
  heuristic per extractor. Still never merges across `ExtractedSection`s
  (the hard, non-negotiable rule every chunker obeys, since
  `document_chunks.page`/`.section` are singular columns). Sentence
  splitting uses a lookbehind regex (`(?<=[.!?])\s+`) so the terminal
  punctuation character is never consumed/lost. Greedy-packs pieces up
  to `target_chunk_size` with character-based overlap, carrying forward
  the same `buffer_is_pure_overlap` guard `StructureAwareChunker._pack()`
  already established (no chunk is ever emitted that's purely
  carried-forward overlap with no new content). Updated the module's
  `ChunkingStrategy` Protocol docstring (was stale) and `__all__`.
  Purely additive — `document_service.process_document()` is unchanged
  and still uses `StructureAwareChunker` exclusively.
- Tests: 15 new unit tests (`backend/tests/test_chunking.py`):
  paragraph/line/sentence/word/hard-cut fallback at each separator
  level, terminal-punctuation never dropped, no chunk exceeds
  `max_chunk_size`, overlap-tail appears in the next chunk, no
  pure-overlap-only chunk is ever emitted, determinism, never merges
  across sections, gapless zero-based indexes, empty-section/
  short-text edge cases, default-config behavior, protocol conformance,
  and a direct behavioral contrast against `StructureAwareChunker` on
  single-newline text.
- Wired `RecursiveChunker` into
  `eval/scripts/run_retrieval_evaluation.py`'s chunking-strategy
  comparison set (now 3 strategies × 4 retrieval methods = 12
  persisted `evaluation_runs`, up from 8) and actually re-ran it
  against real Postgres (host-run: `cd backend && DATABASE_URL=... uv
  run python ../eval/scripts/run_retrieval_evaluation.py`, pointed at
  the compose stack's exposed `localhost:5432`). Genuine, non-fabricated
  results recorded in `eval/results/retrieval_evaluation.json`: all
  three chunking strategies produce identical retrieval metrics on the
  eval fixture — the same honest artifact already documented for
  structure-aware vs. fixed-size (every fixture document is short
  enough to become exactly one chunk under any of the three chunkers,
  not a claim the chunkers are equivalent in general).
- `docs/EVALUATION.md`, `docs/REQUIREMENTS_MATRIX.md` §7, and
  `PROJECT_STATE.md` updated to record recursive chunking as
  `COMPLETE` with evidence, and to mark the feature-completion
  sprint's full 7-item scope as implemented (only the production
  hosting decision remains, and that's explicitly a human decision,
  not an implementation gap).
- No backend regression: full suite re-run clean before any doc
  updates — **812 passed, 1 skipped** (was 797; +15 matches the new
  tests exactly). No frontend change this slice.

## Explicitly NOT done (do not assume otherwise)

- This branch (`feat/recursive-chunking`) is not yet committed, pushed,
  or opened as a PR.
- Production hosting target remains undecided — see
  `docs/PRODUCTION_READINESS.md`; explicitly out of this sprint's scope
  per `CLAUDE.md` §4.
- GitHub Issue #41 has not yet been closed — do that only after this
  PR merges, per the established convention from Issues #1–#8's
  closure (a PR-referenced closing comment).

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment.

## Tests run (this pass, on `feat/recursive-chunking`)

- Backend: `uv run ruff check .` / `uv run mypy .` (the literal CI
  commands, run inside the rebuilt Docker image) both clean (162 source
  files). `uv run pytest -q` (full suite, inside Docker): **812
  passed, 1 skipped** — no regression (+15 over the 797 baseline,
  exactly matching the new recursive-chunker tests).
- Evaluation script: actually executed against real Postgres (host-run,
  `DATABASE_URL` pointed at the compose stack's published `5432` port);
  exit 0; 12 `evaluation_runs` persisted; `eval/results/
  retrieval_evaluation.json` rewritten with genuine numbers.
- Frontend: unchanged this slice — no new run needed (no frontend file
  touched).
- Playwright E2E: unchanged this slice — no new run needed.

## Exact next recommended action

1. Provenance sweep
   (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   commit (`backend/app/ingestion/chunking.py`,
   `backend/tests/test_chunking.py`,
   `eval/scripts/run_retrieval_evaluation.py`,
   `eval/results/retrieval_evaluation.json`, `docs/EVALUATION.md`,
   `docs/REQUIREMENTS_MATRIX.md`, `PROJECT_STATE.md`, `CHANGELOG.md`,
   this file), push, open a PR referencing Issue #41, confirm CI green,
   merge (small, well-tested, non-visual — consistent with this
   sprint's established autonomous-merge pattern for items 1–6).
2. **This is the last item in the feature-completion sprint's stated
   seven-item scope.** Once it merges: update `PROJECT_STATE.md`'s
   "main baseline" line and `CHANGELOG.md`'s entry with the real merge
   hash (move it from "working tree" to "committed"), consider closing
   GitHub Issue #41 with a PR-referenced closing comment (matching the
   established convention for Issues #1–#8), and deliver the final
   sprint-wide report: actual main commit/status; tracking issue and
   completed slices (all 7); features implemented with file/API/test
   evidence; the one deliberately-undecided item (production hosting);
   exact test counts and CI status; security and RAG regressions
   checked; the single highest-priority next action (most likely: get
   the production-hosting decision from the owner, since every other
   sprint item is now done).
