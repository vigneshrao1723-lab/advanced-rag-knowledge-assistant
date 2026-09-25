# Security

**Status:** PARTIALLY IMPLEMENTED — authentication (HttpOnly cookie + CSRF,
password recovery), authorization, workspace isolation, audit logging, and
rate limiting on auth endpoints are now implemented and tested (GitHub
Issue #2 — Authentication & Workspaces; see "Authentication &
authorization", "Rate limiting approach", and "Audit logging" below for
exactly what's real). Upload validation and prompt-injection defense
remain not implemented — there's no upload or generation surface yet for
them to protect. The Issue #1 foundation's generic protections (centralized
error handling, loud-failure config loading) are also in place — see
"Errors and information disclosure" and "Secret management" below. See
[`PROJECT_STATE.md`](../PROJECT_STATE.md) for current, per-control status.

## Trust boundaries and core principles

1. **User data is isolated by workspace.** No user or process should be
   able to read or write another workspace's data.
2. **Authorization must be enforced server-side.** Client-side checks
   (hidden UI, disabled buttons) are never a substitute for a server-side
   permission check.
3. **Retrieved documents are untrusted input.** Anything pulled from the
   corpus during retrieval is data, not instructions.
4. **Prompt injection from retrieved content must not override system
   instructions.** The generation layer must be designed so that text
   embedded in a retrieved chunk cannot cause the LLM to ignore its system
   prompt, exfiltrate data, or take unintended actions.
5. **Secrets must never be committed.** `.env.example` contains placeholders
   only; real secrets live outside version control.
6. **Uploaded files are untrusted.** Every upload must be validated before
   it's processed or stored.
7. **File paths and filenames must be safely handled** — no path traversal,
   no trusting user-supplied filenames for storage paths.
8. **Rate limits must protect expensive operations** (auth attempts,
   uploads, embedding calls, LLM calls).
9. **Errors exposed to users must not reveal stack traces, internal paths,
   or secrets.**
10. **Audit logs should capture security-relevant actions** (auth events,
    workspace membership changes, document deletion, permission changes).
11. **Security assumptions must be tested, not merely documented** — see
    "Security testing" below and `AGENTS.md` §3.

## Authentication & authorization

**Implemented (Issue #2)**, all in `backend/app/core/security.py` and
`backend/app/services/auth_service.py` unless noted:

- Passwords hashed with Argon2id (see
  [ADR 0004](DECISIONS/0004-password-hashing-argon2id.md)).
- Short-lived access tokens backed by server-tracked refresh/session
  records — the architecture is **not** purely stateless. See
  [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  for the full model.
- **Tokens are delivered exclusively via `HttpOnly` cookies, never in a
  response body or an `Authorization` header** — the browser attaches them
  automatically; JavaScript never reads or holds them. A separate,
  non-`HttpOnly` `csrf_token` cookie plus an `X-CSRF-Token` header (double-
  submit pattern) protects every state-changing request, including
  `login`/`register` themselves. `SameSite`/`Secure`/`Domain` are
  deployment-aware (`COOKIE_SAMESITE`/`COOKIE_SECURE`/`COOKIE_DOMAIN`), and
  are never weakened for local-dev convenience. See
  [ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md) for the
  full model, including the "different origin ≠ cross-site" distinction
  that governs `COOKIE_SAMESITE` and the explicit requirements for a
  genuinely cross-site deployment.
- Sessions/devices are listable and individually revocable by the user;
  refresh tokens rotate on use; **logout invalidates the corresponding
  session's refresh capability immediately.** Reuse of a rotated-out
  refresh token revokes that session outright. Per ADR 0003, an
  already-issued access token is not retroactively invalidated by
  logout/session-revocation/password-reset — its blast radius is bounded
  by its short expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`), independent of
  session state; only its refresh capability dies immediately.
- **Password recovery** (`backend/app/services/password_reset_service.py`):
  reset tokens are cryptographically random (`secrets.token_urlsafe(32)`,
  256 bits), SHA-256-hashed at rest (raw value never stored or logged),
  single-use, and expiring (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`).
  `forgot-password` always returns the same generic response regardless of
  whether the email exists, with timing equalized via a dummy Argon2
  verification on the not-found path, to resist enumeration. A successful
  reset revokes every existing session for that user
  (`session_repository.revoke_all_for_user`) and reuses the same Argon2id
  hashing as normal password changes. Email delivery goes through the
  `EmailProvider` abstraction (`backend/app/services/email_provider.py`) —
  `console` (stdout, dev/test fallback) or `smtp` (any SMTP-compatible
  provider; local dev points it at Mailpit). `ENVIRONMENT=production` with
  `EMAIL_PROVIDER=console` fails at startup (`app/core/config.py`), since
  stdout is typically captured by log aggregation in real deployments,
  which would leak raw reset tokens into logs.
- Role-based authorization within a workspace: `OWNER`, `ADMIN`, `MEMBER`,
  `VIEWER` — enforced server-side on every workspace-scoped endpoint via
  `backend/app/core/dependencies.py`'s `require_workspace_role`, not just
  at the UI layer. See `docs/API_CONTRACT.md`'s authorization matrix.
- Rate limiting and brute-force protection on login/registration/refresh/
  forgot-password/reset-password (see "Rate limiting approach" below).
- Login failures, and forgot-password requests, return the same generic
  message whether the account exists or not, resisting enumeration via
  either endpoint.

## Rate limiting approach

Rate limiting is a firm requirement (see principle 8 above). It was
deliberately built in-process first, with no external session/cache store.
Going further is justified by architectural certainty, not measured
production evidence — this project has no production deployment, so there
is no telemetry or incident to point to (see [ADR 0006](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
§1's honest framing). That distinction, and the resulting design, is
documented below rather than anticipated speculatively:

- **Implemented (Issue #2):** an in-process fixed-window limiter
  (`backend/app/core/rate_limit.py`) guards `register`, `login`,
  `refresh`, `forgot-password`, and `reset-password`, keyed by client IP —
  correct for the current single-process deployment
  (`infra/docker/backend.Dockerfile` runs no `--workers`); no
  PostgreSQL-backed counters were needed yet. Per-IP limiting does not stop
  a distributed low-rate attempt to guess a reset token, but the token
  space (256 bits) makes that infeasible regardless of request rate.
- **Designed, not yet implemented:** horizontal scale-out (more than one
  backend instance behind a load balancer) breaks the in-process limiter's
  core assumption — a verified, deterministic architectural fact, not a
  hypothetical one, but *not* itself the "measured requirement" evidence
  bar [ADR 0001](DECISIONS/0001-modular-monolith-over-microservices.md)
  sets for adopting new infrastructure in *production* (no such measurement
  exists yet — see ADR 0006 §1). This ADR treats that architectural
  certainty as sufficient to justify a *design*, a lower bar than
  production adoption. The full design is documented in
  [ADR 0006](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md):
  Redis-backed token-bucket rate limiting plus a deterministic (non-ML),
  rule-based abuse-detection layer, an operation-aware Redis failure
  policy, and a key design that never stores raw credentials.
- **Redis-backed distributed rate limiting implemented, committed,
  pushed, and merged into `main` — both the engine and its endpoint
  wiring:** Slice 1 (squash commit `46ef03b` via PR #11) added the
  multi-key atomic Lua token-bucket engine (`RedisTokenBucketLimiter`,
  ADR §8/§10), a Redis connection abstraction, centralized key
  construction with a keyed-HMAC (not plain-hash) email identifier (ADR
  §14), and a trusted-proxy-aware IP resolver (`resolve_client_ip()`, ADR
  §9a — secure-by-default: `X-Forwarded-For` ignored unless the peer is
  within a configured trusted CIDR). Slice 2 (squash commit `5391a78` via
  PR #12) wired all of it into every `enforce_*_rate_limit` dependency —
  `register`, `login`, `refresh`, `forgot-password`, `reset-password` now
  all attempt the Redis engine first, using ADR §9's exact per-operation
  dimensions — IP always; the submitted email, as a keyed-HMAC
  identifier, for `login`/`forgot-password`; the session ID, parsed from
  the refresh-token cookie without a database round-trip, for
  `refresh` — falling back to the in-process limiter per ADR §13's
  operation-aware policy when Redis is unreachable. **This is now active
  in the committed codebase on `main`.** One implementation-time
  refinement of §13, recorded with rationale in ADR 0006's "Implementation
  status" and `SOLVING.md`: an unconfigured Redis always falls back to
  the in-process limiter, for every operation including `register`;
  §13's literal Tier B fail-open is reserved for a genuine mid-request
  outage of an *already-configured* Redis. A structured log line fires on
  a genuine Redis-failure fallback (ADR §13's own requirement —
  `app.rate_limit` logger, `operation`/`policy` fields only, never a
  request-derived value). Tested: 183 backend tests (119 pre-Redis + 51
  Slice 1 + 13 Slice 2), verified locally against real Postgres + real
  Redis and via GitHub Actions CI on PR #12 (backend/frontend/Docker-build
  checks all passed). **The deterministic abuse-detection layer (ADR §11)
  is now live**, merged in two further slices on top of the above: Slice
  3a (`app/core/abuse_state.py`/`abuse_keys.py`, merged PR #13) added the
  low-level Redis primitives; Slice 3b (`app/core/abuse_decision.py`,
  merged PR #14) wires the R1–R5 rule table into `login`/
  `forgot-password`/`reset-password` (not `register`/`refresh` — no rule
  targets them) — a `TEMPORARY_BLOCK` (R3: 5 distinct source IPs against
  one account; R5: 15 reset-password validation failures from one IP)
  rejects outright before the base bucket is even consulted; a
  `STRICT_THROTTLE` (R1/R2/R4) is enforced via a second, stricter token
  bucket folded into the same atomic `check_all()` call as the base
  bucket. A successful login resets the account-scoped failure counter
  and distinct-IP signal (R2/R3) but never the IP-scoped counter (R1) or
  an already-active escalation. Every threshold/window (§11) and the
  strict/block bucket shapes (§12) are recorded, with rationale, in ADR
  0006's "Resolved during the abuse-layer design/readiness review"
  subsection. Redis's role remains strictly limited to ephemeral
  rate-limit/abuse state; PostgreSQL remains the only durable datastore
  (ADR 0002) — Redis never becomes a second source of truth for users,
  sessions, workspaces, or audit logs.

## Upload & document safety

- Validate MIME type, file extension, and size before processing.
- Reject or safely handle malformed/corrupt documents without crashing the
  ingestion pipeline.
- Store uploaded files using generated identifiers, not user-supplied
  filenames, to avoid path traversal and collision issues.
- Apply resource and time limits to parsing/processing to bound the impact
  of a pathological file.

**Implemented (Issue #3, Slice 3.2 — storage layer):** the
generated-identifier/path-traversal requirement above is enforced by
`StorageProvider`/`LocalStorage` (`backend/app/services/storage_provider.py`)
— every key is checked against escaping the configured storage root
(rejecting empty keys, absolute paths, `..` segments, and symlink-based
escapes, since `relative_to()` runs against the fully symlink-resolved
candidate path). Every operation (`save`/`read`/`delete`/`exists`) also
guards its own filesystem calls: a raw `OSError`/`PermissionError` —
including the absolute configured storage root that would otherwise
appear in its message — never escapes the module; it's translated to
`StorageError` (unsafe key: `StorageKeyError`) referencing only the
caller-supplied key.

**Implemented (Issue #3, Slice 3.3 — the upload endpoint itself,**
`POST /api/v1/workspaces/{workspace_id}/documents`,
`backend/app/services/document_service.py`**):**

- MIME/extension validation, per docs/API_CONTRACT.md's exact allowlist
  (PDF/DOCX/TXT/Markdown/CSV) — plus a magic-byte signature check for
  the two binary formats with a real, stable signature (PDF, DOCX);
  plain-text formats have none, and this is documented as a real gap,
  not silently pretended away. None of these three signals individually
  or together prove the file is well-formed or safe to parse — only
  that it's consistent with the claimed type; genuine malformed-content
  handling is a later slice's job (the extraction step).
- Size enforced by `max_upload_size_bytes` (default 50 MiB) while
  *streaming* the upload — a running total checked chunk by chunk,
  never a full buffer-then-check.
- The client-supplied filename is used only for display and to pick
  which validator applies — never as, or as part of, a storage path.
  The generated storage key is built only from the workspace ID,
  document ID, and the validated (not raw) extension.
- Storage always succeeds before any database row is created. A
  database failure after a successful storage write (including a
  duplicate-checksum race the pre-check didn't catch) triggers a
  best-effort compensating delete of the just-written object; the
  document row is never committed unless the file write already durably
  succeeded. A compensating-delete failure is logged (identifiers only,
  never a path) and never re-surfaces in place of the original error.
- Workspace-scoped duplicate detection (`UNIQUE(workspace_id,
  checksum_sha256)`, Slice 3.1) — a duplicate upload in the same
  workspace is rejected with the existing document's ID; the same
  content in a different workspace is unaffected, since both the
  pre-check and the constraint are workspace-scoped.
- Rate-limited (`document_upload` operation, IP + authenticated user ID,
  the existing Redis token-bucket engine with the same Tier A
  never-fail-open fallback policy as `login`/`refresh`/
  `forgot-password`/`reset-password`) and audited
  (`AuditEvent.DOCUMENT_UPLOADED`, `backend/app/core/audit.py`) exactly
  once per successful upload.
- Not yet implemented, deliberately out of this slice's scope: any
  document-level authorization beyond the standard workspace role check
  (no per-document ACLs exist).

**Implemented (Issue #3, Slice 3.4 — text extraction,**
`POST /api/v1/workspaces/{workspace_id}/documents/{document_id}/process`,
`backend/app/ingestion/extraction.py` +
`backend/app/services/document_service.py::process_document`**):** every
uploaded document is treated as untrusted input at extraction time, not
just at upload time.

- **Malformed/corrupt document handling**: every parser failure (pypdf,
  python-docx, `zipfile`, `csv`, a text-decode error, or any other
  unexpected exception) is caught and normalized to a `FAILED` status
  with a short, generic `failure_reason` — never a crash, never a raw
  library exception, filesystem path, or storage key reaching the
  client. The endpoint itself always returns `200`; a parsing failure is
  an expected, handled outcome recorded on the document row, not a
  request-level error.
- **DOCX zip-bomb / path-traversal defense**: DOCX is a ZIP container, so
  a `%PDF-`/`PK\x03\x04`-style signature match at upload time says
  nothing about safety at parse time. Before `python-docx` ever runs, a
  pre-flight check reads only ZIP central-directory metadata
  (`ZipInfo.file_size`/`.filename` — no member is decompressed) and
  rejects: any member name containing `..` or starting with `/`
  (traversal), any single member's declared uncompressed size over 50
  MiB, a total declared uncompressed size over 200 MiB (the zip-bomb
  case — a highly compressible member can have a tiny on-disk footprint
  and a huge declared size), and more than 2000 members. Real DOCX
  content is read only in-memory via `BytesIO`, never extracted to disk.
- **PDF resource limits**: page count capped at 2000; per-page text
  extraction is wrapped so one malformed page's parser exception doesn't
  crash the whole document. **Known limitation, documented not hidden**:
  no wall-clock/CPU timeout exists for a single pathological PDF's parse
  — true preemption of synchronous CPU-bound work inside an async
  handler would be a disproportionate addition for this slice; the page
  cap is the primary bound.
- **Output-size bound**: extracted text is capped at 20 MiB regardless of
  format, independent of the (already-enforced) 50 MiB upload-size
  limit — a small-but-pathological input (e.g. a PDF that expands
  unusually on extraction) still can't produce unbounded extracted text.
- **TXT/Markdown/CSV**: decoded with `errors="replace"` — an invalid byte
  sequence never raises, never crashes extraction; CSV additionally
  bounds per-field size via Python's own `csv` module default, raising a
  normalized `ExtractionError` (not a crash) if exceeded.
- Extraction reads exclusively through `StorageProvider`, using the
  server-generated storage key — the client-supplied filename is never
  touched again at this stage beyond having already picked the extension
  at upload time.
- **Crash safety**: the document's `PROCESSING` transition is committed
  as its own database transaction *before* extraction is attempted, so a
  process crash or restart mid-parse leaves the document at `PROCESSING`
  (itself treated as retriable) rather than falsely appearing `PARSED`.
- Rate-limited (`document_process` operation, same IP + user-ID
  dimensions and Tier A policy as `document_upload`, since extraction is
  CPU-bound and a repeat-triggerable resource cost) and audited
  (`AuditEvent.DOCUMENT_PARSED` on success,
  `AuditEvent.DOCUMENT_PARSING_FAILED` on failure — metadata never
  includes a raw exception, filesystem path, or storage key).
- Chunking, embeddings, and vector indexing are implemented — see below.
  All remain synchronous, within the request; no background/queued
  processing exists anywhere in this pipeline.

**Implemented (Issue #3, Slices 3.5–3.7 — chunking, cleaning, embedding,
indexing,** `backend/app/ingestion/chunking.py` +
`backend/app/ingestion/cleaning.py` + `backend/app/ingestion/embedding.py`
**):**

- **Chunking resource limits**: a `_MAX_CHUNKS_PER_DOCUMENT` ceiling
  (checked incrementally, not just once per section) bounds a single
  document's chunk count regardless of chunk-size configuration; every
  chunk size is itself bounded by `max_chunk_size`. Chunking is a pure,
  offline transformation — no network call, no filesystem access, no
  database dependency — so it inherits no new attack surface beyond the
  already-bounded extracted-text size (20 MiB, see above).
- **Cleaning is total and conservative by construction**: `clean()`
  never raises for any valid input, never removes semantic content,
  punctuation, or Unicode, and performs only safe, reversible-in-intent
  normalization (line endings, whitespace, blank-line runs) — there is
  no code path in this module that can leak, execute, or otherwise treat
  document content as anything other than inert text.
- **Embedding never leaves the process**: `LocalHashingEmbeddingProvider`
  makes no network call and needs no API key — document content is
  never sent to an external service at this stage. `embed_with_retry()`'s
  backoff/retry path only applies to a future networked provider's own
  transient failures; the shipped provider cannot fail transiently.
  Embedding vectors are numeric only — no chunk text or metadata beyond
  what `document_chunks` already stores is exposed by this stage.
- **Indexing (pgvector HNSW) introduces no new attack surface**: the
  index is maintained transactionally by Postgres itself as part of the
  same `UPDATE` that writes each embedding vector; no separate process,
  endpoint, or credential is involved.
- **Zero-extractable-content documents fail explicitly**: a document
  with no chunks (an empty file, or content that extracts to nothing)
  is reported as `FAILED` with a clear, generic reason rather than
  silently reaching `READY` — this is a correctness/UX property, not a
  security control, but it avoids a document silently existing in a
  state where retrieval could return nothing without explanation.
- Rate-limited and audited exactly as extraction is (same
  `document_process` operation covers the whole pipeline in one call);
  new audit events: `AuditEvent.DOCUMENT_CHUNKED`/`DOCUMENT_CHUNKING_FAILED`/
  `DOCUMENT_CLEANING_FAILED`/`DOCUMENT_EMBEDDING_FAILED`/`DOCUMENT_READY` —
  metadata never includes raw chunk content, embedding vectors, a raw
  exception, filesystem path, or storage key.

## Retrieval workspace isolation

**Implemented (GitHub Issue #4, Slice 4.2 —
`backend/app/retrieval/{dense,lexical,service}.py`):** every retrieval
query (`dense_search()`, `lexical_search()`, and the `hybrid_search()`
orchestrator that composes them) filters by `workspace_id` at the SQL
level — a `WHERE workspace_id = ...` clause on the query itself, never a
filter applied to results after the fact. A chunk from another workspace
is never returned, never scored, never reaches fusion/reranking; this
was verified directly with real cross-workspace test data (`tests/test_retrieval.py`),
not just asserted from the query's own shape. Both queries also join
`documents` and require `status = READY`, so a document still mid-
ingestion (e.g. `CHUNKED` but not yet embedded) never surfaces partial
or inconsistent results, and an optional `document_id` metadata filter
composes safely with the workspace filter (a `document_id` from another
workspace, combined with the caller's own `workspace_id`, simply matches
zero rows — no separate validation needed at this layer, though the
future API endpoint calling this module is still responsible for its
own authorization/ownership checks before invoking it, same as every
other workspace-scoped endpoint in this codebase).

## Prompt injection defense

Because retrieved chunks are untrusted, the generation layer's design must
assume a malicious document could contain text like "ignore previous
instructions" or attempts to exfiltrate other users' data. Mitigations
applied (GitHub Issue #4, Slice 4.3): `LLMProvider.generate()`
(`backend/app/generation/llm_provider.py`) takes `system_prompt`/
`context`/`query` as three structurally separate arguments, never one
concatenated string; the shipped `LocalGroundedExtractiveProvider` never
grants itself (or could be induced to grant) any tool/data access beyond
quoting the evidence it was given, and never interprets retrieved
content as instructions — it treats it as inert text to quote, by
construction, not by a runtime filter that could have gaps.

**Implemented (Issue #4, Slice 4.4 — `backend/tests/test_prompt_injection.py`):**
a 12-payload corpus covering direct "ignore previous instructions,"
fake system messages, requests to reveal the system prompt, requests to
expose secrets/environment variables, malicious instructions disguised
as legitimate documentation, indirect injection embedded inside a
quoted example, instructions conflicting with the user's own query,
claims that a document has authority to override application policy, a
roleplay/persona jailbreak attempt, a request to grant expanded tool/
filesystem access, a cross-workspace data-exfiltration request phrased
as document content, and a fake "end of context" marker attempting to
inject a spoofed trailing system message. Tested at two levels: the
provider directly (every payload in the corpus, proving the answer is
always exactly the fixed template with the payload appearing only as
quoted evidence — never a different response shape, never "obeyed")
and the full HTTP pipeline (four representative payloads, each ingested
as a real document's entire content, then asked about through the real
`/conversations/.../messages` endpoint — proving the invariant holds
end-to-end, not just at the provider in isolation). The corpus and its
tests are explicitly designed to remain the right regression surface
once a real (non-extractive) `LLMProvider` is ever added — a provider
that *could* be persuaded by injected text would need to be caught by
re-running this same corpus against it, not a new one invented later.

## Secret management

- Real secrets are never committed; `.env.example` lists variable names
  with empty/placeholder values only.
- Configuration loading should fail loudly (not silently default) if a
  required secret is missing in a non-development environment.

## Errors and information disclosure

- User-facing errors are generic and actionable ("upload failed — file too
  large") without stack traces, file paths, query text, or internal IDs
  that aren't meant to be public.
- Detailed error information goes to logs/observability (see
  [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) §"Observability"), not to the
  response body.

## Audit logging

**Implemented (Issue #2, extended by Redis abuse-protection Slice 3c)** —
`backend/app/core/audit.py` (`AuditEvent` constants, plain strings for
extensibility) and `backend/app/repositories/audit_log_repository.py`.
Captured today: registration, login success/failure, logout, session
revocation, refresh-token reuse detection, password-reset
request/success, workspace create/delete/membership changes,
authorization denials, and (Slice 3c) abuse-layer escalations —
`AuditEvent.RATE_LIMITED` on a `STRICT_THROTTLE` transition (R1/R2/R4)
and `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` on a `TEMPORARY_BLOCK`
transition (R3/R5), emitted exactly once per escalation (never on an
already-escalated repeat) from `app/api/v1/auth.py`'s `login`/
`forgot-password`/`reset-password` endpoints, after the real request
outcome is known — never for an ordinary `ALLOW`, never for the base
rate limiter's own ordinary throttling. Metadata is limited to the rule
ID, operation, dimension, the already-HMAC-hashed account identifier
(never a raw email) when the dimension is account-scoped, and the block
TTL where applicable — never a raw password, token, or other secret.
`user_id` is `None` for these two event types (the abuse layer never has
a resolved user at the point it escalates). Audit writes commit
immediately and independently of the surrounding request's transaction,
so a denial's (or escalation's) audit record survives even when the
request goes on to raise an error. `user_id`/`workspace_id` use `ON
DELETE SET NULL` so the audit trail outlives the account/workspace it
references. **`AuditEvent.DOCUMENT_UPLOADED` is implemented** (Issue #3,
Slice 3.3) — emitted exactly once per successful upload, from the
document row's own committing transaction (see "Upload & document
safety" above for the exact metadata and the transaction-consistency
detail). **`AuditEvent.DOCUMENT_PARSED`/`DOCUMENT_PARSING_FAILED` are
implemented** (Issue #3, Slice 3.4) — emitted exactly once per
`/process` call, on the extraction outcome (never on an already-`PARSED`
`409` rejection, which never reaches the extraction step at all); see
"Upload & document safety" above for the exact metadata. Document-delete
and other document-lifecycle audit events will be added when those
surfaces exist.

## Security testing

Per `AGENTS.md` §3, security assumptions are verified, not just documented:

- **Cross-workspace access tests** — attempt to read/write another
  workspace's documents, conversations, and collections; must fail.
  **Implemented (Issue #2)** for workspaces/membership themselves —
  `backend/tests/test_workspaces.py` proves a non-member gets `404` (never
  `403`, never real data) on every workspace-scoped endpoint. **Extended
  to documents (Issue #3, Slices 3.3–3.4)** —
  `backend/tests/test_document_upload.py` proves the same 404-not-403
  behavior for document upload, and that a duplicate-checksum match in
  one workspace never affects or is visible from another;
  `backend/tests/test_document_processing.py` proves the same for
  `/process` — a document ID from one workspace is unreachable through
  another workspace's ID, even for a real member of that other
  workspace. Conversations/collections don't exist yet.
- **Malicious upload tests** — oversized files, mismatched
  extension/content, malformed PDFs/DOCX, zip-bomb-style payloads; must be
  rejected or safely contained. **Implemented (Issue #3, Slices 3.3–3.4)**
  — `backend/tests/test_document_upload.py` covers oversized uploads,
  extension/MIME/signature mismatches, and malformed multipart input.
  Genuinely malformed *internal* document structure and zip-bomb-style
  decompression risk are covered by Slice 3.4's extraction tests:
  `backend/tests/test_extraction.py` (unit-level — malformed PDF/DOCX,
  four archive-member-traversal name patterns, per-member/total/
  member-count ZIP limits including one real highly-compressible
  60 MB→~50 KB zip-bomb-shaped member rejected at the real default
  threshold, a malformed CSV exceeding the field-size limit, invalid
  UTF-8 byte sequences) and `backend/tests/test_document_processing.py`
  (HTTP-level — malformed PDF/DOCX/CSV and a DOCX archive-traversal
  attempt each transition the document to `FAILED` with a `200`
  response and a safe `failure_reason`, never a `500` or a crash).
- **Prompt injection tests** — documents containing instruction-like text
  ("ignore the above," attempts to leak system prompt or other users'
  data); the system must not comply with injected instructions. Not
  implemented — no generation surface exists yet (Issue #4).
- **Auth bypass tests** — attempt to access protected endpoints without a
  valid session, with an expired session, or with a session from a
  different workspace. **Implemented (Issue #2)** —
  `backend/tests/test_auth.py` covers missing/garbage/expired/wrong-signature
  access tokens and revoked refresh tokens; `test_workspaces.py` covers a
  valid session with no membership in the target workspace.
- **Path traversal tests** — filenames/paths like `../../etc/passwd` must
  be neutralized. **Implemented** — `backend/tests/test_storage_provider.py`
  (Slice 3.2, the storage layer itself: empty/absolute/`..`-containing
  keys and symlink-based escapes, all rejected on every operation) and
  `backend/tests/test_document_upload.py` (Slice 3.3, end to end: a
  `../../etc/passwd.pdf` filename uploaded through the real endpoint
  lands safely at the generated key, never influencing the storage path).
- **Rate limiting tests** — confirm limits actually trigger under load on
  login and expensive endpoints. **Implemented (Issue #2)** —
  `backend/tests/test_auth.py` drives `register`/`login`/`refresh`, and
  `backend/tests/test_password_reset.py` drives `forgot-password`/
  `reset-password`, past their limits and asserts `429`. **Extended to
  document upload (Issue #3, Slice 3.3)** —
  `backend/tests/test_document_upload.py` drives real uploads past the
  `document_upload` limit (20/60s) and asserts `429`, proves the real
  Redis IP/user dimension keys are created, and proves the Tier A
  fallback (a genuinely unreachable Redis) still enforces the same
  threshold rather than failing open.
- **CSRF tests** — missing/mismatched token rejected, valid token accepted,
  safe methods exempt, login/register themselves protected (login CSRF),
  a token from one client's cookie jar rejected against another's request.
  **Implemented (Issue #2)** — `backend/tests/test_csrf.py`,
  `backend/tests/test_cookie_security.py` (also asserts the actual
  `Set-Cookie` attributes: `HttpOnly`/`Path`/`SameSite`, and that the CSRF
  cookie is deliberately not `HttpOnly`), and
  `backend/tests/test_password_reset.py` (CSRF specifically on
  `forgot-password`/`reset-password`).
- **Cookie-only authentication tests** — an `Authorization: Bearer` header
  alone (no cookie) must not authenticate, and must not satisfy CSRF
  either. **Implemented (Issue #2)** — `backend/tests/test_cookie_security.py`.
- **Password-reset security tests** — enumeration resistance (same
  response/timing for known vs. unknown email), single-use/expired/invalid
  token rejection, session invalidation after reset, a token issued for one
  user never affecting another user. **Implemented (Issue #2)** —
  `backend/tests/test_password_reset.py`.

The remaining tests (malicious upload, prompt injection, path traversal)
are written alongside their corresponding feature per the Definition of
Done in `AGENTS.md` §7, not deferred to a later "security phase."

## Related documents

- [`docs/REQUIREMENTS.md`](REQUIREMENTS.md) — functional security
  requirements (auth, workspaces).
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — where security-relevant code
  lives (`core/`, `api/` dependencies).
- [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) — generation-layer design where
  prompt injection defense is applied.
- [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  — the authentication/session model referenced above.
- [`docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md`](DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  — the cookie/CSRF delivery model, and the "different origin ≠ cross-site"
  distinction governing deployment configuration.
- [`docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md`](DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
  — the Redis rate-limiting/abuse-protection design referenced above
  (design only; not yet implemented).
