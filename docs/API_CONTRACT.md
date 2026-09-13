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
- Authentication uses short-lived bearer access tokens (15 min default,
  `ACCESS_TOKEN_EXPIRE_MINUTES`) backed by server-tracked refresh/session
  records (30 days default, `REFRESH_TOKEN_EXPIRE_DAYS`) — the architecture
  is **not** purely stateless. See
  [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  for the full model. **Delivery mechanism (resolved):** both tokens are
  returned in the JSON response body, not cookies — this keeps the API
  usable by non-browser clients and avoids `SameSite`/`Secure` cookie
  complexity for local HTTP dev; revisit via a new ADR if a browser-only
  requirement emerges. Passwords are hashed with Argon2id — see
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
| `/api/v1/auth` | Registration, login, logout, refresh-token rotation, session/device listing and revocation (**implemented**, Issue #2) |
| `/api/v1/users` | Profile and settings management (**partially implemented** — `GET /me` only, Issue #2) |
| `/api/v1/workspaces` | Create/rename/delete/switch workspaces, membership, roles (**implemented**, Issue #2) |
| `/api/v1/workspaces/{workspace_id}/audit-logs` | Query security-relevant audit log entries for a workspace (`ADMIN`/`OWNER` only) |
| `/api/v1/documents` | Upload, list, search, filter, sort, rename, delete, re-index, retry, download, metadata/status |
| `/api/v1/collections` | Logical document grouping and collection-scoped retrieval |
| `/api/v1/ingestion` | Ingestion pipeline status/control for a document |
| `/api/v1/search` | Standalone search mode (snippets, evidence, scores, retrieval method) |
| `/api/v1/retrieval` | Lower-level retrieval operations (used internally by chat/search) |
| `/api/v1/conversations` | Chat sessions, messages, regenerate/retry, feedback |
| `/api/v1/evaluations` | Trigger and inspect evaluation runs and results |
| `/api/v1/voice` | STT/TTS session endpoints, integrated with conversations |
| `/api/v1/health` | Liveness/readiness checks (**implemented**, Issue #1) |

## Implemented: `/api/v1/auth`, `/api/v1/users`, `/api/v1/workspaces`

All request/response bodies are JSON. All authenticated endpoints require
`Authorization: Bearer <access_token>`.

### Auth

| Endpoint | Auth | Body / params | Response |
|---|---|---|---|
| `POST /api/v1/auth/register` | none (rate-limited) | `{email, password}` | `201` `TokenResponse` |
| `POST /api/v1/auth/login` | none (rate-limited) | `{email, password}` | `200` `TokenResponse`, or `401` (generic "incorrect email or password" — same message whether the account exists or not, to resist enumeration) |
| `POST /api/v1/auth/refresh` | none (rate-limited) | `{refresh_token}` | `200` `TokenResponse` (rotated refresh token), or `401` if invalid/expired/revoked. Reusing an already-rotated-out refresh token revokes that session entirely. |
| `POST /api/v1/auth/logout` | none | `{refresh_token}` | `204` (always — logout is idempotent/best-effort even for an already-invalid token) |
| `GET /api/v1/auth/sessions` | bearer | — | `200` `SessionInfo[]` — every non-revoked session for the caller, `is_current` flags the session tied to the presented access token |
| `DELETE /api/v1/auth/sessions/{session_id}` | bearer | — | `204`, or `404` if the session doesn't exist or belongs to another user (same response either way — never confirms another user's session IDs) |

`TokenResponse`: `{access_token, refresh_token, token_type: "bearer", expires_in (seconds), user: UserRead}`.
`SessionInfo`: `{id, device_label, created_at, last_used_at, expires_at, is_current}`.

### Users

| Endpoint | Auth | Response |
|---|---|---|
| `GET /api/v1/users/me` | bearer | `200` `UserRead` = `{id, email, created_at}` |

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

`register`, `login`, and `refresh` are rate-limited per client IP
(in-process, fixed-window — see `docs/SECURITY.md` "Rate limiting
approach"): `429` once the limit is exceeded. No rate-limit headers are
emitted yet.

### Error shape

Every error response (auth and workspaces included) uses the shared shape
from Issue #1: `{"error": {"code", "message", "request_id"}}` — see
`docs/SECURITY.md` "Errors and information disclosure."

## Related documents

- [`docs/DATA_MODEL.md`](DATA_MODEL.md) — entities these endpoints will
  operate on.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — module responsible for each
  namespace.
- [`docs/SECURITY.md`](SECURITY.md) — authorization rules that apply to
  every namespace above.
- [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  — the `/api/v1/auth` authentication model.
