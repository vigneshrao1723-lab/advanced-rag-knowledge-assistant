# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

**2026-10-23 housekeeping note:** this file had drifted from its own
stated convention above — it had grown to ~4,700 lines of append-only
"Completed work (...)" sections dating back to the project's earliest
Redis/Issue #3 slices, all of which are already fully recorded in
`CHANGELOG.md` (dated, PR-referenced) and in Git history itself. It has
been compacted back down to current-state-only. If you need the detailed
history of any past slice/PR, read `CHANGELOG.md` or `git log`/`gh pr
list --state merged` — nothing below duplicates that.

---

## Current task

**"FINAL PROJECT HANDOFF + DEPLOYMENT READINESS" is complete.** `main`
is at `585722f` (PRs #37/#38/#39 all merged, Issues #1–#8 all closed).
This pass:

1. Ran a real 9-step Playwright browser demo (register → login → create
   workspace → upload → process to `READY` → ask a grounded question →
   open the citation's source inspection → feedback + rename + delete a
   conversation → logout → confirm `/dashboard` redirects to `/login`)
   and a separate real `curl`-based cross-workspace-isolation check
   (two users, three resource types, all correctly `404`). Both passed
   with real content assertions, not just HTTP 200.
2. Wrote `docs/PRODUCTION_READINESS.md` — what's verified locally, what
   genuinely isn't (backup/restore, object storage, multi-instance
   Redis coordination under real concurrent load, image registry,
   metrics/monitoring, CORS/cookie settings against a real cross-site
   target), security/operational risks, three hosting approaches with
   trade-offs (not a recommendation), the exact human decisions/
   credentials a real deployment needs, and a provider-neutral
   checklist. No hosting provider is chosen — that's explicitly a human
   decision per `CLAUDE.md` §4.
3. While verifying a specific claim in that document, found a real,
   evidenced local-dev defect: uploaded documents had no volume mount
   and did not survive a backend container recreation (unlike Postgres,
   which already had `db_data`). Fixed it — added `backend_documents`
   volume to `infra/compose/docker-compose.yml`, which then surfaced a
   second real bug (fresh named volumes default to root ownership,
   breaking the non-root `appuser` container) fixed in
   `infra/docker/backend.Dockerfile` by pre-creating the directory with
   correct ownership before `USER appuser`. Both verified against the
   real failure scenario (upload, then force-recreate, then confirm the
   file and its content survived) — see `SOLVING.md`'s 2026-10-23 entry
   for the full root-cause writeup.
4. Re-ran the full regression suite after the Docker/Dockerfile change
   (infra changes can plausibly affect anything storage-related) — see
   "Tests run" below.
5. Updated `docs/PRODUCTION_READINESS.md`, `PROJECT_STATE.md`, this
   file, and `CHANGELOG.md`/`SOLVING.md` to reflect the above.

## Completed this pass (uncommitted as of this entry)

- `infra/compose/docker-compose.yml` — added `backend_documents` named
  volume for `backend`'s `/app/data/documents`.
- `infra/docker/backend.Dockerfile` — pre-creates that directory,
  `appuser`-owned, before the volume is ever mounted.
- `docs/PRODUCTION_READINESS.md` — new file (production-readiness
  assessment; see "Current task" above).
- `SOLVING.md` — new entry: the volume-ownership/permission bug.
- `PROJECT_STATE.md`, this file, `CHANGELOG.md` — updated to match.

## Explicitly NOT done (do not assume otherwise)

Unchanged from the prior pass's audit — see `PROJECT_STATE.md`
"Immediate priorities" for the authoritative, currently-correct list:
collections, standalone search UI (`/search` is an honest `PageStub`),
command palette, a full in-document citation viewer with contextual
highlighting (`/documents/[id]` is an honest `PageStub`; source
inspection — viewing the exact cited chunk's text — *is* implemented),
regenerate/retry a response, document management beyond list/get/
upload/process, a `recursive` chunking strategy, and a decided
production hosting target. Verified again this pass (read each stub
page's actual source) that none of these have silently appeared.

The document-storage fix this pass is **local-dev only** — it does not
make documents durable on a real multi-instance or ephemeral-filesystem
production deployment (most container platforms give each instance its
own disposable filesystem; a Docker named volume isn't a concept there).
A real object-storage `StorageProvider` implementation is still unbuilt
— see `docs/PRODUCTION_READINESS.md` "No object storage."

## Blockers

None. `gh` CLI, Docker, and the full local stack are all working in
this environment.

## Tests run (this pass, after the Dockerfile/docker-compose.yml change)

- Backend: `uv run ruff check .` (clean, 99 files), `uv run mypy app`
  (clean, "no issues found"), `uv run pytest -q` — **744 passed, 1
  skipped** (the 1 skip is the `.env.example` regression test that only
  applies outside the Docker image's build context — expected, matches
  the documented baseline).
- Frontend: `eslint` (clean), `tsc --noEmit` (clean), `vitest run` —
  **82/82 passed**, `next build` (succeeds, all 17 routes build).
- Playwright E2E, against a freshly `docker compose up --build -d`
  stack: **21/21 passed**.
- Manual, real-infrastructure verification (not covered by the above
  suites): a real `curl` upload returned `201` and the file landed at
  the expected `/app/data/documents/<workspace_id>/<document_id>.txt`
  path, correctly `appuser`-owned; `docker compose up -d
  --force-recreate backend` followed by re-reading that same path
  confirmed the file and its exact content survived.

## Exact next recommended action

1. Provenance sweep (`git diff | grep -iE "claude|anthropic|co-authored|generated with"`),
   then commit the uncommitted changes listed above (infra fix +
   `docs/PRODUCTION_READINESS.md` as one commit, doc updates as
   another, or combined — whichever keeps the diff legible).
2. Push to a new branch, open a PR, confirm CI green (pay particular
   attention to the `docker-build` job, since this touches the backend
   Dockerfile/compose file — `docker compose config --quiet` has
   already been confirmed passing locally).
3. This is a small, well-tested, non-visual infra fix — consistent with
   this project's established autonomous-merge pattern (large/visually-
   risky design-pass PRs are left for explicit human review; small,
   well-tested, non-visual fixes are merged once CI is green). Merge,
   verify `main`, delete the branch (local + remote).
4. No further action is required on this project's documented
   requirements — Issues #1–#8 are closed, the deferred-feature list is
   accurate and unchanged, and the only remaining blocker to an actual
   production deployment is the set of human decisions listed in
   `docs/PRODUCTION_READINESS.md` (hosting provider/approach, object
   storage, secrets, SMTP, CORS/cookie settings, backup/restore,
   monitoring) — none of which this agent can or should decide
   unilaterally per `CLAUDE.md` §4.
