# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Final release audit + production-deployment planning (Issue #50) —
complete, awaiting owner decisions.** Nothing was deployed, no cloud
resource, domain or credential was created.

- PR #51 (merged as `6a6e44e`): fixed two audit-found defects — non-Latin-1
  download filenames returned 500; filename filter treated `%`/`_` as LIKE
  wildcards.
- PR #52 (this branch, `chore/release-audit-eval-and-docs`): larger
  evaluation fixture + `--fixture large` runner mode + real results,
  `evidence_coverage_at_k`, doc corrections, sourced hosting comparison.
  If it is not yet merged, check `gh pr view 52` and CI before relying on it.

## Where things stand

- `main` was `6a6e44e` when #52 was opened. Recursive chunker is still
  evaluation-only; ingestion still uses `StructureAwareChunker`.
- Verified in the audit: backend 825 passed + 2 skipped (image), frontend
  113/113, Playwright 21/21, `ruff`/`mypy` clean, migration round trip OK,
  ~240 scripted HTTP checks + a 30-check headless-browser run (see
  `docs/PRODUCTION_READINESS.md` "Release audit" for what each covered).
- **Not production-ready** — see the checklist in
  `docs/PRODUCTION_READINESS.md`.

## Explicitly NOT done (do not assume otherwise)

- **Hosting target** — undecided. Recommendation (Option A, single
  DigitalOcean Droplet + Compose + Caddy, ≈₹1,370/mo estimate) is in
  `docs/PRODUCTION_READINESS.md`; it is the owner's call.
- **Relevance gate** (off-topic questions still get cited answers),
  **Redis-outage event-loop stall**, **lexical AND-semantics**, **security
  response headers** — verified, documented, deliberately not changed.
- A committed Playwright spec for the Issue #41 UI — see PROJECT_STATE's
  E2E row for why (registration rate limit) and how to do it safely.
- No real LLM / embedding model has ever been evaluated.

## Blockers

Owner decisions only (below). No technical blocker.

## Exact next recommended action

1. Merge PR #52 once its 4 required CI checks are green.
2. Owner: pick a hosting option (A/B/C) and a domain; then write the ADR.
3. Owner: decide whether to fix the relevance-gate finding first. Suggested
   approach: drop candidates with no content-word overlap with the query in
   `conversation_service` only (not in `hybrid_search()`, so search/eval
   are unchanged), with tests, behind an ADR since it touches the
   retrieval → generation boundary (`CLAUDE.md` §4).
4. Restore/keep local Compose as is: `docker compose -f
   infra/compose/docker-compose.yml up -d` (the original `compose` project
   was stopped, not removed, during the audit — its volumes are intact).
