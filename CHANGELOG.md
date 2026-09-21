# CHANGELOG.md

All notable changes to this project are recorded here, in chronological
order. Entries under **[Unreleased — working tree]** describe changes made
locally that have **not yet been committed** (see `git status`) — logged
honestly as such, not backdated to look committed. Entries under
**[Unreleased — committed]** are real commits, referenced by hash, that
haven't been part of a tagged release yet. This file is never backfilled
with invented history of either kind.

## [Unreleased — working tree]

### 2026-09-21 — Document upload API (Issue #3, Slice 3.3)

- **Not committed.** `POST /api/v1/workspaces/{workspace_id}/documents`
  (`multipart/form-data`, field `file`) — authenticate, authorize
  (MEMBER, via the existing `require_workspace_role`), rate-limit,
  validate, checksum, check for a workspace-scoped duplicate, write to
  `StorageProvider`, create the `documents` row, emit the audit event,
  commit, return `201`. The document stays in `UPLOADED` — no
  extraction, chunking, embedding, or background processing.
- `backend/app/services/document_service.py` (new): validation
  (extension allowlist, MIME allowlist including named browser variants
  for `.md`/`.csv`, a magic-byte signature check for PDF/DOCX — no
  reliable signature exists for the plain-text formats, a documented
  gap, not a hidden one); a streamed, chunked checksum/size-limit reader
  that aborts before buffering an oversized payload; storage-key
  generation from trusted identifiers only, never the client filename.
  Storage-then-database ordering: the file always durably exists before
  any DB row is attempted; if the insert then fails for any reason
  (including a race-lost duplicate-checksum insert the pre-check missed),
  a best-effort compensating `storage.delete()` runs, logged if it also
  fails, never masking the original error. Duplicate uploads in the same
  workspace return `409` referencing the existing document's id; the
  same checksum in a different workspace is unaffected.
- `backend/app/repositories/document_repository.py`,
  `backend/app/schemas/document.py` (new, small, following the existing
  patterns exactly — `DocumentRead` never includes `storage_key`).
- `backend/app/core/audit.py`: additive `AuditEvent.DOCUMENT_UPLOADED`.
- `backend/app/core/rate_limit.py`: additive `document_upload` operation
  (IP + authenticated user ID, 20/60s, Tier A — falls back on a Redis
  outage, never fails open; the R1–R5 abuse-decision layer is not
  consulted, since its rule table targets a different threat model).
- `backend/app/core/config.py`: additive `max_upload_size_bytes`
  (default 50 MiB). New dependency: `python-multipart` (required by
  FastAPI for any file-upload route).
- `backend/app/api/v1/documents.py` (new) + router registration.
- `backend/tests/test_document_service.py` (new, 37 unit tests, no
  database) and `backend/tests/test_document_upload.py` (new, 30
  HTTP-level tests, real Postgres/Redis/filesystem, no mocks) — covering
  authentication/authorization/cross-workspace isolation, every
  supported format, unsupported extension/MIME/signature mismatches,
  the size limit, checksum correctness, path-traversal-filename safety,
  the audit event, duplicate-checksum handling (same and different
  workspace), a genuine storage failure, a genuine database failure
  (FK violation) after a successful storage write with compensating
  cleanup, a genuine race-lost duplicate insert, cleanup-failure
  path-leak safety, malformed multipart input, and real-Redis rate-limit
  key creation/enforcement/fallback.
- `docs/API_CONTRACT.md`: the `/api/v1/workspaces/{workspace_id}/documents`
  contract filled in (correcting the "Target namespaces" table's earlier
  flat, non-binding `/api/v1/documents` sketch to the nested path
  actually used, matching `/members`/`/audit-logs`'s existing
  convention). `docs/SECURITY.md`: "Upload & document safety" extended;
  "Audit logging" and "Security testing" bullets updated from their
  previous "not implemented yet" state.
- `ruff`/`mypy` clean (94 source files). **67/67 new tests passing**;
  the complete backend suite **361/361 passing** (294 pre-existing + 67
  new), **3 consecutive runs**, no regression in any existing test.
  Frontend re-confirmed unaffected (48/48 vitest, lint/typecheck clean).
  A full manual smoke test against the real Docker Compose stack
  (register → create workspace → upload a real PDF) succeeded
  end-to-end, including verifying the file landed at the correct path
  inside the running container.

### 2026-09-20 — Abuse-protection Slice 3c: escalation audit emission + HTTP-level tests

- **Not committed.** Adds abuse-escalation audit emission on top of
  Slice 3b's now-merged decision engine (`42529e3`, PR #14) — no
  production abuse-decision code modified, only consumed via
  `AbuseRecordOutcome`'s existing return value.
- `backend/app/core/audit.py`: one additive constant,
  `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` — no existing constant or
  the `record()` function's signature changed.
- `backend/app/api/v1/auth.py`: a new `_audit_abuse_escalation()` helper
  called from `login`/`forgot-password`/`reset-password` right after
  each `record_login_failure()`/`record_forgot_password_request()`/
  `record_reset_validation_failure()` call. Fires exactly once per
  escalation (`outcome.newly_escalated`) — never on an already-escalated
  repeat, never for an ordinary `ALLOW`. Emits `AuditEvent.RATE_LIMITED`
  for a `STRICT_THROTTLE` transition or `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED`
  for a `TEMPORARY_BLOCK` transition, with metadata limited to
  `rule`/`operation`/`dimension`, the already-HMAC-hashed `account_hash`
  when account-scoped, and `block_ttl_seconds` for blocks — never a raw
  email, password, or token. `user_id` is always `None` (genuinely
  unavailable at this layer in all three call sites, never invented).
  `ip_address` is the same trusted-proxy-resolved value the abuse
  decision itself acted on.
- `backend/tests/test_abuse_audit.py` (new, 6 HTTP-level tests, real
  Redis + real PostgreSQL, no mocks): R1 strict-throttle with exactly
  one audit row and strict-bucket consumption proof; account-scoped R2
  through the endpoint with isolation; R3's 5-distinct-IP temporary
  block with audit row, TTL metadata, and outright post-block rejection;
  R4 forgot-password strict-throttle with enumeration resistance intact;
  R5 reset-password validation-failure block; successful-login reset
  behavior with zero abuse-audit rows from an ordinary sequence. Two
  test-design bugs (not production defects) were found and fixed during
  this slice's own validation: an initial attempt to pre-fill the base
  `rl:*` bucket with abundant tokens doesn't work (the Lua script always
  clamps effective tokens at the dimension's configured capacity,
  regardless of stored value) — fixed by pre-seeding the abuse layer's
  own counters directly via the same production `record_*` functions;
  and an assertion wrongly assumed a globally-empty `audit_logs` table
  for `LOGIN_SUCCEEDED`, when 5 real historical rows already existed
  from earlier manual verification sessions against the live stack —
  fixed by scoping the assertion to the test's own unique IP.
- `ruff`/`mypy` clean (82 source files). **6/6 new tests passed, 3
  consecutive times**, alongside the complete **254-test backend suite
  passing 254/254, 3 consecutive runs**, against real Redis and real
  PostgreSQL inside `compose-backend-1` (the host shell's own
  published-port path remained broken this session too).
- Docs updated in the same working tree: ADR 0006 (Implementation status
  table updated for Slice 3b's merge and the new audit-emission row),
  `docs/SECURITY.md` (the "Rate limiting" section's stale
  "abuse-detection layer does not exist yet" statement corrected now
  that Slice 3b has actually merged; "Audit logging" extended for the
  two new event types and their metadata/`user_id` conventions),
  `PROJECT_STATE.md`, `HANDOFF.md`.

### 2026-09-19 — Test-isolation fix: sweep `abuse:*` Redis keys between tests

- **Not committed to `main`** (commit on the still-open PR #14 branch,
  `issue-redis-rate-limiting-slice-3b`). Fixes a real test-isolation gap
  the abuse-protection layer's endpoint wiring (Slice 3b, below)
  surfaced and CI itself caught: `backend/tests/conftest.py`'s
  `_reset_rate_limiters` autouse fixture swept `rl:*` Redis keys between
  tests but not the new `abuse:*` keys `login`/`forgot-password`/
  `reset-password` now write. Every `TestClient` request shares the same
  fixed default peer IP, so that state accumulated across unrelated
  tests within one pytest session and could legitimately trip R4's
  `STRICT_THROTTLE`, producing real `429` responses in later,
  unconnected tests.
- Fixed with a single, minimal change: the existing `rl:*`
  pattern-delete loop now also sweeps `abuse:*`, under the same
  `RedisError` tolerance already in place. No production code touched
  (`abuse_decision.py`/`abuse_state.py`/`rate_limit.py`/`auth.py` all
  unchanged); no test skipped, `xfail`ed, or reordered.
- The complete backend suite (248 tests: 215 pre-abuse-layer + 32 Slice
  3a + 33 Slice 3b) **passed 248/248, 3 consecutive runs**, against real
  PostgreSQL and real Redis. `ruff`/`mypy` clean.

### 2026-09-19 — Abuse-protection Slice 3b: decision engine and endpoint wiring

- **Not committed.** Implements the deterministic decision layer on top
  of Slice 3a's primitives (now merged, see `[Unreleased — committed]`
  below) and wires it into `login`/`forgot-password`/`reset-password` —
  the only three operations any of R1–R5 target. `register`/`refresh`
  remain byte-for-byte unchanged.
- `backend/app/core/abuse_decision.py` (new): a module-level R1–R5 rule
  table (the data that makes `TEMPORARY_BLOCK` deterministically
  dominate `STRICT_THROTTLE` — block dimensions are always resolved
  before any strict dimension is even inspected); `check()` (pre-request,
  read-only); four explicitly-named record functions
  (`record_login_failure`, `record_login_success`,
  `record_forgot_password_request`, `record_reset_validation_failure` —
  deliberately not one function overloaded with a `succeeded` flag,
  since `forgot-password` has no real success/failure branch to key
  off); fails open unconditionally on Redis unavailability, no-ops when
  Redis is unconfigured; never touches PostgreSQL or `app.core.audit`
  (Slice 3c's job).
- `backend/app/core/abuse_state.py` (additive): one new primitive,
  `temporary_block_ttl_seconds()`, for an accurate `Retry-After` on a
  blocked response — no existing signature changed.
- `backend/app/core/token_bucket_types.py` (new): `DimensionSpec`/
  `TokenBucketResult` extracted out of `rate_limit.py` to break a
  circular import (`rate_limit.py` → `abuse_decision.py` →
  `abuse_state.py` → `rate_limit.py`) discovered — via an actual
  `ImportError`, not just suspected — while wiring this slice.
  `rate_limit.py` re-exports both names unchanged; no other call site
  needed to change.
- `backend/app/core/rate_limit.py` / `backend/app/api/v1/auth.py`
  (modified): `enforce_login_rate_limit`/
  `enforce_forgot_password_rate_limit`/`enforce_reset_password_rate_limit`
  now consult `abuse_decision.check()` ahead of the base `check_all()`
  (an active block rejects immediately; an active strict dimension is
  folded into the same atomic `check_all()` invocation as the base
  dimensions — never a second Redis round trip). `login`/
  `forgot-password`/`reset-password` gained post-outcome recording,
  called only after the real outcome is known — never in the
  pre-request dependency, which necessarily runs before authentication
  is attempted.
- `backend/tests/test_abuse_decision.py` (new, 33 tests): rule-table
  shape, per-rule threshold behavior for R1–R5, TTL/non-refresh
  semantics, simultaneous-rule precedence (confirming block always
  dominates strict, by construction), account/IP isolation,
  successful-login reset scoping, R4's unconditional recording, R5's
  failure-only recording, Redis-unavailable/unconfigured handling,
  concurrency races, strict-dimension atomicity with the base dimension,
  and no raw secret leakage. Two test-design bugs (not implementation
  bugs) were found and fixed during this slice's own validation.
- `ruff`/`mypy` clean (81 source files). **33/33 new tests passed, 3
  consecutive times, against real Redis + real PostgreSQL**, run inside
  `compose-backend-1` (the host shell's own published-port path remained
  broken this session too) — alongside the unaffected 32 from Slice 3a
  (65/65 combined).
- **A genuine test-infrastructure gap was found and deliberately not
  fixed** (out of scope for this slice): `tests/conftest.py`'s
  `_reset_rate_limiters` sweeps `rl:*` between tests but not the new
  `abuse:*` keys, so a full pre-existing-suite run can accumulate real
  R4 state across the shared default `TestClient` IP and fail 2
  pre-existing `test_password_reset.py` tests — reproduced from a
  freshly flushed Redis, confirmed unrelated to this slice's own
  correctness. Recorded in `HANDOFF.md` with the exact one-line fix for
  a future, separately-approved change.
- Docs updated in the same working tree: ADR 0006 (§6's flow diagram
  corrected — the original placed `record(outcome)` inside the
  pre-request dependency, which is unreachable since outcomes aren't
  known until the endpoint body runs; "Implementation status" table
  updated), `PROJECT_STATE.md`, `HANDOFF.md`. `docs/SECURITY.md`
  reviewed and left unchanged — it describes the *committed* codebase,
  and Slice 3b isn't committed yet, so its "abuse layer doesn't exist
  yet" statement remains accurate for `main`.

### 2026-09-19 — Abuse-protection Slice 3a: real-Redis validation

- **Still not committed** — this entry records a validation result for
  the same uncommitted working tree as the entry immediately below, not a
  new implementation change.
- The host shell's path to the Dockerized Redis/Postgres published ports
  (`127.0.0.1:5432`/`127.0.0.1:6379`) was found broken this session (TCP
  handshake succeeds, protocol read reset) — confirmed as an environment
  fault via internal Docker-network health checks and via a
  previously-passing, unrelated test file failing identically, not a
  Slice 3a defect.
- Worked around by running `tests/test_abuse_state.py` **inside the
  running `compose-backend-1` container**, over its internal `db`/`redis`
  Docker service hostnames: **32/32 passed, 3 consecutive runs**, no
  flakiness. Live Redis inspection during that run confirmed real
  `abuse:*` key creation of every expected type, a finite positive TTL on
  every key observed, and no raw email substring in any key name or
  value. `ruff`/`mypy` re-confirmed clean inside the container.
- The container's own backend image was stale relative to `main` HEAD
  (missing 8 pre-existing tests from `test_rate_limit_wiring.py`) and had
  an `EMAIL_PROVIDER=smtp` app-runtime setting that caused 5 unrelated
  `test_password_reset.py` failures (diagnosed and resolved via a
  one-off, file-free `EMAIL_PROVIDER=console` invocation override to
  confirm the root cause) — **this is not a run of the current 215-test
  full suite** and is not represented as one.
- Net effect: Slice 3a's 32 tests are now **real-Redis validated**,
  distinct from — and not yet extending to — a clean host-side full-suite
  run or any production validation.

### 2026-09-18 — Abuse-protection Slice 3a: Redis/Lua primitives for the deterministic abuse layer (ADR 0006 §11/§12)

- **Not committed.** Implements only the low-level Redis primitives the
  abuse layer needs — no rule table, no `AbuseDecisionEngine`, no
  endpoint wiring (Slice 3b/3c, not started). Every existing endpoint
  (`register`/`login`/`refresh`/`forgot-password`/`reset-password`)
  remains byte-for-byte unchanged from Slice 2.
- `backend/app/core/abuse_keys.py` (new): key builders for the `abuse:`
  namespace (`failcount_key`, `distinct_ips_key`, `strict_throttle_key`,
  `block_key`), mirroring `redis_keys.py`'s role for `rl:`.
- `backend/app/core/abuse_state.py` (new): atomic Lua-scripted
  primitives, fully parameterized (no hardcoded thresholds):
  `record_login_failure()` (one Lua invocation atomically updating the
  IP failcount, account failcount, and distinct-IP HyperLogLog together,
  escalating each dimension independently once its own threshold is
  crossed); `record_ip_failure()` (the shared primitive behind the
  forgot-password/reset-password IP counters, parameterized by a
  `strict`/`block` escalation mode); `reset_account_state()` (the
  successful-login decay — deletes only the account-scoped failcount and
  distinct-IP HyperLogLog, never the IP failcount or any block/strict
  state); `is_strict_throttle_active()`/`is_temporarily_blocked()`
  (read-only checks for Slice 3b's future use). STRICT_THROTTLE reuses
  the existing `RedisTokenBucketLimiter`/`DimensionSpec` bucket shape —
  no new bucket engine. TEMPORARY_BLOCK's TTL is set once at creation and
  never refreshed (guarantees ADR §12's "never permanent or indefinite");
  STRICT_THROTTLE's TTL does refresh on re-escalation. All primitives
  raise `RedisUnavailableError` on failure — no second fallback limiter.
- `backend/tests/test_abuse_state.py` (new, 32 tests): failcount
  lifecycle, HyperLogLog lifecycle, reset-on-success scoping, block/
  strict-throttle creation and TTL semantics, multi-signal atomicity,
  concurrent-write races (real `threading`, no mocks), cross-account/
  cross-IP isolation, Redis-unavailable handling, and a check that no raw
  email or secret is ever stored in a Redis value.
- `ruff`/`mypy` clean on all three new files; `pytest --collect-only`
  succeeds at 215 tests (183 existing + 32 new). **The 32 new tests have
  not been executed against a real Redis this session** — Docker/WSL was
  confirmed unavailable (connection-refused checks against both
  6379/5432; see `HANDOFF.md` for the exact evidence). Do not read "215
  collected" as a passing count.
- Docs updated in the same working tree: `docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md`
  (R1–R5 thresholds/windows resolved and recorded, the corrected
  60-second token-bucket timing derivation replacing an earlier wrong
  "~2 minutes" estimate, the strict/block TTL-asymmetry rationale, the
  successful-login decay policy, and a 7-row per-component
  implementation-status breakdown for the abuse layer),
  `PROJECT_STATE.md` (component-status rows), `HANDOFF.md` (current
  task, a new "Completed work (Redis abuse layer — Slice 3a)" section,
  revised "Next major task"/"Tests run"/"Exact next recommended action").
  `docs/SECURITY.md` was reviewed and needs no change — it already
  states the abuse layer doesn't exist yet, still true since Slice 3a
  changes no runtime behavior.

### 2026-09-11 — Application Foundation: backend/frontend/infra scaffold, Docker fixes, CI workflow

- Backend (`backend/`): FastAPI scaffold with configuration
  (`app/core/config.py`), structured JSON logging, request-ID middleware,
  centralized error handling, SQLAlchemy + Alembic, a pgvector-enabling
  migration (`0001_enable_pgvector_extension`), and health/readiness
  endpoints (`/api/v1/health`, `/api/v1/health/ready`).
- Frontend (`frontend/`): Next.js + TypeScript, Tailwind v4, a shadcn/ui
  foundation, an application shell, stub routes for the target feature
  areas, and a live backend-readiness widget (`components/backend-status.tsx`).
- Infrastructure (`infra/`): `infra/docker/backend.Dockerfile`,
  `infra/docker/frontend.Dockerfile`, and
  `infra/compose/docker-compose.yml` wiring Postgres+pgvector, backend, and
  frontend together for local development.
- Fixed a container-runtime bug found during verification: the backend
  image built its virtualenv as root, then switched to a non-root
  `appuser` without transferring ownership, so the entrypoint's
  `uv run alembic upgrade head` crash-looped with `Permission denied`
  trying to resync the root-owned `.venv`. Fixed with
  `chown -R appuser:appuser /app` before `USER appuser` in
  `infra/docker/backend.Dockerfile`.
- Fixed a missing-CORS bug found during verification: the backend had no
  CORS middleware, so a real browser at `http://localhost:3000` fetching
  `http://localhost:8000` would have been silently blocked even though the
  backend was reachable (confirmed via `curl` outside the browser's CORS
  enforcement). Added `CORSMiddleware` to `backend/app/main.py`, a new
  `cors_allowed_origins` setting (default `http://localhost:3000`) in
  `backend/app/core/config.py`, and wired `CORS_ALLOWED_ORIGINS` through
  `.env.example` and `infra/compose/docker-compose.yml`.
- Added `.github/workflows/ci.yml`: backend lint/typecheck/tests, frontend
  lint/typecheck/tests/build, and a Docker build + `docker compose config`
  validation job.
- Verified end-to-end, against real running containers (not mocked):
  both Docker images build; the full Compose stack starts; the pgvector
  extension is enabled in the running Postgres container (`vector 0.8.6`);
  the Alembic migration applies against the real database
  (`alembic current` → `0001 (head)`); `/api/v1/health` and
  `/api/v1/health/ready` return 200 with a real database round-trip; the
  frontend serves; and a CORS-enabled cross-origin fetch from the
  frontend's origin to the backend's readiness endpoint succeeds.
- No product functionality (auth, ingestion, retrieval, generation, chat,
  voice) was implemented — out of scope for this issue. See `HANDOFF.md`
  for the one verification gap (the `BackendStatus` widget's resolved
  rendered state was not confirmed in an actual browser DOM, only the
  underlying CORS-enabled fetch it depends on).

### 2026-09-11 — Second-pass documentation audit and corrections

- Audited the full documentation set for internal consistency (see
  `HANDOFF.md` for the finding list: 0 CRITICAL / 2 HIGH / 5 MEDIUM / 4 LOW
  / 3 SUGGESTION) and applied corrections:
  - Added [ADR 0003](docs/DECISIONS/0003-authentication-session-architecture.md)
    (authentication/session architecture), resolving the bearer-token vs.
    session-revocation contradiction and promoting `sessions` to a core
    entity in `docs/DATA_MODEL.md`. Updated `docs/API_CONTRACT.md` and
    `docs/SECURITY.md` to match.
  - Documented the rate-limiting approach (in-process/PostgreSQL-backed,
    no Redis) in `docs/SECURITY.md` and `docs/ARCHITECTURE.md`.
  - Added `RERANKER_API_KEY` to `.env.example`.
  - Added a target audit-logs API namespace to `docs/API_CONTRACT.md`.
  - Documented chunking-strategy comparison in `docs/EVALUATION.md`.
  - Added `.gitattributes` to the target tree in `docs/ARCHITECTURE.md`.
  - Reworded `README.md`'s opening to avoid any production-readiness
    misread.
  - Documented the Git-workflow bootstrap exception in `AGENTS.md`.
  - Made `docs/DECISIONS/` and `.agents/skills/` explicitly discoverable
    in `START_HERE.md`/`README.md`.
  - Clarified that baseline issue numbers in `PROJECT_STATE.md`/
    `AGENTS.md` are planning references, not existing GitHub issues.
- No application code, dependencies, schemas, Docker services, API
  endpoints, or GitHub issues were created — documentation only.

### 2026-09-11 — Documentation architecture established

- Populated the full documentation/project-memory system: `README.md`,
  `START_HERE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
  `PROJECT_STATE.md`, `HANDOFF.md`, `SOLVING.md` (this changelog's sibling
  files were all previously empty placeholders).
- Populated `docs/PROJECT_BRIEF.md`, `docs/REQUIREMENTS.md`,
  `docs/ARCHITECTURE.md`, `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`,
  `docs/SECURITY.md`, `docs/RAG_DESIGN.md`, `docs/EVALUATION.md`,
  `docs/DEPLOYMENT.md`.
- Added `docs/DECISIONS/` with an ADR process, a template, and two initial
  architecture decision records: modular monolith over microservices, and
  PostgreSQL + pgvector as the initial vector store.
- Added `.agents/skills/README.md` documenting the intended skills roster
  and the RULE/SKILL/MCP/MEMORY/ADR/HANDOFF/SOLVING distinction.
- No application code, dependencies, database schema, Docker services, or
  API endpoints were added — this was a documentation-only initialization
  task.

## [Unreleased — committed]

### 2026-09-21 — `feat: add StorageProvider abstraction (Issue #3, Slice 3.2)` (91d98b7) + docs (d57ccdb, 044c54f), merged as `941c1a7`

*(Branch `issue-3-slice-3-2-storage-provider`, cut from the merged Slice
3.1 (`79d4787`, PR #17). Opened as **PR #18**, verified green on GitHub
Actions CI (4/4 checks), merged into `main` as squash commit `941c1a7`.
Note: this merge happened before a concurrent correctness/security
review of the same slice had finished — that review's own fix (next
entry below) landed as a separate follow-up PR instead of inside this
one.)*

Adds the `StorageProvider` abstraction — a `Protocol`
(`save`/`read`/`delete`/`exists`) plus `LocalStorage`, a filesystem-
backed implementation for local dev/CI, mirroring `EmailProvider`'s
exact shape (`backend/app/services/storage_provider.py`). Storage keys
are always server-generated upstream (never a user-supplied filename —
`docs/SECURITY.md`), but `LocalStorage` also rejects any key that would
resolve outside its configured root as defense in depth. New settings:
`storage_provider` (`Literal["local"]`, the only implementation today)
and `storage_local_root`; `storage_bucket` stays reserved for a future
object-storage provider. 14 new tests
(`backend/tests/test_storage_provider.py`), real filesystem, no mocks.
`ruff`/`mypy` clean. Full backend suite: 287/287 passing (273 existing +
14 new), 3 consecutive runs. No upload endpoint, extraction, chunking,
background processing, or embedding code — nothing calls this yet.

### 2026-09-21 — `fix: prevent raw filesystem errors/paths escaping StorageProvider` (6e96481) + docs (d950d4e), merged as `5e6fdc2`

*(A correctness/security review of the already-merged Slice 3.2 found
that `save()`/`delete()`/`exists()` had no filesystem-error handling at
all, and `read()` only handled the "not found" case — a raw
`PermissionError`/`OSError` could have escaped the module, leaking the
absolute configured storage root via its own message. The review ran
concurrently with PR #18's merge, so the fix couldn't land inside it —
committed as `050b185`/`03c870e` on that now-merged branch, then
cherry-picked cleanly onto a fresh branch cut from `main`, opened as
**PR #19**, verified green on GitHub Actions CI (4/4 checks), merged as
squash commit `5e6fdc2`.)*

Every operation now guards its own filesystem calls, raising
`StorageError` referencing only the caller-supplied key, never the
resolved absolute path. Two stdlib-behavior assumptions from the
original implementation were empirically disproven while fixing this —
`Path.is_file()` does not swallow `OSError` on this project's actual
Python version (3.13.15), contrary to what the original code's own
comment claimed. 7 new tests (`backend/tests/test_storage_provider.py`,
14 → 21): a symlink planted inside the root that would resolve outside
it, permission-denied operations each raising `StorageError` with no
path leak, and `exists()` still correctly returning `True` when only a
file's own permissions are restricted. `ruff`/`mypy` clean. Full backend
suite: 294/294 passing (273 existing + 21 new), 3 consecutive runs.

### 2026-09-20 — `feat: add document and document_chunk schema (Issue #3, Slice 3.1)` (36fe8b0) + docs (301f8a2, e73c883), merged as `79d4787`

*(Branch `issue-3-slice-3-1-document-schema`, cut from the merged
Playwright E2E work (`e1c4858`, PR #16). Opened as **PR #17**, verified
green on GitHub Actions CI (4/4 checks — backend, frontend, Docker
build, and the first real Actions run of the `e2e` job), merged into
`main` as squash commit `79d4787`.)*

GitHub Issue #3 (Knowledge Ingestion), Slice 3.1 — schema only. Adds
`documents`/`document_chunks` (migration `0004`): workspace ownership,
nullable `uploaded_by` (`ON DELETE SET NULL`), server-generated
`storage_key`, a native `DocumentStatus` enum matching the documented
ingestion lifecycle exactly, and `document_chunks` with a deliberately
denormalized `workspace_id` and no embedding column yet (deferred until
the embedding provider/model/dimension is chosen). 19 new tests
(`backend/tests/test_document_schema.py`), real Postgres, no mocks.
`ruff`/`mypy` clean. Full backend suite: 273/273 passing (254 existing +
19 new), 3 consecutive runs. Migration reversibility explicitly verified
(`alembic downgrade 0003` / `upgrade head` against the real database).
Also reconciled a documentation lag from the Playwright merge below
(`PROJECT_STATE.md`/`HANDOFF.md`/`CHANGELOG.md` still described it as
uncommitted).

### 2026-09-20 — `feat: add Playwright E2E coverage for auth and password recovery` (e1c4858)

*(Branch `playwright-e2e-auth-validation`, cut from the merged Slice 3c
(`75dd466`, PR #15). Opened as **PR #16** and merged into `main` as
squash commit `e1c4858` — a single-commit PR, so the commit hash above
is both the branch's own commit and the merge result.)*

Introduces Playwright (`@playwright/test` ^1.63.0, Chromium), previously
absent from this repository. `frontend/playwright.config.ts` —
`workers: 1`/`fullyParallel: false` deliberately, since the backend's
rate limiter and abuse layer (ADR 0006) both key partly by source IP and
every request in a run shares one peer address. 19 tests across three
spec files: `app-availability.spec.ts` (3), `auth.spec.ts` (9 —
registration, session persistence/reload, logout, protected-route
redirects, a genuine CSRF positive+negative case through the real
backend middleware), `password-recovery.spec.ts` (7 — the full
forgot-password → Mailpit → reset-password → post-reset login →
session-revocation flow). Run against the real
frontend/backend/PostgreSQL/Redis/Mailpit stack, no mocks — 19/19
passed, 3 consecutive clean runs. Three genuine findings from validation,
all fixed as test-code corrections, no application code changed:
a locator strict-mode ambiguity (a workspace name correctly renders in
three places, not a bug); a direct refresh-revocation check that
initially omitted the CSRF header a state-changing endpoint requires;
Chromium's own "Failed to load resource: 401" console logging for an
already-handled anonymous-visitor auth check. `.github/workflows/ci.yml`
gained a new `e2e` job. `ruff`/`npx eslint`/`npx tsc --noEmit` all clean;
existing 48 vitest tests unaffected.

### 2026-09-20 — `feat: emit audit events for abuse-layer escalations` (58b6c71), merged as `75dd466`

*(Branch `issue-redis-rate-limiting-slice-3c`, on top of the merged
Slice 3b (`42529e3`, PR #14). Opened as **PR #15**, verified green on
GitHub Actions CI (3/3 checks) on the first push, merged into `main` as
squash commit `75dd466`.)*

Adds `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` to
`backend/app/core/audit.py` and a `_audit_abuse_escalation()` helper in
`backend/app/api/v1/auth.py`, called from `login`/`forgot-password`/
`reset-password` right after each abuse-state `record_*()` call — emits
`AuditEvent.RATE_LIMITED` for a `STRICT_THROTTLE` transition or
`AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` for a `TEMPORARY_BLOCK`
transition, exactly once per escalation, with metadata limited to
rule/operation/dimension, the already-HMAC-hashed account identifier
when account-scoped, and the block TTL — never a raw secret. No
abuse-decision production code (`abuse_decision.py`/`abuse_state.py`/
`rate_limit.py`) was modified. 6 new HTTP-level tests
(`backend/tests/test_abuse_audit.py`), real-Redis validated (6/6, 3
consecutive runs, alongside the complete 254-test suite) before this PR
was opened.

### 2026-09-20 — `feat: add abuse-decision engine and wire R1-R5 into auth endpoints` (906e2f9) + `test: clear abuse:* Redis keys between tests alongside rl:*` (46a2860) + docs (2896b1d), merged as `42529e3`

*(Branch `issue-redis-rate-limiting-slice-3b`, on top of the merged
Slice 3a (`026dcf3`, PR #13). Opened as **PR #14**, iterated once after
CI caught a real test-isolation gap, verified green on GitHub Actions CI
(3/3 checks) on the final push, merged into `main` as squash commit
`42529e3`.)*

Adds `backend/app/core/abuse_decision.py` (the deterministic R1–R5 rule
table, `check()`/four explicitly-named `record_*()` functions), one
additive primitive in `backend/app/core/abuse_state.py`
(`temporary_block_ttl_seconds()`), and `backend/app/core/token_bucket_types.py`
(`DimensionSpec`/`TokenBucketResult`, extracted from `rate_limit.py` to
break a real circular import this slice's wiring introduced —
`rate_limit.py` re-exports both names unchanged). Wires the engine into
`enforce_login_rate_limit`/`enforce_forgot_password_rate_limit`/
`enforce_reset_password_rate_limit` (`backend/app/core/rate_limit.py`)
and post-outcome recording into `login`/`forgot-password`/
`reset-password` (`backend/app/api/v1/auth.py`) — `register`/`refresh`
untouched. 33 tests (`backend/tests/test_abuse_decision.py`), real-Redis
validated (65/65 combined with the unaffected Slice 3a suite, 3
consecutive runs) before this PR was opened. A genuine test-isolation
gap in `backend/tests/conftest.py` (`_reset_rate_limiters` not sweeping
the new `abuse:*` keys) was found during validation, confirmed by CI
itself failing 3/248 on the first push, and fixed with a single-file,
minimal change before the final green push — the complete 248-test
backend suite passed 248/248, 3 consecutive runs, after the fix.

### 2026-09-19 — `feat: add Redis abuse state primitives` (676d7e5), merged as `026dcf3`

*(Branch `issue-redis-rate-limiting-slice-3a`, on top of the merged
Slice 2 (`5391a78`, PR #12). Opened as **PR #13**, verified green on
GitHub Actions CI (backend lint/typecheck/tests, frontend
lint/typecheck/tests/build, Docker build check), merged into `main` as
squash commit `026dcf3`.)*

Adds `backend/app/core/abuse_keys.py` (the `abuse:` Redis key namespace)
and `backend/app/core/abuse_state.py` (atomic Lua-scripted record/reset
primitives for R1–R5's counters, R3's distinct-IP HyperLogLog, the
strict-throttle bucket, and the temporary-block flag — reusing the
existing token-bucket engine for the strict bucket, no new engine).
Fully parameterized — no rule thresholds hardcoded. 32 tests
(`backend/tests/test_abuse_state.py`), real-Redis validated (32/32, 3
consecutive runs) before this PR was opened. No endpoint wiring —
`register`/`refresh`/`login`/`forgot-password`/`reset-password` remain
byte-for-byte unchanged from Slice 2 (that's Slice 3b, see
`[Unreleased — working tree]` above).

### 2026-09-18 — `feat: wire Redis rate limiting into auth endpoints` (f61737f), merged as `5391a78`

*(Branch `issue-redis-rate-limiting-slice-2`, on top of the merged Slice
1 (`46ef03b`, PR #11). Opened as **PR #12**, verified green on GitHub
Actions CI (3/3 checks: backend lint/typecheck/tests, frontend
lint/typecheck/tests/build, Docker build check), and **merged into
`main` as squash commit `5391a78`** — a single-parent squash merge
(parent `46ef03b`), so `f61737f` is not itself an ancestor of `5391a78`.
`main` and `origin/main` are both at `5391a78`. The
`issue-redis-rate-limiting-slice-2` branch was auto-deleted on `origin`
after the merge; it still exists as a stale local branch only.)*

Wires the Redis-backed engine built in Slice 1 into every
`enforce_*_rate_limit` dependency (`backend/app/core/rate_limit.py`),
per [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
§6/§9/§13. This **is** a real, observable change to every authentication
endpoint's rate-limiting behavior, now active in the committed codebase
on `main`:

- `register`, `login`, `refresh`, `forgot-password`, `reset-password` all
  now attempt `RedisTokenBucketLimiter` first, using ADR §9's exact
  per-operation dimensions (IP via the trusted-proxy-aware
  `resolve_client_ip()`; HMAC-hashed email for `login`/`forgot-password`'s
  account dimension; the refresh-token cookie's session ID — no DB
  lookup — for `refresh`), falling back to the existing
  `FixedWindowRateLimiter` per ADR §13's operation-aware policy.
- **Resolved one of ADR §13/§22's explicitly-open implementation
  decisions, with rationale recorded in the ADR, `SOLVING.md`, and code**:
  an *unconfigured* Redis (`REDIS_URL` unset — today's default
  everywhere) always falls back to the in-process limiter, for every
  operation including `register`; the ADR's literal Tier B fail-open is
  reserved for a genuine mid-request outage of an *already-configured*
  Redis. Implementing the literal default would have made `register`
  unprotected by default in every environment today.
- New `rate_limit_hash_key` setting (`backend/app/core/config.py`) —
  resolves ADR §14/§22's "HMAC key location" open decision by reusing
  `SECRET_KEY` unless explicitly overridden.
- Fixed a real test-isolation gap this wiring exposed: `conftest.py`'s
  `_reset_rate_limiters` fixture only reset the in-process limiters, not
  the `rl:*` Redis keys every test now writes through the live wiring —
  52 previously-passing tests failed until this was fixed. Full writeup
  in `SOLVING.md`.
- From this slice's own read-only security/architecture review (0 P0,
  3 P1, 3 P2, 2 P3 findings, all P1s and the important P2 fixed before
  commit): structured logging on the Redis-failure fallback path
  (`_log_redis_fallback()`, ADR §13's own requirement — `operation`/
  `policy` fields only, never a request-derived value); corrected stale
  docstrings in `redis_client.py`/`ip_resolution.py` ("not wired into any
  endpoint yet", false as of this slice); 8 additional HTTP-level tests
  covering `refresh`/`forgot-password`/`reset-password` Redis-key
  creation and Tier A fallback (previously only `login`/`register` had
  them), an endpoint-driven multi-dimension atomicity regression test for
  `login`, and a cross-user account-isolation test.
- 13 HTTP-level tests total (`backend/tests/test_rate_limit_wiring.py`,
  183 total up from 170): real-Redis key creation via live endpoint
  calls, Tier A/Tier B failure-policy behavior via dependency override,
  the unconfigured-vs-unreachable distinction, spoofed
  `X-Forwarded-For` ignored by default, endpoint-driven multi-dimension
  atomicity, cross-user isolation. `ruff`/`mypy` clean; full suite
  re-run 3 times with no flakiness (locally, against real Postgres +
  real Redis, immediately before this commit) and independently
  re-verified by GitHub Actions CI on PR #12 after push.
- Verified live against the real Docker Compose stack, in an earlier
  checkpoint before commit: inspected the exact Redis keys a live login
  created (`redis-cli --scan`), confirmed login capacity enforcement
  across a real session, confirmed `/api/v1/health/ready` stays
  independent of Redis, and exercised a genuine Redis outage and
  recovery mid-session — `register` failed open only during the outage,
  `login` still hit `429` via the fallback limiter during that same
  outage, and enforcement resumed automatically once Redis came back,
  with no process restart.
- Also reconciles `PROJECT_STATE.md`, `HANDOFF.md`, `docs/SECURITY.md`,
  and ADR 0006 to reflect that both Redis slices are now merged.
- Does **not** include the deterministic abuse-detection layer (ADR
  §11/§12) — still not started, see `HANDOFF.md`.

### 2026-09-15 — `feat: implement distributed Redis rate limiting foundation` (b1f1b00), merged as `46ef03b`

*(Branch `issue-redis-rate-limiting`. Reconciled with a documentation
checkpoint, `docs: reconcile Redis Slice 1 project state` (`c8aa2be`),
pushed, opened as **PR #11**, verified green on GitHub Actions CI (3/3
checks), and **merged into `main` as squash commit `46ef03b`** — a
single-parent squash merge (parent `7e439d2`), so `b1f1b00`/`c8aa2be`
are not themselves ancestors of `46ef03b`, but its tree content is
byte-identical to `c8aa2be`'s (`git diff c8aa2be 46ef03b` is empty).
`main` and `origin/main` are both at `46ef03b`. The `issue-redis-rate-limiting`
branch still exists locally and on `origin` (not auto-deleted) but has
no content not already in `main`; Slice 2 work continues on a new
branch, `issue-redis-rate-limiting-slice-2`, cut from the merged `main`.)*

Adds the Redis-backed distributed rate-limiting foundation designed in
ADR 0006 (§8/§10/§14), without wiring it into any endpoint yet: the
multi-key atomic Lua token-bucket engine (`RedisTokenBucketLimiter`,
`DimensionSpec`), a Redis connection abstraction with an exception-free
availability check, centralized rate-limit key construction with a
keyed-HMAC (not plain-hash) email identifier, and a trusted-proxy-aware
IP resolver (secure-by-default: `X-Forwarded-For` ignored unless the
peer is within a configured trusted CIDR). The existing in-process
`FixedWindowRateLimiter` and every `enforce_*_rate_limit` function are
byte-for-byte unchanged and remain what every endpoint actually uses —
still true as merged. Also adds the `redis` dependency, a pinned
`redis:7.4-alpine` Docker Compose/CI service, and 51 new tests (119 →
170) covering config validation, the Lua engine's atomicity/concurrency/
TTL/cost semantics (including the multi-key all-or-nothing regression
test for the partial-consumption race found during ADR review), and
trusted-proxy IP resolution. Independently validated in an isolated
worktree before the commit: 170/170 tests pass against real Postgres and
real Redis, `ruff`/`mypy` clean. Endpoint wiring (Slice 2) was
deliberately kept out of this PR — see the "implementation slice 2"
entry above for its own, separate status.

### 2026-09-14 — `feat: complete secure cookie auth and password recovery` (864d783)

*(GitHub Issue #2 checkpoint. Opened as PR #10, verified green on GitHub
Actions CI (3/3 checks), and merged into `main` as commit `ec4225d` — a
squash/rebase merge, so `ec4225d` has a single parent rather than being a
two-parent merge commit, but its tree content is byte-identical to
`864d783`. `main` and `origin/main` are both at `ec4225d`.)*

Migrates browser authentication from bearer tokens in the response body to
HttpOnly cookies with CSRF protection, and adds a complete password
recovery vertical slice, on top of the registration/login/workspace work
already in this branch:

- **Cookie + CSRF authentication** (supersedes the original
  response-body-token design): access/refresh tokens delivered exclusively
  via `HttpOnly` cookies (`access_token` on `Path=/`, `refresh_token`
  scoped to `Path=/api/v1/auth`) — never in a response body, never read by
  frontend JavaScript, no `localStorage`/`sessionStorage` token storage
  anywhere (`frontend/lib/auth-storage.ts` removed). Double-submit CSRF
  cookie (`csrf_token`, deliberately non-`HttpOnly`) + `X-CSRF-Token`
  header on every state-changing request, including login/register.
  Deployment-aware cookie/CORS configuration
  (`COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`/
  `CORS_ALLOWED_ORIGINS`), documented in new
  [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  including the "different origin ≠ cross-site" distinction that governs
  `COOKIE_SAMESITE`.
- **Password recovery** (backend + frontend): `/forgot-password` and
  `/reset-password` — cryptographically random, SHA-256-hashed-at-rest,
  single-use, expiring reset tokens; enumeration-resistant
  (identical response/timing regardless of whether the email exists); a
  successful reset revokes every existing session for the account. Email
  delivery via a new vendor-neutral `EmailProvider` abstraction (`console`
  dev fallback or `smtp`, verified locally against Mailpit).
  `ENVIRONMENT=production` with `EMAIL_PROVIDER=console` now fails at
  config-load time — a genuine defect found during a dedicated security
  audit of this feature (stdout is typically captured by log aggregation
  in real deployments, which would otherwise leak raw reset tokens into
  production logs).
- **Audit logging**: new `audit_logs` table and `AuditEvent` recording for
  authentication events, password-reset events, workspace membership
  changes, and authorization denials.
- **Docs**: `docs/SECURITY.md` corrected to match the current
  implementation (previously described bearer tokens and listed audit
  logging as not implemented).
- **Tests**: backend 95 → 119 pytest tests; frontend 30 → 48 vitest tests,
  including explicit regression tests proving no auth token ever reaches
  `localStorage`/`sessionStorage`/an `Authorization` header.
- **Verified end-to-end** against the real Docker Compose stack (now
  including a `mailpit` service): register → forgot-password → Mailpit
  received the email with a correct reset link → reset-password (CSRF
  matrix: missing rejected, valid accepted) → old password rejected, new
  password accepted → the pre-reset refresh token invalidated → zero
  occurrences of the raw reset token in backend logs.
- Two non-obvious problems solved during this checkpoint are written up in
  `SOLVING.md`: a rate-limiter test-isolation gap that made password-reset
  tests silently receive no email, and a Vitest fetch-mock `Response`
  object being reused across multiple calls in one test (causing "Body
  already read" errors).
- Does **not** include Redis-backed rate limiting, a deterministic
  abuse-detection layer, or Playwright E2E — all explicitly deferred; see
  `HANDOFF.md`.

### 2026-09-11 — `chore: configure Git line endings` (a059965)

- Added `.gitattributes` (`* text=auto eol=lf`).

### 2026-09-11 — `chore: initialize project architecture and documentation` (a7d81cf)

- Initial repository scaffold: empty placeholder docs (`AGENTS.md`,
  `CHANGELOG.md`, `CLAUDE.md`, `GEMINI.md`, `HANDOFF.md`,
  `PROJECT_STATE.md`, `SOLVING.md`, `START_HERE.md`, `docs/*.md`),
  `.env.example`, `.gitignore`.
