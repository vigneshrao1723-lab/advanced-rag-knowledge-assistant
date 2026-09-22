# API Contract

**Status:** PARTIALLY IMPLEMENTED — `/api/v1/health` (Issue #1) and
`/api/v1/auth`, `/api/v1/users`, `/api/v1/workspaces` (Issue #2 —
Authentication & Workspaces) are implemented, with the concrete
request/response schemas below. Every other namespace remains PROPOSED /
target only; this document records the intended API namespace layout to
keep future implementation consistent, not a claim that those endpoints
exist. See [`PROJECT_STATE.md`](../PROJECT_STATE.md) for current status.

## Conventions (intended)

- REST-style JSON API under `/api/v1/`.
- Authentication uses short-lived access tokens (15 min default,
  `ACCESS_TOKEN_EXPIRE_MINUTES`) backed by server-tracked refresh/session
  records (30 days default, `REFRESH_TOKEN_EXPIRE_DAYS`) — the architecture
  is **not** purely stateless. See
  [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  for the full model. **Delivery mechanism (superseded — see
  [ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md)):**
  both tokens are delivered exclusively via `HttpOnly` cookies, never in a
  response body or an `Authorization` header — the original response-body
  design this section once described was replaced before this API had any
  external consumers. A separate, non-`HttpOnly` `csrf_token` cookie plus
  an `X-CSRF-Token` header (double-submit pattern) is required on every
  state-changing request, including `login`/`register` themselves. This
  API is currently designed for the first-party browser client only; a
  future non-browser client would need its own token-delivery path, not a
  weakening of this one. Passwords are hashed with Argon2id — see
  [ADR 0004](DECISIONS/0004-password-hashing-argon2id.md).
- All endpoints except `/api/v1/auth/*` and `/api/v1/health` require a valid
  session and are scoped to the caller's workspace(s), enforced server-side
  (see [`docs/SECURITY.md`](SECURITY.md)).
- Request/response bodies validated with Pydantic (backend) and Zod
  (frontend).
- Errors return a consistent shape without leaking stack traces or internal
  details (see [`docs/SECURITY.md`](SECURITY.md) §"Errors").

## Target namespaces

| Namespace | Purpose |
|---|---|
| `/api/v1/auth` | Registration, login, logout, refresh-token rotation, session/device listing and revocation, password recovery (**implemented**, Issue #2) |
| `/api/v1/users` | Profile and settings management (**partially implemented** — `GET /me` only, Issue #2) |
| `/api/v1/workspaces` | Create/rename/delete/switch workspaces, membership, roles (**implemented**, Issue #2) |
| `/api/v1/workspaces/{workspace_id}/audit-logs` | Query security-relevant audit log entries for a workspace (`ADMIN`/`OWNER` only) |
| `/api/v1/workspaces/{workspace_id}/documents` | Upload + synchronous text extraction, including retrying a `FAILED` document via the same `/process` endpoint (**implemented**, Issue #3 Slices 3.3–3.4); list, search, filter, sort, rename, delete, re-index, download, metadata/status (not yet implemented). Nested under the owning workspace, matching `/workspaces/{workspace_id}/members` and `/audit-logs`'s existing convention, rather than the flat `/api/v1/documents` this table previously sketched. |
| `/api/v1/collections` | Logical document grouping and collection-scoped retrieval |
| `/api/v1/ingestion` | Ingestion pipeline status/control for a document |
| `/api/v1/search` | Standalone search mode (snippets, evidence, scores, retrieval method) |
| `/api/v1/retrieval` | Lower-level retrieval operations (used internally by chat/search) |
| `/api/v1/conversations` | Chat sessions, messages, regenerate/retry, feedback |
| `/api/v1/evaluations` | Trigger and inspect evaluation runs and results |
| `/api/v1/voice` | STT/TTS session endpoints, integrated with conversations |
| `/api/v1/health` | Liveness/readiness checks (**implemented**, Issue #1) |

## Implemented: `/api/v1/auth`, `/api/v1/users`, `/api/v1/workspaces`

All request/response bodies are JSON. Authentication is **cookie-based**
(`access_token`/`refresh_token` `HttpOnly` cookies — see
[ADR 0005](DECISIONS/0005-httponly-cookie-csrf-authentication.md)), not a
bearer header — the client never sends or receives a token value directly.
Every state-changing request below also requires a valid CSRF pairing
(`csrf_token` cookie + matching `X-CSRF-Token` header), obtained via
`GET /api/v1/auth/csrf`; omitted from the table below since it applies
uniformly rather than per-endpoint.

### Auth

| Endpoint | Auth | Body / params | Response |
|---|---|---|---|
| `GET /api/v1/auth/csrf` | none | — | `204` — bootstraps the `csrf_token` cookie if the caller doesn't already have one |
| `POST /api/v1/auth/register` | none (rate-limited) | `{email, password}` | `201` `AuthResponse`; sets auth cookies |
| `POST /api/v1/auth/login` | none (rate-limited) | `{email, password}` | `200` `AuthResponse`; sets auth cookies, or `401` (generic "incorrect email or password" — same message whether the account exists or not, to resist enumeration) |
| `POST /api/v1/auth/refresh` | refresh cookie | — (reads `refresh_token` cookie) | `200` `AuthResponse`; rotates auth cookies, or `401` if the cookie is missing/invalid/expired/revoked. Reusing an already-rotated-out refresh token revokes that session entirely. |
| `POST /api/v1/auth/logout` | refresh cookie (optional) | — | `204` (always — idempotent/best-effort even with no/an already-invalid cookie); clears auth cookies |
| `GET /api/v1/auth/sessions` | access cookie | — | `200` `SessionInfo[]` — every non-revoked session for the caller, `is_current` flags the session tied to the presented access token |
| `DELETE /api/v1/auth/sessions/{session_id}` | access cookie | — | `204`, or `404` if the session doesn't exist or belongs to another user (same response either way — never confirms another user's session IDs) |
| `POST /api/v1/auth/forgot-password` | none (rate-limited) | `{email}` | `200` `{message}` — always the same generic message/status regardless of whether the email exists |
| `POST /api/v1/auth/reset-password` | none (rate-limited) | `{token, new_password}` | `204`, or `400` with `{error: {code: "reset_token_invalid" \| "reset_token_expired" \| "reset_token_already_used", message}}`. Success revokes every existing session for the account. |

`AuthResponse`: `{user: UserRead}` — no token fields; tokens are cookies
only.
`SessionInfo`: `{id, device_label, created_at, last_used_at, expires_at, is_current}`.

### Users

| Endpoint | Auth | Response |
|---|---|---|
| `GET /api/v1/users/me` | access cookie | `200` `UserRead` = `{id, email, created_at}` |

### Workspaces

Every endpoint below resolves `workspace_id` through a server-side
membership check first — a non-member and a nonexistent workspace both
produce `404` (never `403`), so a `workspace_id` never confirms a
workspace's existence to someone who isn't in it.

| Endpoint | Min. role | Body | Response |
|---|---|---|---|
| `POST /api/v1/workspaces` | any authenticated user | `{name}` | `201` `WorkspaceRead` (caller becomes `OWNER`) |
| `GET /api/v1/workspaces` | any authenticated user | — | `200` `WorkspaceRead[]` (only workspaces the caller belongs to) |
| `GET /api/v1/workspaces/{workspace_id}` | VIEWER | — | `200` `WorkspaceRead` |
| `PATCH /api/v1/workspaces/{workspace_id}` | ADMIN | `{name}` | `200` `WorkspaceRead` |
| `DELETE /api/v1/workspaces/{workspace_id}` | OWNER | — | `204` |
| `GET /api/v1/workspaces/{workspace_id}/members` | VIEWER | — | `200` `MemberRead[]` |
| `POST /api/v1/workspaces/{workspace_id}/members` | ADMIN | `{email, role}` | `201` `MemberRead`, or `403` if the role being assigned exceeds the caller's authority (see the authorization matrix below) |
| `PATCH /api/v1/workspaces/{workspace_id}/members/{user_id}` | ADMIN | `{role}` | `200` `MemberRead` |
| `DELETE /api/v1/workspaces/{workspace_id}/members/{user_id}` | VIEWER (self-leave always allowed; removing someone else requires the matrix below) | — | `204` |

`WorkspaceRead`: `{id, name, created_at, updated_at, my_role}`.
`MemberRead`: `{user_id, email, role, created_at}`.

#### Workspace authorization matrix

Docs (`docs/REQUIREMENTS.md`) name the four roles without fully specifying
the edges between them; this is the conservative, implemented resolution
(`backend/app/services/workspace_service.py`):

- **OWNER** — full control: rename, delete, add/remove any member, change
  any role. A workspace may never be left with zero OWNERs (demoting or
  removing the last one is rejected with `409`).
- **ADMIN** — rename the workspace; add/remove `MEMBER`/`VIEWER` members;
  change roles only between `MEMBER` and `VIEWER`. Cannot touch
  `OWNER`/`ADMIN` membership, promote anyone to `OWNER`/`ADMIN`, or delete
  the workspace.
- **MEMBER / VIEWER** — read-only on the workspace and its membership.
  Any member (any role) can always remove themselves ("leave"), subject to
  the last-owner rule above.

### Rate limiting

`register`, `login`, `refresh`, `forgot-password`, and `reset-password`
are rate-limited per client IP (in-process, fixed-window — see
`docs/SECURITY.md` "Rate limiting approach"): `429` once the limit is
exceeded. No rate-limit headers are emitted yet. This remains in-process
only (correct for the current single-process deployment) — Redis-backed
distributed rate limiting has not been implemented yet.

### Error shape

Every error response (auth and workspaces included) uses the shared shape
from Issue #1: `{"error": {"code", "message", "request_id"}}` — see
`docs/SECURITY.md` "Errors and information disclosure."

## Implemented: `/api/v1/workspaces/{workspace_id}/documents`

**Upload + text extraction** (GitHub Issue #3, Slices 3.3–3.4) —
list/search/filter/sort/rename/delete/re-index/download/metadata are not
implemented yet. Documents reach `UPLOADED` (upload) then `PARSED` or
`FAILED` (processing); no chunking or embedding exists.

| Endpoint | Min. role | Body | Response |
|---|---|---|---|
| `POST /api/v1/workspaces/{workspace_id}/documents` | MEMBER | `multipart/form-data`, one field: `file` | `201` `DocumentRead`, or `400`/`409`/`413`/`429`/`500` (see below) |
| `POST /api/v1/workspaces/{workspace_id}/documents/{document_id}/process` | MEMBER | none | `200` `DocumentRead`, or `404`/`409`/`429`/`500` (see below) |

`DocumentRead`: `{id, filename, mime_type, size_bytes, checksum_sha256, status, page_count, failure_reason, created_at, updated_at}` — never `storage_key` (internal only).

Resolves `workspace_id` through the same `require_workspace_role`
dependency every other workspace-scoped route uses — a non-member or
nonexistent workspace produces `404` (never `403`, never leaks
existence), matching the rest of this document.

**Supported formats:** PDF, DOCX, TXT, Markdown, CSV only — extension
(case-insensitive), client-supplied MIME type (a small named allowlist,
including known browser variants for `.md`/`.csv`), and a magic-byte
signature check (PDF/DOCX only — no reliable signature exists for the
plain-text formats) must all be consistent with the claimed type. This
is a lightweight consistency check, not a parser — it does not prove the
file is well-formed or safe to parse; real parsing is a later slice's
job, and a malformed-but-signature-matching file is expected to be
caught there, not here.

**Size limit:** `max_upload_size_bytes` (default 50 MiB), enforced while
streaming the upload — a chunk-by-chunk running total, never buffering
an oversized payload first.

**Duplicates:** `documents` has `UNIQUE(workspace_id, checksum_sha256)`
— re-uploading identical content into the same workspace returns `409`
referencing the existing document's `id`; the same content in a
*different* workspace succeeds (the constraint, and the pre-check that
backs it, are both workspace-scoped).

**Storage/database consistency:** the file is always written via
`StorageProvider` before any database row is created. If the database
insert then fails for any reason (including losing a duplicate-checksum
race that the pre-check didn't catch), the just-written storage object
is deleted on a best-effort basis and the failure is translated to the
documented `409`/`500` — the database row is never committed unless the
storage write already durably succeeded first. See
`backend/app/services/document_service.py` for the exact sequence.

**Rate limiting:** a dedicated `document_upload` operation (Redis token
bucket, falling back to the existing in-process limiter — the same
Tier A policy as `login`/`refresh`/`forgot-password`/`reset-password`,
never failing open), dimensioned by IP and the authenticated user ID,
20 requests/60s. The deterministic R1–R5 abuse-detection layer (ADR
0006) is not consulted — its rule table targets the
login/forgot-password/reset-password credential-stuffing threat model
specifically, not file uploads.

**Audit:** `AuditEvent.DOCUMENT_UPLOADED`, emitted exactly once per
successful upload, metadata limited to `document_id`/`filename`/
`mime_type`/`size_bytes`/`checksum_sha256` — never the storage key, a
filesystem path, or file content.

### `POST /api/v1/workspaces/{workspace_id}/documents/{document_id}/process` (Slice 3.4)

Synchronous text extraction for the same five formats (PDF, DOCX, TXT,
Markdown, CSV) — no background job/queue exists; the request blocks
until extraction finishes or fails. Callable when the document is
`UPLOADED`, `PROCESSING` (a prior attempt was interrupted and never
reached `PARSED`/`FAILED` — treated as retriable, not stuck), or
`FAILED` (explicit retry). Returns `409` (`document_already_processed`)
if the document is `PARSED` or any later lifecycle state. Returns `404`
if the document doesn't exist or doesn't belong to `workspace_id`
(same non-leaking pattern as workspace lookup itself).

**This always returns `200`, even when extraction fails** — a malformed
or corrupt document is an expected, handled outcome (`status: "FAILED"`,
`failure_reason` set to a short, generic, storage-safe string), not a
server error. Only a genuinely unexpected condition (auth, lookup,
already-processed, rate limit, an unhandled server fault) produces a
non-`200` status.

**Crash safety:** the `PROCESSING` transition is committed as its own
transaction *before* extraction is attempted, so a crash or restart
mid-extraction leaves the document honestly at `PROCESSING` (itself
retriable) rather than falsely appearing `PARSED` or silently reverting
to `UPLOADED`.

**Security (every uploaded file is untrusted input):** extraction reads
through `StorageProvider` only, using the server-generated storage key —
never the client-supplied filename beyond recovering its
already-validated extension. DOCX (a ZIP container) gets a pre-flight
archive-safety check — member count, per-member and total uncompressed
size, and member-name traversal — using only ZIP metadata (`file_size`
from the central directory), before any member is actually decompressed
or `python-docx` runs; this rejects zip-bomb-style and path-traversal
archives cheaply. PDF page count and extracted-text size are both
capped. TXT/Markdown/CSV are decoded with `errors="replace"`, never
raising on invalid byte sequences. No parser failure (pypdf, python-docx,
`zipfile`, `csv`, a decode error) ever reaches the client raw — every
failure path is normalized to a short, generic reason string containing
no filesystem path, no storage key, and no library stack trace. See
`backend/app/ingestion/extraction.py` and
`backend/app/services/document_service.py::process_document` for the
exact limits and ordering.

**Rate limiting:** a dedicated `document_process` operation, same shape
as `document_upload` (IP + authenticated user ID, Tier A, 20/60s) —
processing is CPU-bound, not just I/O, so it gets the same defensive
treatment as upload.

**Audit:** `AuditEvent.DOCUMENT_PARSED` (metadata:
`document_id`/`page_count`/`section_count`) on success,
`AuditEvent.DOCUMENT_PARSING_FAILED` (metadata: `document_id`/`reason`)
on failure — the `reason` is the same storage-safe string returned to
the client, never a raw exception or storage key.

## Related documents

- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — entities these endpoints will
  operate on.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — module responsible for each
  namespace.
- [`docs/SECURITY.md`](SECURITY.md) — authorization rules that apply to
  every namespace above.
- [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  — the `/api/v1/auth` authentication model.
