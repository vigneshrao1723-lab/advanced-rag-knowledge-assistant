# API Contract

**Status:** PROPOSED — no API endpoints are implemented. This document
records the intended API namespace layout only, to keep future
implementation consistent. It is not a claim that any endpoint exists.

## Conventions (intended)

- REST-style JSON API under `/api/v1/`.
- Authentication uses short-lived bearer access tokens backed by
  server-tracked refresh/session records — the architecture is **not**
  purely stateless. See
  [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  for the full model (session listing, revocation, refresh-token
  rotation). Exact token lifetimes and delivery mechanism are finalized
  when authentication is implemented — see [`docs/REQUIREMENTS.md`](REQUIREMENTS.md).
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
| `/api/v1/auth` | Registration, login, logout, refresh-token rotation, session/device listing and revocation |
| `/api/v1/users` | Profile and settings management |
| `/api/v1/workspaces` | Create/rename/delete/switch workspaces, membership, roles |
| `/api/v1/workspaces/{workspace_id}/audit-logs` | Query security-relevant audit log entries for a workspace (`ADMIN`/`OWNER` only) |
| `/api/v1/documents` | Upload, list, search, filter, sort, rename, delete, re-index, retry, download, metadata/status |
| `/api/v1/collections` | Logical document grouping and collection-scoped retrieval |
| `/api/v1/ingestion` | Ingestion pipeline status/control for a document |
| `/api/v1/search` | Standalone search mode (snippets, evidence, scores, retrieval method) |
| `/api/v1/retrieval` | Lower-level retrieval operations (used internally by chat/search) |
| `/api/v1/conversations` | Chat sessions, messages, regenerate/retry, feedback |
| `/api/v1/evaluations` | Trigger and inspect evaluation runs and results |
| `/api/v1/voice` | STT/TTS session endpoints, integrated with conversations |
| `/api/v1/health` | Liveness/readiness checks |

## Not yet defined

Request/response schemas, pagination conventions, rate-limit headers, and
error-code taxonomy are not yet specified. These will be defined alongside
the corresponding backend module's implementation and documented here at
that time — this file will be updated incrementally rather than
speculatively filled in now.

## Related documents

- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — entities these endpoints will
  operate on.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — module responsible for each
  namespace.
- [`docs/SECURITY.md`](SECURITY.md) — authorization rules that apply to
  every namespace above.
- [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  — the `/api/v1/auth` authentication model.
