# Security

**Status:** PROPOSED — this document defines the security model the
implementation must satisfy. Application code now exists (GitHub Issue #1 —
Application Foundation), but none of the security controls described below
are implemented yet: there is no authentication/authorization, no workspace
isolation, no upload validation, and no rate limiting, because none of the
surfaces those controls protect (auth, uploads, workspaces) exist yet
either. The Issue #1 foundation does implement generic, non-auth-related
protections already required by this document — centralized error handling
that never leaks stack traces/internal paths (see "Errors and information
disclosure" below) and loud-failure config loading for missing required
settings (see "Secret management" below). See
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

- Passwords hashed with a modern, salted algorithm (algorithm choice to be
  recorded as an ADR when authentication is implemented).
- Short-lived bearer access tokens backed by server-tracked refresh/session
  records — the architecture is **not** purely stateless. See
  [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  for the full model.
- Sessions/devices are listable and individually revocable by the user;
  refresh tokens rotate on use; **logout invalidates the corresponding
  session's refresh capability immediately.**
- Role-based authorization within a workspace: `OWNER`, `ADMIN`, `MEMBER`,
  `VIEWER` — enforced server-side on every workspace-scoped endpoint, not
  just at the UI layer.
- Rate limiting and brute-force protection on login/registration/refresh
  (see "Rate limiting approach" below).

## Rate limiting approach

Rate limiting is a firm requirement (see principle 8 above), but no
external session/cache store is introduced solely to implement it:

- The initial, single-instance deployment may use an in-process mechanism
  (e.g., a token-bucket/sliding-window limiter held in application memory)
  and/or PostgreSQL-backed counters where state must persist across
  restarts or be shared correctly (e.g., login/brute-force attempt
  counters).
- **Redis is not added solely for initial rate limiting** — this would
  contradict the no-premature-infrastructure principle in
  [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) and
  [ADR 0001](DECISIONS/0001-modular-monolith-over-microservices.md).
- If horizontal scaling later makes in-process/PostgreSQL-backed limiting
  inadequate, that is revisited through a new ADR backed by measured
  evidence, not decided in advance.
- This section describes the intended approach only — **rate limiting is
  not implemented yet.**

## Upload & document safety

- Validate MIME type, file extension, and size before processing.
- Reject or safely handle malformed/corrupt documents without crashing the
  ingestion pipeline.
- Store uploaded files using generated identifiers, not user-supplied
  filenames, to avoid path traversal and collision issues.
- Apply resource and time limits to parsing/processing to bound the impact
  of a pathological file.

## Prompt injection defense

Because retrieved chunks are untrusted, the generation layer's design must
assume a malicious document could contain text like "ignore previous
instructions" or attempts to exfiltrate other users' data. Mitigations to
apply when the generation module is built (and to test explicitly — see
below): structurally separating system instructions from retrieved content
in the prompt, not granting the LLM tool/data access beyond what's needed to
answer from the provided evidence, and treating any instruction-like text
inside retrieved content as inert.

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

Security-relevant actions to capture once implemented: authentication
events (login, logout, failed attempts), workspace membership/role changes,
document upload/delete, and any cross-workspace access attempt (successful
or blocked).

## Security testing

Per `AGENTS.md` §3, security assumptions are verified, not just documented:

- **Cross-workspace access tests** — attempt to read/write another
  workspace's documents, conversations, and collections; must fail.
- **Malicious upload tests** — oversized files, mismatched
  extension/content, malformed PDFs/DOCX, zip-bomb-style payloads; must be
  rejected or safely contained.
- **Prompt injection tests** — documents containing instruction-like text
  ("ignore the above," attempts to leak system prompt or other users'
  data); the system must not comply with injected instructions.
- **Auth bypass tests** — attempt to access protected endpoints without a
  valid session, with an expired session, or with a session from a
  different workspace.
- **Path traversal tests** — filenames/paths like `../../etc/passwd` must
  be neutralized.
- **Rate limiting tests** — confirm limits actually trigger under load on
  login and expensive endpoints.

None of these tests exist yet — they are written alongside the
corresponding feature per the Definition of Done in `AGENTS.md` §7, not
deferred to a later "security phase."

## Related documents

- [`docs/REQUIREMENTS.md`](REQUIREMENTS.md) — functional security
  requirements (auth, workspaces).
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — where security-relevant code
  lives (`core/`, `api/` dependencies).
- [`docs/RAG_DESIGN.md`](RAG_DESIGN.md) — generation-layer design where
  prompt injection defense is applied.
- [`docs/DECISIONS/0003-authentication-session-architecture.md`](DECISIONS/0003-authentication-session-architecture.md)
  — the authentication/session model referenced above.
