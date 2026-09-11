# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

Second-pass documentation and architecture consistency audit, and applying
its corrections. Documentation-only — no application code, dependencies,
schemas, Docker services, or GitHub issues were created.

## Completed work

- Read the complete documentation set plus `.env.example`, `.gitignore`,
  `.gitattributes`, and Git status/history, and audited it for internal
  consistency across 25 dimensions (requirements↔architecture,
  architecture↔security, provider abstractions, workspace isolation,
  auth/session assumptions, ingestion lifecycle, retrieval pipeline,
  citations, voice, observability, testing, scope creep, fabrication
  checks, etc.).
- Produced a full audit report: 0 CRITICAL / 2 HIGH / 5 MEDIUM / 4 LOW / 3
  SUGGESTION findings.
- Applied the corrections:
  - Added [ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md)
    resolving the "bearer tokens" vs. session/device-revocation
    contradiction: short-lived bearer access tokens backed by
    server-tracked refresh/session records in PostgreSQL — not purely
    stateless, no Redis. Updated `docs/API_CONTRACT.md`,
    `docs/DATA_MODEL.md` (promoted `sessions` to a core entity),
    `docs/SECURITY.md`, and `docs/ARCHITECTURE.md` to match.
  - Documented the rate-limiting approach (in-process/PostgreSQL-backed,
    no Redis for the initial implementation) in `docs/SECURITY.md` (new
    "Rate limiting approach" section) and `docs/ARCHITECTURE.md` — not
    implemented, documentation only.
  - Added `RERANKER_API_KEY=` to `.env.example` to match the six
    documented provider abstractions.
  - Added a target `/api/v1/workspaces/{workspace_id}/audit-logs`
    namespace (admin/owner-authorized) to `docs/API_CONTRACT.md`.
  - Documented chunking-strategy comparison as part of the evaluation
    framework in `docs/EVALUATION.md`, alongside the existing
    Dense/BM25/Hybrid/Hybrid+Reranker comparison.
  - Added `.gitattributes` to the target repository tree in
    `docs/ARCHITECTURE.md`.
  - Reworded `README.md`'s opening so "production-oriented" design intent
    can't be misread as a production-readiness claim, and moved the status
    disclaimer ahead of the description.
  - Documented the one-time Git-workflow bootstrap exception in
    `AGENTS.md` §6.
  - Made `docs/DECISIONS/` and `.agents/skills/` explicitly discoverable
    in `START_HERE.md`'s reading order and `README.md`'s documentation map.
  - Clarified in `PROJECT_STATE.md` that baseline issue numbers
    (`AGENTS.md` §9) are planning references only, not existing GitHub
    issues, and removed the confident `#4 = backend skeleton` mapping the
    audit flagged as unsupported.
  - Added a working-tree-vs-committed-state clarification to
    `PROJECT_STATE.md`, and restructured `CHANGELOG.md` into
    `[Unreleased — working tree]` vs. `[Unreleased — committed]` sections
    so uncommitted and committed history are never conflated.

## Remaining work

- Everything in `PROJECT_STATE.md` marked `PLANNED` — the entire
  application. Nothing beyond documentation exists.
- This documentation set (original initialization pass + audit
  corrections) is still uncommitted — see `git status`.
- GitHub issues have not been created.
- Implementation-detail items ADR 0003 explicitly leaves open: exact token
  lifetimes, refresh-token delivery mechanism, reuse-detection response,
  password hashing algorithm choice.

## Blockers

None.

## Tests run

Not applicable — no application code exists. Verification for this pass
was `git status`/`git diff` review plus targeted `grep` checks for
remaining contradictions (authentication, sessions, bearer tokens, rate
limiting, Redis, audit logs, chunking evaluation, production claims).

## Exact next recommended action

1. Review this corrected documentation set (original initialization +
   audit corrections, both still uncommitted) with the user/maintainer.
2. If approved, commit the full documentation baseline in one commit (or a
   small, logical set of commits), then create GitHub Issue #1 and #2 per
   `AGENTS.md` §9.
3. Do not begin backend/frontend implementation before that review and
   commit, per `START_HERE.md` §6.
