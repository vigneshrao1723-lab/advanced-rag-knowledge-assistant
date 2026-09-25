# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Everything through Redis Slices 1–3c, Playwright E2E, and Issue #3
Slices 3.1–3.2 (including Slice 3.2's own correctness-review fix) is
merged into `main`.** In order: Redis Slice 1 (foundation +
token-bucket engine) — PR #11, squash commit `46ef03b`. Slice 2
(endpoint wiring) — PR #12, squash commit `5391a78`. Slice 3a
(abuse-state Redis primitives) — PR #13, squash commit `026dcf3`. Slice
3b (decision engine + R1–R5 endpoint wiring, plus a `tests/conftest.py`
test-isolation fix) — PR #14, squash commit `42529e3`. Slice 3c
(abuse-escalation audit emission) — PR #15, squash commit `75dd466`.
Browser E2E (Playwright) for authentication/password-recovery — PR #16,
squash commit `e1c4858`. Issue #3 Slice 3.1 (document data model +
migration `0004`) — PR #17, squash commit `79d4787`. Issue #3 Slice 3.2
(`StorageProvider` abstraction) — PR #18, squash commit `941c1a7`.
Slice 3.2's own pre-merge correctness/security review fix (raw
filesystem errors/paths could otherwise escape the module — see the
dedicated "Completed work" section below) — PR #19, squash commit
`5e6fdc2`, CI green (4/4 checks). **`main`/`origin/main` are at
`5e6fdc2`.** Slice 3.3 (document upload API) has since been merged too
— see the paragraph immediately below. Full per-item implementation
detail is preserved below under its own "Completed work" section — not
repeated here, per this file's own "don't append a history" instruction.

**GitHub Issue #3 (Knowledge Ingestion), Slice 3.3 (document upload API)
was committed, pushed, opened as PR #20, and merged into `main` as
squash commit `a6762e2` by the repository owner (not by this agent).
`main`/`origin/main` are currently at `a6762e2`.** `POST
/api/v1/workspaces/{workspace_id}/documents` (multipart upload) —
authenticate, authorize (MEMBER), rate-limit, validate
(extension/MIME/magic-byte), checksum, workspace-scoped duplicate
check, `StorageProvider.save()`, then the `documents` row + audit event,
committed together. See "Completed work (Issue #3 — Slice 3.3: document
upload API)" below for the full implementation, transaction-consistency,
and test detail.

**GitHub Issue #3, Slice 3.4 (text extraction, including two pre-merge
correctness-review fixes) was committed, pushed, opened as PR #21, and
merged into `main` as squash commit `2961b62`. `main`/`origin/main` are
currently at `2961b62`.** `POST
/api/v1/workspaces/{workspace_id}/documents/{document_id}/process` —
synchronous text extraction (PDF/DOCX/TXT/Markdown/CSV) moving a
document from `UPLOADED`/`PROCESSING`/`FAILED` to `PARSED` or `FAILED`.
See "Completed work (Issue #3 — Slice 3.4: text extraction)" below for
the full implementation, security, crash-safety, and test detail, and
the two independent review sections immediately after it for the fixes
found during PR #21's own pre-merge reviews.

**GitHub Issue #3, Slice 3.5 (structure-aware chunking, including its
own two-round final correctness/security review) was committed, pushed,
opened as PR #22, and merged into `main` as squash commit `237be97`.
`main`/`origin/main` were at `237be97` at the point Slice 3.6 branched
off.** A pure, in-memory `ChunkingStrategy` protocol plus one concrete
`StructureAwareChunker` (`backend/app/ingestion/chunking.py`), turning an
`ExtractedDocument` (Slice 3.4) into ordered `Chunk` objects. See
"Completed work (Issue #3 — Slice 3.5: structure-aware chunking)" and
"Final independent review (Issue #3 — Slice 3.5, same PR #22)" below for
the full design, the schema-compatibility constraint that shaped it, and
the genuine gaps found and fixed across both of that slice's reviews.

**GitHub Issue #3, Slice 3.6 (processing lifecycle: cleaning stage,
chunk persistence, and `PARSED → CLEANED → CHUNKED` continuation) was
committed, pushed, opened as PR #23, and merged into `main` as squash
commit `aa68079`. `main`/`origin/main` were at `aa68079` at the point
Slice 3.7 branched off.** Extends the existing `POST
.../documents/{document_id}/process` endpoint
(`app/services/document_service.py::process_document`) past `PARSED`
through a new `backend/app/ingestion/cleaning.py` stage to `CLEANED`,
then through `StructureAwareChunker` (Slice 3.5) to persisted
`document_chunks` rows and `CHUNKED`. See "Completed work (Issue #3 —
Slice 3.6: processing lifecycle)" below for the full design, transaction/
concurrency strategy, and test detail.

**⚠ Execution mode changed: we are now on an explicit 5-day completion
timeline** (Issues #3 through #8 — authentication/workspaces, this
ingestion pipeline, core RAG retrieval/generation, product UI, voice,
evaluation/security/observability, and final deployment/integration —
all to be finished as one coherent, demonstrable MVP). **This changes
the standing git-workflow default for the rest of this timeline: PRs are
now merged promptly once reviewed and CI-green, without waiting for a
separate per-PR merge instruction**, unless a genuine architectural
blocker requires pausing for review first (`CLAUDE.md` §4's
architectural-review triggers still apply and still require stopping).
Speed is explicitly secondary to correctness/security/data-integrity —
see the project's own "5-day rule": implement the smallest correct
version of each feature, test the critical path, validate security,
commit, update this documentation, and move forward; defer (not skip,
and always document) genuinely non-critical polish rather than let it
block the critical path.

**GitHub Issue #3, Slice 3.7 (embedding generation + vector indexing,
`CHUNKED → EMBEDDED → INDEXED → READY`) was committed, pushed, opened as
PR #24, and merged into `main` as squash commit `7241ec8`.
`main`/`origin/main` were at `7241ec8` at the point Slice 4.1 branched
off.** Extends `process_document()` past `CHUNKED` through a new
`backend/app/ingestion/embedding.py` module (a deterministic, offline
`EmbeddingProvider` — no paid external API required) to `EMBEDDED`, then
through a real pgvector HNSW index (migration `0005`, no separate build
step needed) to `INDEXED`, then `READY`. See "Completed work (Issue #3 —
Slice 3.7: embedding + vector indexing)" below for the full design,
transaction/concurrency strategy, and test detail. **GitHub Issue #3
(Knowledge Ingestion) is now functionally complete end-to-end
(`UPLOADED → READY`).**

**GitHub Issue #4 (Hybrid RAG Pipeline) has started, per the 5-day
plan's Day 2 scope. Slice 4.1** (`conversations`/`messages`/`citations`/
`retrieval_events` schema, migration `0006`) **was committed, pushed,
opened as PR #25, and merged into `main` as squash commit `5e4a626`.**
`main`/`origin/main` were at `5e4a626` at the point Slice 4.2 branched
off. The minimal persistence shape needed for the rest of Issue #4
(retrieval + reranking + generation + citations) to write a result
somewhere — see "Completed work (Issue #4 — Slice 4.1: conversation/
message/citation/retrieval-event schema)" below for the full design.

**Slice 4.2** (retrieval module — dense/lexical/fusion/reranking,
`backend/app/retrieval/`, migration `0007`) **was committed, pushed,
opened as PR #26, and merged into `main` as squash commit `378fec4`.**
`main`/`origin/main` were at `378fec4` at the point Slice 4.3 branched
off. `hybrid_search()` (`app/retrieval/service.py`) is the single
orchestrating entry point: embed the query -> dense (pgvector) +
lexical (Postgres full-text search) retrieval -> Reciprocal Rank
Fusion -> `LexicalOverlapReranker` -> optionally record a
`RetrievalEvent`. See "Completed work (Issue #4 — Slice 4.2: retrieval
module)" below for the full design and the standing
workspace-isolation-at-retrieval-time security guarantee it
establishes.

**Slice 4.3** (generation module + a minimal conversations ask-flow
endpoint, `backend/app/generation/`, `app/api/v1/conversations.py`)
**is IMPLEMENTED and FULLY TESTED, on branch
`issue-4-slice-4-3-generation`** (cut from `378fec4`) — not yet
committed/pushed/PR'd as of this line; see "Exact next recommended
action" at the end of this file. `POST .../conversations/{id}/messages`
now runs the full pipeline end-to-end: persist the user's question ->
`hybrid_search()` (Slice 4.2) -> `generate_answer()` (context builder +
`LLMProvider`, this slice) -> persist the assistant's answer + its
`Citation` rows (Slice 4.1 schema), atomically. **This is the first
slice where a real question against real ingested documents returns a
real grounded answer with citations end-to-end — Issue #4's primary
Definition-of-Done item.** See "Completed work (Issue #4 — Slice 4.3:
generation module + conversations endpoint)" below for the full design,
including the deterministic-and-therefore-prompt-injection-immune
`LocalGroundedExtractiveProvider` and [ADR 0007](docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md)
recording why no commercial LLM/embedding/reranker vendor is selected
yet.

Issue #2 (merged) covered: registration/login/logout/refresh with
PostgreSQL-backed sessions, HttpOnly cookie + CSRF browser authentication,
workspace CRUD/membership/RBAC, password recovery (backend and frontend),
audit logging, and the security documentation/ADRs for all of it.

## Completed work (Issue #2, merged in PR #10)

- **Cookie + CSRF authentication migration** (superseding the original
  design where tokens were returned in the JSON response body for the
  frontend to hold and send as `Authorization: Bearer`): access and
  refresh tokens are now delivered exclusively via `HttpOnly` cookies
  (`access_token` on `Path=/`; `refresh_token` narrowly scoped to
  `Path=/api/v1/auth`), never in a response body, never read by
  JavaScript. A double-submit `csrf_token` cookie (deliberately **not**
  `HttpOnly`) + `X-CSRF-Token` header protects every state-changing
  request, including login/register (login-CSRF defense). Cookie
  attributes (`COOKIE_SAMESITE`/`COOKIE_DOMAIN`/`COOKIE_SECURE`) and CORS
  (`CORS_ALLOWED_ORIGINS`, credentialed) are deployment-aware — see
  [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  for the full model, including the "different origin ≠ cross-site"
  distinction that governs `COOKIE_SAMESITE` (a subdomain split, or
  `localhost:3000` ↔ `localhost:8000`, is same-site despite being a
  different origin — don't set `SameSite=None` for those; it's an
  unforced weakening).
  - Backend: `app/core/cookies.py`, `app/core/csrf.py`,
    `app/core/dependencies.py` (`get_current_token_claims` reads the
    cookie, not a header), `app/main.py` (middleware ordering: CSRF →
    access-log → request-ID → CORS, added in that order so CORS ends up
    outermost and its headers land on CSRF/auth rejections too),
    `app/api/v1/auth.py`, `app/schemas/auth.py` (`AuthResponse = {user}`
    only, no token fields).
  - Frontend: `lib/api-client.ts` fully rewritten (`credentials:
    "include"` on every request, CSRF header attached on state-changing
    requests, `Authorization`/bearer logic and `localStorage`/
    `sessionStorage` token storage entirely removed —
    `lib/auth-storage.ts` deleted), `lib/csrf.ts` (new — reads the
    non-HttpOnly CSRF cookie), `lib/auth-context.tsx` rewritten (auth
    state derived from `getCurrentUser()` on mount, not from storage).
- **Password recovery** — backend and frontend, both complete:
  - Backend: `POST /api/v1/auth/forgot-password` and
    `POST /api/v1/auth/reset-password`
    (`app/services/password_reset_service.py`). Reset tokens are
    `secrets.token_urlsafe(32)` (256 bits), SHA-256-hashed at rest, never
    logged raw, single-use (`used_at`), expiring
    (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`). `forgot-password` always
    returns the same generic response/status regardless of whether the
    email exists, with a dummy Argon2 verification on the not-found path
    for timing equalization. A successful reset revokes every existing
    session for that user (`session_repository.revoke_all_for_user`) and
    reuses the existing Argon2id hashing. Email delivery via the
    `EmailProvider` abstraction (`app/services/email_provider.py`) —
    `console` (stdout, dev/test fallback) or `smtp` (local dev points it
    at Mailpit). **`ENVIRONMENT=production` + `EMAIL_PROVIDER=console`
    now fails at config-load time** (`app/core/config.py`'s
    `_validate_email_provider_for_production`) — this was a genuine
    defect found during audit: stdout is typically captured by log
    aggregation in real deployments, which would have leaked raw reset
    tokens into logs if `EMAIL_PROVIDER` were ever left unset in
    production.
  - Frontend: `app/forgot-password/page.tsx` (email input, generic
    success message, no existence leakage) and
    `app/reset-password/page.tsx` (reads `token` from the URL via
    `useSearchParams` inside a `Suspense` boundary — the page is
    statically prerendered, so the token is only resolved client-side
    after hydration, not server-rendered; this is correct Next.js
    behavior, not a bug, but it means a plain `curl` of the page shows
    the `Suspense` fallback, not the form — don't mistake that for a
    broken page). New password + confirm-password fields with
    client-side match validation (`lib/schemas.ts`'s
    `ResetPasswordFormSchema`), distinct UX for invalid/expired/
    already-used tokens (surfaces the backend's exact message), and a
    "Forgot password?" link added to `/login`.
- **Audit logging**: `app/core/audit.py` (`AuditEvent` string constants,
  not a DB enum, for extensibility) and
  `app/repositories/audit_log_repository.py`. Records registration,
  login success/failure, logout, session revocation, refresh-token reuse
  detection, password-reset request/success, workspace
  create/delete/membership changes, and authorization denials. Writes
  commit immediately/independently of the surrounding request's
  transaction. `user_id`/`workspace_id` use `ON DELETE SET NULL`.
- **Docs**: [ADR 0005](docs/DECISIONS/0005-httponly-cookie-csrf-authentication.md)
  (new — the cookie/CSRF model and the origin-vs-site distinction);
  `docs/SECURITY.md` corrected (previously stale: described "bearer
  access tokens" and listed audit logging as "not implemented" — both
  fixed to match the current implementation).
- **Tests**: backend went from 95 to **119** pytest tests this checkpoint
  (new: `tests/test_cookie_security.py`, `tests/test_csrf.py` additions,
  `tests/test_password_reset.py` additions, `tests/test_config.py`
  additions for the production email-provider guard). Frontend went from
  30 to **48** vitest tests (new: `lib/api-client.test.ts` and
  `lib/auth-context.test.tsx` regression tests proving no token ever
  reaches `localStorage`/`sessionStorage`/an `Authorization` header;
  `app/forgot-password/page.test.tsx`, `app/reset-password/page.test.tsx`).

## Completed work (Redis/abuse-protection architecture design)

- [ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
  — the full design: what's wrong with the current in-process limiter
  (verified from code, not assumed — no cross-instance coordination,
  fixed-window boundary doubling, IP-only keying, no `X-Forwarded-For`
  handling, and the already-defined-but-never-emitted
  `AuditEvent.RATE_LIMITED`); a Redis token-bucket algorithm; hierarchical
  dimensions chosen per-operation (IP/account/session, never applied
  uniformly); a deterministic rule table for abuse detection (not a
  numeric score, not ML); `ALLOW`/`THROTTLE`/`STRICT_THROTTLE`/
  `TEMPORARY_BLOCK` semantics (`REJECT` explicitly left undefined — no
  operation in this system needs it yet); an operation-aware Redis
  failure policy; a Redis key namespace that never stores raw
  credentials/tokens/emails; an observability split (ordinary throttling
  → logs only, escalations → `audit_logs`); Docker/CI implications; and a
  full test strategy — all **design only**.
- **This ADR was then adversarially reviewed for architectural/security
  flaws (a separate, dedicated task) and corrected before this
  checkpoint** — read the ADR itself for the full reasoning, but the
  headline corrections, since they materially change the design from a
  first read of the summary above:
  - **Atomicity is per-operation, not per-key.** The first draft ran one
    independent Lua script per dimension key (e.g., separately for
    `login`'s IP bucket and account bucket) and treated each key's own
    atomicity as sufficient for the combined decision. It wasn't — a
    request could consume one dimension's bucket and then be rejected on
    another, a real partial-consumption/fairness bug. The corrected
    design runs **one Lua invocation per operation, over all of that
    operation's dimension keys together**, all-or-nothing (ADR §8, §10).
  - **Email keys use a keyed HMAC, not plain SHA-256** — a plain hash of
    a low-entropy identifier like an email is dictionary/rainbow-table-
    matchable and isn't a real privacy protection (ADR §14).
  - **The R3 distinct-IP-per-account signal uses a HyperLogLog, not a
    plain Redis `SET`** — a `SET` would let an attacker's own botnet
    inflate Redis memory in direct proportion to the attack the signal
    exists to detect (ADR §11).
  - **R2 (many login failures against one account) escalates to
    `STRICT_THROTTLE`, not a hard `TEMPORARY_BLOCK`** — a hard,
    account-scoped block triggerable by anyone who merely knows a
    victim's (non-secret) email is itself a denial-of-service vector
    against that victim. Only R3 (genuinely distributed source IPs, much
    harder to cheaply fake against a chosen victim) still triggers a
    hard block (ADR §11, §18).
  - **A full trusted-proxy / `X-Forwarded-For` design was added** (ADR
    §9a) — the first draft only flagged the gap; it's now fully
    specified: ignore the header unless a configured
    `TRUSTED_PROXY_CIDRS` trusts the immediate peer, then walk the
    header from the right (never trust a client-supplied leftmost entry).
  - **The Redis-failure section now states plainly what security
    guarantee is lost** in each scenario (single vs. multi-instance,
    which checks fail open vs. fall back) rather than leaving that
    implicit (ADR §13).
  - A full Redis cardinality/memory threat table (every structure: who
    can create it, its bound, its TTL) was added (ADR §18).
- **This is still design work only.** No Redis dependency, Docker
  service, or application code was added; no tests were added or
  modified; no existing code was changed — the adversarial review only
  edited the ADR and this documentation.

## Completed work (Redis implementation slice 1 — foundation + token-bucket engine)

**Merged into `main` as squash commit `46ef03b` via PR #11.** Implemented
the pieces of ADR 0006 that don't require touching any endpoint, per that
slice's explicit scope (superseded by slice 2 below, which wires all of
this in):

- **`redis` dependency** (`redis>=8.1.0` resolved, pinned in
  `backend/pyproject.toml`/`backend/uv.lock` via `uv add redis`, matching
  the project's existing lower-bound-only convention).
- **Settings** (`app/core/config.py`): `redis_url` (optional — `None`
  means the engine is simply unavailable, not a config error),
  `redis_socket_timeout_seconds`/`redis_socket_connect_timeout_seconds`
  (default `0.05`, validated `> 0`), `trusted_proxy_cidrs` (default `""`,
  ADR §9a) + `trusted_proxy_cidrs_list` property.
- **`app/core/redis_client.py`** (new): `build_redis_client()` (explicit
  URL + timeouts, never hardcoded), `get_redis_client()` (settings-backed,
  cached, returns `None` if unconfigured), `is_redis_available()` (never
  raises — catches `redis.RedisError`), `RedisUnavailableError`.
- **`app/core/redis_keys.py`** (new): `rate_limit_key(operation,
  dimension, value)` (ADR §14's `rl:{operation}:{dimension}:{value}`
  namespace) and `hash_account_identifier(email, key=...)`
  (HMAC-SHA256, ADR §14's corrected email-identifier design — never a
  plain hash).
- **`app/core/ip_resolution.py`** (new): `resolve_ip()` (pure function)
  and `resolve_client_ip()` (`Request` wrapper) implementing ADR §9a's
  trusted-proxy walk. Not called from any endpoint as of this Slice 1
  checkpoint — Slice 2 (below, now also merged) is what wires it in.
- **`app/core/rate_limit.py`** (extended, not replaced): `DimensionSpec`,
  `TokenBucketResult`, `RedisTokenBucketLimiter` — the ADR §8/§10 Lua
  token-bucket engine. One `EVAL` per operation, over every dimension key
  that operation has; reads/refills/checks all dimensions before writing
  any; writes nothing on rejection. `FixedWindowRateLimiter` and every
  `enforce_*_rate_limit` function are **byte-for-byte unchanged**.
- **`infra/compose/docker-compose.yml`** / **`.github/workflows/ci.yml`**:
  a pinned `redis:7.4-alpine` service, healthcheck-gated (`redis-cli
  ping`), matching the existing `mailpit`/`db` pattern. `backend`'s
  `depends_on: redis: condition: service_healthy` is container-startup
  ordering only (ADR §13 explicitly sanctions this — distinct from
  runtime readiness). `.env.example` documents the new variables.
- **A genuinely hard problem, documented in `SOLVING.md`**: Redis's
  Lua→RESP2 reply conversion silently truncates a returned float to an
  integer — the token-bucket script computes/returns `retry_after_ms` as
  an integer instead of fractional seconds specifically to survive this,
  with the unscaling done on the Python side.

## Completed work (Redis implementation slice 2 — wire the engine into every endpoint)

**Merged into `main` as squash commit `5391a78` via PR #12**, on top of
the merged Slice 1 (`46ef03b`):

- **`app/core/rate_limit.py`'s `enforce_*_rate_limit` functions rewritten**
  to attempt the Redis engine first, per ADR §9's exact per-operation
  dimensions, falling back to `FixedWindowRateLimiter` per ADR §13:
  - `register`: IP only. Tier B.
  - `login`: IP + account (email extracted from the JSON body via a new
    `_extract_email_from_json_body()` helper — a best-effort peek that
    never blocks normal Pydantic validation, since `Request.json()`
    caches the raw bytes). Tier A.
  - `refresh`: IP + session ID (parsed from the refresh-token cookie via
    the existing `parse_refresh_token()` in `app/core/security.py` — no
    database round-trip, per ADR §7's hot-path requirement). Tier A.
  - `forgot-password`: IP + account (same email-extraction approach as
    `login`). Tier A.
  - `reset-password`: IP only, per ADR §9's reasoning (the token's own
    256-bit entropy is the real defense). Tier A.
  - A shared `_check_or_fallback()` helper implements the tier logic once,
    used by all five functions.
  - `get_redis_client` is now injected via `Depends()` (not called as a
    plain function) specifically so tests can override it with
    `app.dependency_overrides` — this is what makes the Tier A/B tests
    below possible without needing to actually kill a real Redis.
- **A deliberate refinement of ADR §13's Tier B, resolving its own
  explicitly-left-open sub-decision** (full writeup: `SOLVING.md`'s
  2026-09-14 "ADR 0006 §13's Tier B..." entry; also recorded in ADR
  0006's "Implementation status" and §22): `get_redis_client()` returning
  `None` (Redis never configured — today's default everywhere) always
  falls back to `FixedWindowRateLimiter`, for every operation including
  `register`. Only a `RedisUnavailableError` from an *already-configured*
  client triggers Tier B's literal fail-open. Implementing the ADR's
  literal wording without this distinction would have made `register`
  unprotected by default in every environment that hasn't explicitly set
  `REDIS_URL` — i.e. every environment today.
- **`FixedWindowRateLimiter` gained `.limit`/`.window_seconds`
  properties** so the Redis dimensions' capacity/refill-rate are derived
  live from the same objects, never a second hardcoded copy of the same
  numbers (ADR §8 "Continuity with today's numbers").
- **New setting**: `rate_limit_hash_key` (`app/core/config.py`) —
  resolves ADR §14/§22's open "HMAC key location" decision by reusing
  `secret_key` unless explicitly overridden, avoiding a new required
  secret for a threat model that doesn't need key separation from JWT
  signing to be effective.
- **`backend/tests/conftest.py` fixed**: `_reset_rate_limiters` now also
  clears `rl:*` Redis keys between tests (via `SCAN`+`DELETE`), not just
  the in-process limiters — see `SOLVING.md`'s first 2026-09-14 entry for
  why this was necessary (52 previously-passing tests failed the moment
  the Redis path went live in tests, until this fix).
- **`tests/test_rate_limit_wiring.py`** (HTTP-level, through real
  endpoints; started at 5 tests, now 13 — see the review/fixes entry
  below for the 8 added since): a successful login creates the exact
  `rl:login:ip:*`/`rl:login:acct:*` keys ADR §14 specifies; Tier A
  fallback and Tier B fail-open, both via `app.dependency_overrides`
  pointing `get_redis_client` at an unreachable client; the
  "unconfigured vs. unreachable" distinction (`None` override still
  rate-limits `register`); a spoofed `X-Forwarded-For` does not let an
  attacker escape the IP bucket with `TRUSTED_PROXY_CIDRS` unset.
- **Live-verified against the real Docker Compose stack** (not just
  tests): a live login created real `rl:login:ip:*`/`rl:login:acct:*`
  keys (inspected directly via `redis-cli --scan`); `/api/v1/health/ready`
  stayed `200 ready` with Redis stopped; `register` failed open (7/7
  succeeded past the base limit of 5) only while Redis was actually down,
  and `login` still hit `429` at exactly the fallback limiter's threshold
  during that same outage (Tier A); stopping and restarting Redis
  mid-session, `register` went from failing open back to enforcing its
  limit at exactly 5 with no process restart.

### Slice 2 read-only security/architecture review, and the fixes it produced

A dedicated read-only review of the uncommitted Slice 2 diff (endpoint
wiring, Redis failure policy, HMAC construction, trusted-proxy IP
handling, test quality, observability, performance/failure modes,
documentation consistency) found 0 P0, 3 P1, 3 P2, 2 P3 findings. All 3
P1s and the most important P2 (HTTP-level test coverage) were then fixed,
still entirely within Slice 2's uncommitted working tree:

- **P1 — documentation staleness (this reconciliation).** `HANDOFF.md`,
  `PROJECT_STATE.md`, `docs/SECURITY.md`, and ADR 0006 still described
  "slices 1–2, uncommitted" as one unit, predating even Slice 1's own
  commit — corrected here to reflect Slice 1 merged (`46ef03b`, PR #11)
  and Slice 2 uncommitted, on the new branch name.
- **P1 — Redis-failure fallback was unobservable.** ADR 0006 §13
  explicitly requires a structured log line when the rate limiter
  degrades to its fallback on a genuine Redis outage; none existed.
  Added `_log_redis_fallback()` in `app/core/rate_limit.py`, using the
  project's existing `logging.getLogger("app.<domain>")` +
  `extra={...}` convention (matching `auth_service.py`/`access_log.py`).
  Logs only `operation` (a fixed, non-secret literal) and `policy`
  (`fail_open` or `fallback_to_in_process_limiter`) — never an email, IP,
  token, or secret. Fires only on a genuine `RedisUnavailableError`, not
  on the normal "Redis never configured" default state (which would be
  noisy and uninformative on every single request in every environment
  that hasn't opted into Redis).
- **P1 — stale docstrings.** `redis_client.py` and `ip_resolution.py`
  still said "not wired into any endpoint yet" (accurate when Slice 1
  alone was committed, false once Slice 2 lands) — corrected to describe
  their actual role as of this slice, including
  `resolve_client_ip()`'s own docstring, which had the same claim.
- **P2 — missing HTTP-level test coverage**, now closed: Redis-key-
  creation tests for `refresh` (proves the session dimension key holds
  only the session ID, never the refresh token's secret half) and
  `forgot-password` (mirroring the existing `login` test); a
  `reset-password` test proving it creates only an IP-dimension key,
  never an account/session one; Tier A fallback tests for `refresh`/
  `forgot-password`/`reset-password` (previously only `login`/`register`
  had them); an endpoint-driven multi-dimension atomicity regression test
  for `login` (proves `enforce_login_rate_limit` wires both dimensions
  into one `check_all()` call — a losing account-dimension check must
  never have touched a fresh IP's own bucket); and a cross-user
  account-isolation test (account A's exhausted bucket must not throttle
  account B, verified using `TestClient(app, client=(ip, port))` for two
  genuinely different peer IPs, so the shared-IP dimension can't confound
  the result). 8 new tests, `test_rate_limit_wiring.py` 5 → 13.
- **Remaining P2/P3, intentionally not addressed in this pass** (see
  "Explicitly NOT done" below): an endpoint-driven concurrency test under
  real HTTP load; ordinary `THROTTLE`/429 rejections still aren't logged
  (a broader, pre-existing gap, not introduced by Slice 2);
  `ip_resolution.py`'s docstring still slightly overstates `Forwarded`
  (RFC 7239) support that was never implemented (fails safe, not a
  security gap — explicitly out of scope per this task's own
  instruction not to expand into `Forwarded`-header work).
- Full suite re-verified after these fixes: **183/183 passing** (real
  Postgres + real Redis, re-run 3 times, no flakiness), `ruff`/`mypy`
  clean.

## Completed work (Redis abuse layer — Slice 3a: primitives only)

**Uncommitted, working-tree-only.** Implements only the low-level,
fully-parameterized Redis/Lua primitives ADR 0006 §11/§12/§14 needs —
explicitly not the rule table, not `AbuseDecisionEngine`, not endpoint
wiring (all Slice 3b/3c, not started). No existing file was modified
except the two documentation files noted below; `register`/`refresh`/
`login`/`forgot-password`/`reset-password` are byte-for-byte unchanged
from Slice 2.

- **`app/core/abuse_keys.py`** (new): key builders for the `abuse:`
  namespace, mirroring `redis_keys.py`'s role for `rl:` —
  `failcount_key`, `distinct_ips_key`, `strict_throttle_key`, `block_key`.
- **`app/core/abuse_state.py`** (new): atomic Lua-scripted primitives,
  with no knowledge of R1–R5 as named rules (fully parameterized —
  thresholds/windows are Slice 3b's rule table, not hardcoded here):
  - `record_login_failure()` — **one Lua invocation** that atomically
    increments the IP failcount (R1) and account failcount (R2), adds the
    IP to the account's distinct-IP HyperLogLog (R3), and escalates each
    dimension independently once its own threshold is crossed. Multi-
    signal atomicity matches the same "check all → decide → write all"
    pattern Slice 1's `_TOKEN_BUCKET_LUA` already established.
  - `record_ip_failure()` — the shared primitive behind R4/R5
    (forgot-password/reset-password IP counters), parameterized by an
    `escalation: Literal["strict", "block"]` argument (passed to Lua as a
    **numeric** flag, not a string — a deliberate risk-reduction choice
    made because the script could not be execute-tested live this
    session; the codebase's existing Lua scripts never pass string
    ARGVs, so this also matches convention).
  - **Fixed-window counters**: TTL is set only when a counter is first
    created (`count == 1`), never refreshed by later increments — a
    deliberate simplicity choice, not a sliding window.
  - **STRICT_THROTTLE**: created via `HSETNX` (never resets an
    already-escalated/partially-consumed bucket) reusing the existing
    `RedisTokenBucketLimiter`/`DimensionSpec` bucket shape — no new
    bucket engine. Its TTL **does refresh** on every re-escalation, to
    keep the throttle alive while abuse continues.
  - **TEMPORARY_BLOCK**: created via `SETNX`, TTL **set once at creation
    and never refreshed** by a later crossing — this asymmetry with
    STRICT_THROTTLE is exactly what guarantees ADR §12's "never permanent
    or indefinite" requirement; there is no manual-unblock path, and a
    successful login must never remove it (verified — see next bullet).
  - `reset_account_state()` — the successful-login decay: deletes the
    account-scoped failcount (R2) and the distinct-IP HyperLogLog (R3)
    only. **Never touches R1 (IP failcount), block state, or strict-
    throttle state.** Concurrency semantics (a reset racing a concurrent
    failure) are "last write wins," documented in-code as a deliberate,
    bounded, self-healing, non-exploitable choice — **no generation/
    version counter was introduced**, matching this project's own prior
    analysis that one isn't needed (an attacker cannot trigger their own
    account's success without already having the correct credential).
  - `is_strict_throttle_active()` / `is_temporarily_blocked()` — plain
    `EXISTS` reads, unused by anything yet, provided for Slice 3b's
    future `check()`.
  - Every primitive raises `RedisUnavailableError` on any
    `redis.RedisError` — never swallows, never introduces a second
    fallback limiter (matches ADR §13's existing outage contract exactly;
    the abuse layer relies on the same fail-open/fallback policy Slice 2
    already implements for the base rate limiter).
- **`tests/test_abuse_state.py`** (new, 32 tests): failcount creation/
  increment/TTL/expiry; HLL creation/repeated-IP/distinct-IP counting/
  threshold boundary/expiry/reset-on-success; R2 reset vs. R1-not-reset;
  block creation/TTL/expiry/not-removed-by-success; strict-throttle
  not-created-by-ordinary-failures/created-only-after-escalation/correct
  capacity/does-not-reset-consumed-tokens-on-re-escalation/TTL/expiry;
  multi-signal atomicity; concurrent-failure-increment and concurrent-
  reset-vs-failure race tests (real `threading`, asserting only bounded,
  non-negative, valid final states — no mocks); cross-account isolation;
  shared-IP-multiple-accounts; one-account-multiple-IPs; Redis-
  unavailable (all 5 primitives); no raw email/secret ever stored in a
  Redis value; a bounded-TTL sweep across every key type. Uses small
  fast test thresholds (e.g. 3/1–2s), not the real R1–R5 production
  values — this slice tests the mechanism, not the rule table.
  - **`ruff`/`mypy` clean** on all three new files. Test collection on
    the host succeeds (`pytest --collect-only` → 215 tests: 183 existing +
    32 new).
  - **Real-Redis validated**: after the host shell's own path to the
    Dockerized Redis/Postgres published ports was confirmed broken (an
    environment fault, not a code defect — see "Tests run" below), the 32
    tests were copied into and run inside the already-running
    `compose-backend-1` container, over the Docker-internal `db`/`redis`
    hostnames, and **passed 3 consecutive times (32/32 each run)**. This
    is not the same as a clean host-side run of the current 215-test full
    suite, and not a production validation — see "Tests run" for the
    full method and caveats.
- **Documentation updated this slice**: ADR 0006 (§22's now-resolved
  open decisions moved into a new "Resolved during the abuse-layer
  design/readiness review" subsection — the full R1–R5 threshold/window
  table, the corrected 60-second token-bucket timing derivation replacing
  an earlier wrong "~2 minutes" estimate, the strict/block TTL-asymmetry
  rationale, and the decay policy; the "Implementation status" table's
  abuse-layer row split into 7 granular per-component rows, all
  Tested=No/Committed=No with an explicit Docker-unavailable note) and
  `PROJECT_STATE.md` (component-status rows updated). `docs/SECURITY.md`
  was reviewed and needs **no change** — it already states the abuse
  layer doesn't exist yet, which remains true since Slice 3a changes zero
  runtime behavior (unused primitives, no wiring).

**Slice 3a note (superseded by the entry above): Slice 3a has since been
committed and merged into `main` as squash commit `026dcf3` (PR #13).**

## Completed work (Redis abuse layer — Slice 3b: decision engine + endpoint wiring)

**Superseded by the current-task summary above: Slice 3b has since been
committed and merged into `main` as squash commit `42529e3` (PR #14),
including the `tests/conftest.py` test-isolation fix.** The record below
is kept as accurate history of that slice's own implementation/
validation, not as the current status.

Implements the deterministic
decision layer on top of Slice 3a's primitives and wires it into the
three operations R1–R5 actually target — `login`, `forgot-password`,
`reset-password`. `register`/`refresh` are untouched (no rule in R1–R5
targets them).

- **`app/core/abuse_decision.py`** (new): a module-level rule table
  (`_BLOCK_DIMENSIONS`/`_STRICT_DIMENSIONS` per operation — the data
  that makes `TEMPORARY_BLOCK` deterministically dominate
  `STRICT_THROTTLE`, since block dimensions are always resolved in full
  before any strict dimension is even inspected) plus a stateless
  `check()`/`record_*()` API:
  - `check(client, context) -> AbuseDecision` — pre-request, read-only
    (`EXISTS`/`TTL` only). Returns `temporary_blocked` (with
    `retry_after_seconds` sourced from the new `temporary_block_ttl_seconds()`
    primitive) and a list of already-escalated `strict_dimensions`
    (`DimensionSpec`s) for the caller to fold into its own
    `check_all()` — never a separate Redis round trip, which would
    reopen the partial-consumption race ADR 0006 §10 already closed once.
  - `record_login_failure()` / `record_login_success()` /
    `record_forgot_password_request()` / `record_reset_validation_failure()`
    — four explicitly-named functions, not one function overloaded with
    a `succeeded` flag that would sometimes mean "always true"
    (forgot-password has no real success/failure branch to key off —
    see ADR's enumeration-resistance design). Each returns an
    `AbuseRecordOutcome` (`rule_id`/`action`/`newly_escalated`/
    `operation`/`dimension`) with enough detail for a future Slice 3c to
    decide what, if anything, to audit.
  - Fails open unconditionally on `RedisUnavailableError` (logged,
    never re-raised) and is a no-op when `client` is `None` — simpler
    than the base limiter's operation-aware Tier A/B split, since the
    abuse layer is defense-in-depth on top of the base token bucket, not
    a replacement for it.
  - Never imports `app.core.audit` or touches PostgreSQL — audit
    emission stays Slice 3c's job.
- **`app/core/abuse_state.py`** (additive change only): one new
  primitive, `temporary_block_ttl_seconds()` — a plain `TTL` read,
  returning remaining seconds or `None`. Added because
  `is_temporarily_blocked()`'s existing boolean isn't enough to build an
  accurate `Retry-After`; its own signature/contract is unchanged.
- **`app/core/token_bucket_types.py`** (new — a deviation from the
  original file plan, explained below): `DimensionSpec`/
  `TokenBucketResult`, extracted out of `rate_limit.py`.
  `rate_limit.py` re-exports both names unchanged (`from
  app.core.rate_limit import DimensionSpec` still works everywhere it
  already did), so no other existing call site needed to change.
  **Why this file exists:** wiring `rate_limit.py` to call
  `abuse_decision.check()` created a real circular import
  (`rate_limit.py` → `abuse_decision.py` → `abuse_state.py` →
  `rate_limit.py`, since `abuse_state.py` already imported
  `DimensionSpec` from `rate_limit.py`) — confirmed by an actual
  `ImportError` at runtime, not just suspected. This was the minimal fix
  (move one dependency-free dataclass pair to a leaf module both sides
  can import from) rather than a broader refactor; verified afterward
  that the full app (`create_app()`) and a full `mypy .` (81 files)
  both pass cleanly.
- **`app/core/rate_limit.py`** (modified): `enforce_login_rate_limit`/
  `enforce_forgot_password_rate_limit`/`enforce_reset_password_rate_limit`
  each now call `abuse_decision.check()` first — an active
  `TEMPORARY_BLOCK` raises `429` immediately, before the base
  `check_all()` even runs; any active `STRICT_THROTTLE` dimension is
  appended to the *same* dimension list passed to `_check_or_fallback()`,
  so strict-bucket consumption stays atomic with the base bucket's own
  consumption in one Lua invocation. `enforce_register_rate_limit`/
  `enforce_refresh_rate_limit` are byte-for-byte unchanged.
- **`app/api/v1/auth.py`** (modified): `login`/`forgot-password`/
  `reset-password` gained post-outcome recording:
  - `login`: `auth_service.login()` is wrapped in `try/except
    HTTPException` — a caught exception calls `record_login_failure()`
    then re-raises; a normal return calls `record_login_success()`.
    Recording happens **only after the real outcome is known**, never
    in the pre-request dependency (this is the exact bug the stale ADR
    §6 diagram — now corrected — would have caused if implemented
    literally).
  - `forgot-password`: `record_forgot_password_request()` is called
    unconditionally, right after `password_reset_service.request_password_reset()`
    (which itself never raises).
  - `reset-password`: a caught `HTTPException` is inspected for
    `detail["code"]` — only `reset_token_invalid`/`_expired`/
    `_already_used` triggers `record_reset_validation_failure()`; a
    successful reset records nothing.
- **`tests/test_abuse_decision.py`** (new, 33 tests): rule-table shape,
  `AbuseContext` construction, per-rule threshold behavior (below/exact/
  already-active) for all of R1–R5, TTL expiry and the block's
  non-refreshing TTL, R1+R2/R2+R3/R1+R2+R3 simultaneous-escalation and
  precedence tests (confirming `TEMPORARY_BLOCK` always dominates,
  by construction of `check()`'s dimension ordering, not by chance),
  block-expiry-falls-through-to-strict, account/IP isolation,
  successful-login reset scoping (R2/R3 cleared, R1 and active
  escalations untouched), R4's unconditional recording, R5's
  failure-only recording, Redis-unavailable/unconfigured fail-open and
  no-op paths, concurrent-failure races (real `threading`, reusing
  Slice 3a's established pattern), strict-dimension-atomic-with-base-
  dimension (using `RedisTokenBucketLimiter.check_all()` directly to
  prove no partial consumption), and no raw email/secret leakage.
  - **Two test-design bugs found and fixed during this slice's own
    validation** (not defects in `abuse_decision.py`/`abuse_state.py`
    themselves): the original R1-isolation test reused the same account
    across all 10 calls, so R2 co-escalated and the test asserted the
    wrong `rule_id`; the original R2-isolation test used a fresh IP per
    call, which tripped R3's lower threshold (5) before R2's (10) ever
    fired. Both fixed by controlling which dimension varies per call so
    only the rule under test can possibly cross its threshold.
  - `ruff`/`mypy` clean. **33/33 passed, 3 consecutive runs**, plus the
    unaffected 32 from Slice 3a (**65/65 combined**), against real Redis
    + real PostgreSQL inside `compose-backend-1`.
- **Full pre-existing suite, run inside the same container, from a
  freshly flushed Redis, with `EMAIL_PROVIDER=console` overridden to
  isolate the already-known, already-documented Slice-3a-era artifact**:
  **238 passed, 2 failed** (240 collected). Both failures
  (`test_reset_token_does_not_affect_other_users`,
  `test_password_reset_does_not_retroactively_invalidate_an_already_issued_access_token`)
  were diagnosed precisely, not assumed: a direct diagnostic script
  showed the `forgot-password` call itself returning `429`, not a
  print-capture problem. Root cause: `tests/conftest.py`'s
  `_reset_rate_limiters` autouse fixture sweeps `rl:*` Redis keys
  between tests but **not** the new `abuse:*` keys this slice's wiring
  creates — so `abuse:failcount:forgot-password:ip:testclient` (every
  `TestClient` request shares the same fixed `"testclient"` peer
  address) accumulates across every test in the session that calls
  `forgot-password`, and once R4's threshold (10) is crossed, later
  `forgot-password` calls from the same fixed IP get `STRICT_THROTTLE`d
  for real. Confirmed reproducible from a genuinely clean Redis (not an
  artifact of repeated same-session reruns) by flushing Redis and
  running the full suite once, cleanly, twice (with and without the
  `EMAIL_PROVIDER` override) — both times, exactly these same 2 tests
  failed with the identical `429` root cause. `test_abuse_decision.py`/
  `test_abuse_state.py` were unaffected throughout (each has its own
  dedicated `abuse:*`-sweeping cleanup fixture, scoped to just those
  files).

**Test-isolation fix (same branch, follow-up commit `46a2860`):**
`tests/conftest.py`'s `_reset_rate_limiters` extended to also sweep
`abuse:*` between tests, mirroring the existing `rl:*` pattern-delete
loop exactly, under the same `RedisError` tolerance already in place —
one file, no production code touched, no test skipped/xfailed/reordered,
no sleeps added. Confirmed CI itself hit the identical root cause on PR
#14 before this fix (3/248 failed: the same 2 `test_password_reset.py`
tests plus `test_rate_limit_wiring.py::test_successful_forgot_password_creates_the_redis_ip_and_account_dimension_keys`,
which failed there with the same `429 == 200` signature — a different
specific test than locally, purely because CI's test-execution order
differs, not a different root cause). After the fix: the 3 previously-
failing tests pass individually and together; the complete **248-test
backend suite passed 248/248, 3 consecutive runs** (real Postgres + real
Redis, inside `compose-backend-1`, `EMAIL_PROVIDER=console` to match
CI's own environment — confirmed via `.github/workflows/ci.yml` that CI
never sets `EMAIL_PROVIDER` at all, so it was never affected by this
container's separate `EMAIL_PROVIDER=smtp` runtime artifact). No new
regression test was added — the existing suite (specifically the
forgot-password wiring test that was one of the 3 originally failing)
already directly demonstrates the fix, and adding another would have
been redundant. `ruff`/`mypy` clean (host and container, 81 source
files — the fixture change touches only a test file).
- **Documentation updated this slice**: ADR 0006 (§6's flow diagram
  corrected — the original placed `record(outcome)` inside the
  pre-request dependency, which is unreachable since outcomes aren't
  known until the endpoint body runs; the "Implementation status" table
  updated for Slice 3a's merge and Slice 3b's new components),
  `PROJECT_STATE.md`, this file. `docs/SECURITY.md` was reviewed and
  needs **no change**: it describes the *committed* (`main`) codebase's
  security posture, and Slice 3b is not committed — `main` genuinely
  still has zero reachable abuse escalation, so its "the deterministic
  abuse-detection layer does not exist yet" statement remains accurate.
  **This will need updating the moment Slice 3b actually merges** — done,
  see the Slice 3c entry below (`docs/SECURITY.md` was updated for both
  Slice 3b's live escalation and Slice 3c's audit emission in the same
  pass, once Slice 3b had actually merged).

## Completed work (Redis abuse layer — Slice 3c: audit emission + HTTP-level tests)

**Uncommitted, working-tree-only.** Adds abuse-escalation audit emission
on top of Slice 3b's now-merged decision engine — no production
abuse-decision code modified, only consumed.

- **`app/core/audit.py`** (additive): one new constant,
  `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` — no existing constant or
  the `record()` function's signature changed.
- **`app/api/v1/auth.py`** (modified): a new `_audit_abuse_escalation()`
  helper, called from `login`/`forgot-password`/`reset-password` right
  after each `record_login_failure()`/`record_forgot_password_request()`/
  `record_reset_validation_failure()` call:
  - Fires only when `outcome.newly_escalated` is `True` — never on an
    already-escalated repeat, never for an ordinary `ALLOW` (this
    function is only ever called with the result of a `record_*` call,
    itself only reached after a real outcome is known).
  - Event type: `AuditEvent.RATE_LIMITED` for `STRICT_THROTTLE`,
    `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` for `TEMPORARY_BLOCK`.
  - Metadata: `rule`/`operation`/`dimension` always; `account_hash`
    (already HMAC-hashed, never raw) when the dimension is
    account-scoped; `block_ttl_seconds` (600, from
    `abuse_state.TEMPORARY_BLOCK_TTL_SECONDS`) for blocks. Never a raw
    email, password, reset token, or refresh token.
  - `user_id` is always `None` — none of the three call sites have a
    resolved user at this point (a failed login never returns one;
    forgot-password/reset-password never expose one to this layer) —
    never invented.
  - `ip_address` is the same trusted-proxy-resolved `AbuseContext.ip`
    the abuse decision itself acted on, not the separate, unconditional
    `client_ip()` used elsewhere for session/authorization audit rows.
- **`tests/test_abuse_audit.py`** (new, 6 HTTP-level tests, real Redis +
  real PostgreSQL, no mocks): repeated login failures → R1
  `STRICT_THROTTLE` + exactly one `RATE_LIMITED` row + strict-bucket
  consumption proof (2 allowed, 3rd rejected) + no duplicate rows;
  account-scoped R2 through the endpoint + account isolation; 5 distinct
  IPs against one account → R3 `TEMPORARY_BLOCK` + exactly one
  `ABUSE_TEMPORARY_BLOCK_APPLIED` row with `block_ttl_seconds` + the
  account rejected outright afterward, before `auth_service` ever runs;
  R4 forgot-password strict-throttle with enumeration-resistant
  responses intact throughout; R5 reset-password validation failures →
  `TEMPORARY_BLOCK` + audit row + subsequent outright rejection;
  successful login resetting R2/R3 but not R1, with zero abuse-audit
  rows from an ordinary below-threshold sequence.
  - **Two test-design bugs found and fixed during this slice's own
    validation** (not production defects): (1) the initial approach
    tried to pre-fill the *base* `rl:*` token bucket with an abundant
    token count to reach abuse thresholds (10–15) faster than the base
    bucket's own small capacity (5–10) would otherwise allow — this
    doesn't work, because the Lua bucket script always clamps effective
    tokens at the dimension's configured `capacity` regardless of what's
    stored, so no amount of pre-written state lets more than `capacity`
    real requests through in one window. Fixed by pre-seeding the
    *abuse-layer's own* counters directly via the same production
    `record_*` functions the endpoint itself calls (real code, not a
    mock), reserving real HTTP calls for the actually-interesting final
    transition and its surrounding assertions. (2) One assertion assumed
    the shared, persistent `audit_logs` table would show zero
    `LOGIN_SUCCEEDED` rows — wrong, since real historical rows already
    existed from earlier manual verification sessions against the live
    Docker stack (confirmed by direct query: 5 rows, all
    `ip_address='172.18.0.1'`, dated 2026-09-14). Fixed by scoping the
    assertion to the test's own unique IP instead of a bare global count.
  - `ruff`/`mypy` clean. **6/6 passed, 3 consecutive runs**, alongside
    the complete **254-test backend suite passing 254/254, 3 consecutive
    runs** — all against real Redis and real PostgreSQL inside
    `compose-backend-1` (the host shell's own published-port path
    remained broken this session too, confirmed again before falling
    back to the established container-based validation approach).
- **Documentation updated this slice**: ADR 0006 (Implementation status
  table updated for Slice 3b's merge and the new audit-emission row),
  `docs/SECURITY.md` (the "Rate limiting" section's stale "abuse-
  detection layer does not exist yet" statement corrected now that
  Slice 3b has actually merged; the "Audit logging" section extended for
  the two new event types and their metadata/`user_id` conventions),
  `PROJECT_STATE.md`, this file.

## Completed work (Playwright E2E — authentication/password-recovery)

**This work has since been committed, pushed, opened as PR #16, and
merged into `main` as squash commit `e1c4858`, with CI green.** The
record below is kept as accurate history of the implementation/
validation itself, not as current status — see "Current task" above.

No Playwright infrastructure existed before this — `@playwright/test`
was not installed (only present transitively, unused, in
`frontend/package-lock.json`'s dependency graph); introduced fresh.

- **`frontend/playwright.config.ts`** (new): `baseURL` from
  `PLAYWRIGHT_BASE_URL` (default `http://localhost:3000`); Chromium only,
  for now; `trace`/`screenshot`/`video` captured `retain-on-failure`/
  `only-on-failure` for debugging without bloating every run.
  **`workers: 1`, `fullyParallel: false`, deliberately** — the backend's
  base rate limiter and the deterministic abuse layer (ADR 0006) both key
  partly by source IP, and every Playwright request in a run shares one
  peer address; parallel specs would risk a real, correctly-functioning
  `429` unrelated to what any individual test checks.
- **`frontend/e2e/fixtures/`**: `users.ts` (unique-email/password
  helpers, mirroring the backend pytest suite's own `_unique_email()`
  pattern); `mailpit.ts` (polls Mailpit's real REST API —
  `http://localhost:8025` — for the password-reset email by recipient
  and subject, extracts the reset link by regex; a genuine poll loop for
  real, variable SMTP-capture delivery latency, not a fixed sleep);
  `auth-helpers.ts` (`registerViaUi`/`loginViaUi`/`logoutViaUi`/
  `readBrowserStorage`, all driving the real UI, never a direct API
  shortcut for the flows actually under test).
- **`frontend/e2e/app-availability.spec.ts`** (3 tests): the home page
  loads with no unexpected console errors, an anonymous visitor sees
  the log in/register entry points, the backend readiness endpoint the
  application itself depends on is reachable and reports `ready`.
- **`frontend/e2e/auth.spec.ts`** (9 tests, 2 `describe.serial` blocks
  each driving one shared `page` created in `beforeAll` — `.serial()`
  alone does not share a page/context between tests, so each block
  creates and closes its own explicitly): short-password client-side
  validation (no request sent); a full register → verify no token in
  `localStorage`/`sessionStorage` → reload persists the session → logout
  ends it → an unauthenticated visitor is redirected away from a
  protected route journey; a separate login → storage-security check →
  **CSRF negative case** (a state-changing `POST` with the session's real
  cookies but no `X-CSRF-Token` header — the exact shape the
  double-submit pattern exists to reject — gets a real `403` from the
  real middleware) → **CSRF positive case** (the same mutation through
  the real UI, which does attach the header, succeeds) journey.
- **`frontend/e2e/password-recovery.spec.ts`** (7 tests, one
  `describe.serial` block): forgot-password for an existing account and
  for a nonexistent one return the identical generic message
  (enumeration resistance); the real email is read back through Mailpit,
  the reset link is followed, the new password is accepted, and no
  token/link is left in browser storage; the old password stops
  authenticating (with the backend's own generic
  "Incorrect email or password." message — itself further
  enumeration-resistance evidence); the new password authenticates; and
  — the one test needing genuinely persistent pre-reset session state —
  the pre-reset session's **refresh capability** (not its short-lived
  access token, which is documented, intentional, not-retroactively-
  invalidated behavior — ADR 0003's hot-path trade-off, already proven
  by the backend's own
  `test_password_reset_does_not_retroactively_invalidate_an_already_issued_access_token`)
  is confirmed revoked (`401`) by a direct, CSRF-header-attached
  `POST /api/v1/auth/refresh` using that session's own cookies.
- **Genuine findings from this validation, all fixed as test-code
  corrections — no application/production code was changed for any of
  them:**
  1. A locator using `getByText(workspaceName)` hit a real strict-mode
     ambiguity — the created workspace's name legitimately renders in
     three places at once (the workspace switcher, the list, and its own
     detail heading), which is correct application behavior, not a bug.
     Fixed by scoping the assertion to the main content region.
  2. A direct `POST /api/v1/auth/refresh` call meant to prove session
     revocation returned `403`, not the expected `401` — because, like
     `/api/v1/workspaces`, `/refresh` is itself a state-changing,
     CSRF-protected endpoint, and the raw request (deliberately, in the
     *other*, adjacent CSRF-negative test) didn't attach the header.
     Fixed by reading the session's own `csrf_token` cookie and attaching
     it, matching what `lib/api-client.ts` already does for every real
     request.
  3. `page.on("console", ...)` with `type() === "error"` also captures
     Chromium's own "Failed to load resource: 401" log line for the
     anonymous-visitor auth-bootstrap check
     (`GET /api/v1/users/me` on mount, `lib/auth-context.tsx`) —
     expected, already-caught application behavior, not a fatal error.
     Fixed by filtering that specific, well-understood log pattern while
     still catching any other console error and any genuine uncaught
     exception (`pageerror`, a separate listener, unchanged).
- **`ruff`/`npx eslint e2e/ playwright.config.ts`/`npx tsc --noEmit`**
  all clean. **19/19 passed, 3 consecutive clean runs.** The first
  attempt at 3 back-to-back runs (no gap) hit a real, correctly-working
  `429` from the backend's own `register` rate limiter (capacity 5/60s
  per source IP) — not flakiness, a deterministic consequence of firing
  ~9 registrations inside one 60-second window across 3 runs. Re-run
  cleanly 3 times with the real bucket's own TTL-based refill (polled via
  `redis-cli TTL`, not a blind sleep) between runs. **This means: do not
  fire the full E2E suite repeatedly back-to-back with no gap** — a
  single CI job run is unaffected (one run, once), but local repeat runs
  for flakiness-hunting need the same spacing.
- Existing frontend suite (**48 vitest tests**) and `npm run lint`
  confirmed unaffected/still clean.
- **`.github/workflows/ci.yml`** gained a new `e2e` job (after
  `backend`/`frontend` pass): real Postgres/Redis/Mailpit service
  containers, the real backend (`uvicorn`) and frontend (`next dev`)
  started as background processes with a deterministic readiness-poll
  wait (not a fixed sleep), then `npm run test:e2e`; uploads the HTML
  report (and, on failure, the server logs — no secrets) as build
  artifacts. **Not yet run on GitHub Actions as of this entry** — this
  session's own validation was local, against the already-running
  `docker compose` stack; the CI job's exact behavior will be confirmed
  once the PR is actually opened and CI runs for real, not claimed here
  in advance.
- **This is not a production validation.**

## Completed work (Issue #3 — Slice 3.1: document data model + migration)

**This work has since been committed, pushed, opened as PR #17, and
merged into `main` as squash commit `79d4787`, with CI green (4/4
checks).** The record below is kept as accurate history of the
implementation/validation itself, not as current status — see "Current
task" above.

Schema only — per this slice's explicit scope, no upload API, storage
abstraction, text extraction, chunking, background processing, or
embedding code was added.

- **`backend/app/models/document.py`** (new): `Document` model —
  `documents` table. `workspace_id` (`ON DELETE CASCADE`, indexed);
  `uploaded_by` nullable, `ON DELETE SET NULL` (matches `AuditLog.user_id`'s
  precedent — a document should outlive the account that uploaded it,
  not disappear when the account is removed); `filename`/`mime_type`/
  `size_bytes`/`checksum_sha256`/`storage_key` (server-generated, unique
  — never the user-supplied filename, per `docs/SECURITY.md` "Upload &
  document safety"); `status` as a new `DocumentStatus` native Postgres
  enum (`document_status`) matching the documented lifecycle exactly
  (`docs/REQUIREMENTS.md`/`docs/RAG_DESIGN.md`): `UPLOADED → PROCESSING →
  PARSED → CLEANED → CHUNKED → EMBEDDED → INDEXED → READY / FAILED`. A
  native enum was chosen over a plain string (unlike `audit_logs.event_type`,
  which is deliberately open-ended) because this lifecycle is a fixed,
  closed set defined once by the project specification — following
  `WorkspaceMember.role`'s (`workspace_role`) convention instead.
  `failure_reason`/`page_count`/`processing_started_at`/
  `processing_completed_at` all nullable. `UNIQUE(storage_key)` and
  `UNIQUE(workspace_id, checksum_sha256)` (duplicate-upload detection,
  scoped per workspace, not global — the same checksum in two different
  workspaces is allowed).
- **`backend/app/models/document_chunk.py`** (new): `DocumentChunk`
  model — `document_chunks` table. `document_id` (`ON DELETE CASCADE`,
  indexed); `workspace_id` deliberately denormalized (also indexed) —
  every future workspace-scoped retrieval/security query needs to filter
  chunks by workspace without an extra join; `chunk_index`/`page`/
  `section`/`content`. `UNIQUE(document_id, chunk_index)`, scoped per
  document, not global. **No embedding column** — see the next bullet.
- **Deliberately no pgvector column yet**: choosing `VECTOR(n)` now would
  lock the schema to an embedding model/dimension before the
  `EmbeddingProvider` abstraction is designed in a later slice; adding it
  is planned as a small additive migration once that choice is actually
  made, not a breaking change to this one.
- **`backend/alembic/versions/0004_add_documents_and_document_chunks.py`**
  (new): reversible migration for both tables, following `0002`/`0003`'s
  style (the `document_status` enum type is created by `create_table`'s
  column type hook, matching how `0002` creates `workspace_role` — no
  separate `.create()` call). `downgrade()` drops both tables' indexes,
  both tables, then the enum type.
- **`backend/app/models/__init__.py`** (modified): registers `Document`/
  `DocumentChunk`/`DocumentStatus` on `Base.metadata` so Alembic
  autogenerate and the test suite's session-scoped migration fixture see
  them, matching every prior model's registration pattern.
- **`backend/tests/test_document_schema.py`** (new, 19 tests, real
  Postgres via `tests/conftest.py`'s `db_session` fixture, no mocks):
  table existence; a document referencing an existing workspace/uploader;
  `uploaded_by` nullability; invalid workspace FK rejected
  (`IntegrityError`); the workspace+checksum unique constraint, and that
  it's correctly *not* global (same checksum across two different
  workspaces is allowed); the storage-key unique constraint; a chunk
  referencing its document/workspace; invalid document FK on a chunk
  rejected; the document+chunk_index unique constraint, and that it's
  correctly *not* global (same `chunk_index` across two different
  documents is allowed); cascade delete from `documents` to
  `document_chunks`; nullable-metadata-field defaults; `DocumentStatus`
  defaulting to `UPLOADED` and persisting a mutation; database-assigned
  timestamps on both tables.
  - **One genuine test-design bug found and fixed during this slice's
    own validation** (not a schema/migration defect): the first version
    of the cascade-delete test called `db_session.get(DocumentChunk,
    chunk_id)` right after deleting the parent `document` and flushing —
    `ON DELETE CASCADE` ran correctly in Postgres, but the SQLAlchemy
    session's identity map still held the pre-delete `chunk` object
    (the ORM was never told about the DB-level cascade), so `.get()`
    returned the stale cached instance instead of re-querying and
    getting `None`. Fixed by calling `db_session.expire_all()` before
    the assertion.
  - `ruff`/`mypy` clean (86 source files, only 2 mypy findings surfaced
    along the way, both fixed: `sa.inspect(db_session.bind)` typed as
    `Any | None` — switched to `sa.inspect(engine)`, the same real bind
    `conftest.py` itself uses).
  - **Real-Postgres validated**: **19/19 new tests passing**; the
    complete backend suite **273/273 passing** (254 pre-existing + 19
    new), **3 consecutive runs**, no flakiness, no regression in any
    existing auth/workspace/rate-limit/abuse-protection test.
  - **Migration `0004` explicitly verified reversible**, not just
    assumed from the code: `alembic downgrade 0003` removes both tables
    and the `document_status` enum (confirmed via `sqlalchemy.inspect`
    against the real database); `alembic upgrade head` re-creates both
    tables with the correct column set; the full suite re-run clean
    afterward.
  - This session hit a genuine environment interruption mid-task:
    Docker Desktop's WSL integration dropped (the `docker` CLI briefly
    reported "command could not be found in this WSL 2 distro" after
    working moments earlier) and had to be restored on the Windows side
    before any of the above could run — not a code or schema defect;
    documented here per this project's established practice of recording
    genuine Docker/WSL environment faults rather than silently working
    around or omitting them.
- **Docs updated this slice**: `docs/DATA_MODEL.md` (`documents`/
  `document_chunks` moved PROPOSED → IMPLEMENTED, schema only; the chunk
  metadata list annotated field-by-field; the embedding-column decision
  documented explicitly), `PROJECT_STATE.md`, `CHANGELOG.md`, this file.
  Also reconciled in the same pass, per explicit instruction: `PROJECT_STATE.md`/
  `HANDOFF.md`/`CHANGELOG.md` still described the already-merged
  Playwright E2E work (PR #16, `e1c4858`) as uncommitted — corrected
  throughout all three files (see "Completed work (Playwright E2E...)"
  above for its own updated status note, and the `CHANGELOG.md` entry
  moved from "Unreleased — working tree" to "Unreleased — committed"
  with the real commit hash).

## Completed work (Issue #3 — Slice 3.2: StorageProvider abstraction)

**Implemented, tested, committed as `91d98b7` (plus a docs commit,
`d57ccdb`), pushed, opened as PR #18, and merged into `main` as squash
commit `941c1a7`. A correctness/security review's own fix (below)
landed too late to be included in that PR — it shipped separately as
PR #19, squash commit `5e6fdc2`, also merged.** Storage abstraction only — per this slice's explicit scope,
no upload endpoint, text extraction, chunking, background processing, or
embedding code was added; nothing in the codebase calls
`get_storage_provider()` yet.

- **`backend/app/services/storage_provider.py`** (new): mirrors
  `EmailProvider`'s exact shape (`app/services/email_provider.py`) — a
  `StorageProvider` `Protocol` (`save`/`read`/`delete`/`exists`, all
  keyword-only) plus `LocalStorage`, a filesystem-backed implementation
  for local dev/CI, and `get_storage_provider()`, a settings-driven
  factory. `get_storage_provider()` has no branching yet (only "local"
  exists) — it gains an `if`/`elif` when a second implementation is
  actually added, matching how `get_email_provider()`'s own factory
  evolved from one branch to two.
  - **Path safety**: storage keys are always server-generated upstream
    (never a user-supplied filename — `docs/SECURITY.md` "Upload &
    document safety"), but `LocalStorage._resolve()` still rejects any
    key that would resolve outside its configured root as defense in
    depth: empty keys, keys starting with `/`, and any key containing a
    `..` path segment are all rejected — checked both by string/parts
    inspection *and* by resolving the candidate path and confirming it's
    still relative to the root (`Path.relative_to()`, raising
    `ValueError` — caught and re-raised as `StorageKeyError` — for
    anything that escapes). Every one of the four operations
    (`save`/`read`/`delete`/`exists`) calls `_resolve()` first, so the
    check can't be bypassed by calling a different method.
  - **Errors**: a dedicated `StorageError`/`StorageKeyError` hierarchy —
    never a raw `OSError`/`FileNotFoundError` escaping this module, so a
    future endpoint layer can map these to the shared `{"error": {...}}`
    shape (`app/core/errors.py`) without needing to know filesystem
    detail, matching this codebase's existing exception-boundary
    convention.
  - `save()` creates parent directories as needed
    (`path.parent.mkdir(parents=True, exist_ok=True)`) — keys are
    expected to be namespaced (e.g.
    `{workspace_id}/{document_id}/{uuid}.pdf`), so this avoids requiring
    every caller to pre-create directory structure.
  - `delete()` of a nonexistent key is a no-op (`Path.unlink(missing_ok=True)`)
    — deliberately, since a future delete endpoint calling this after
    the database row is already gone (or never fully written) shouldn't
    itself become a new failure mode.
- **`backend/app/core/config.py`** (modified): `storage_provider` changed
  from `str | None = None` to `Literal["local"] = "local"` (the only
  implementation today, following `email_provider`'s
  `Literal["console", "smtp"]` precedent); new `storage_local_root: str
  = "./data/documents"`. `storage_bucket` stays reserved, unused, for a
  future object-storage provider.
- **`.env.example`** (modified): documents `STORAGE_PROVIDER`
  (now defaulted to `local` rather than blank, since it's actually
  consumed now) and the new `STORAGE_LOCAL_ROOT`.
- **`.gitignore`** (modified): excludes `data/`/`backend/data/` (the
  local storage root's default location) so dev/test uploads are never
  committed — this slice's own tests use `tmp_path`, not this default
  location, so this is precautionary for future manual/dev use, not
  something this slice's own validation depended on.
- **`docs/ARCHITECTURE.md`** (modified): the "Provider abstractions"
  section's table now marks `StorageProvider` IMPLEMENTED with a short
  description; every other provider interface remains PROPOSED,
  unchanged.
- **`backend/tests/test_storage_provider.py`** (new, 14 tests, against a
  real filesystem via pytest's `tmp_path` — no mocks): save/read
  round-trip; nested-parent-directory creation; `exists()` reflecting
  save/delete; delete-of-nonexistent-key is a no-op; read-of-nonexistent-
  key raises `StorageError`; five unsafe keys (`../escape.txt`,
  `a/../../escape.txt`, `../../etc/passwd`, `/etc/passwd`, and an empty
  string) each rejected on `save()`; the same unsafe key rejected on
  `read()`/`exists()`/`delete()` too, not just `save()`; two different
  keys don't collide; `get_storage_provider()` returns a `LocalStorage`
  instance; the `storage_provider`/`storage_local_root` settings default
  correctly.
  - `ruff`/`mypy` clean (88 source files). **14/14 new tests passing**;
    the complete backend suite **287/287 passing** (273 pre-existing +
    14 new), **3 consecutive runs**, no flakiness, no regression in any
    existing test (auth/workspace/rate-limit/abuse/document-schema all
    unaffected). This slice touches no database/Redis state, so the
    existing real-Postgres/real-Redis validation the rest of the suite
    already provides is what confirms no regression — no new
    Postgres/Redis-specific validation was needed for this slice's own
    code.

### Correctness/security review, and the fix it produced

A dedicated review of the above, intended as a final pre-merge check on
Slice 3.2, found one genuine gap: `LocalStorage.read()` translated only
`FileNotFoundError` to `StorageError`; `save()`/`delete()`/`exists()`
had no filesystem-error handling at all. A `PermissionError` (or any
other `OSError` — disk full, etc.) would escape the module raw — and
Python's own `OSError` message includes the absolute path of the
operation that failed, which would have leaked the configured storage
root, directly contradicting this module's own documented "never leaks
a raw filesystem path" contract.

**The review ran concurrently with PR #18 actually being merged** (by
the repository owner directly, independent of this review) **— so by
the time the fix was ready, PR #18 was already closed and could not
receive more commits.** The fix (originally committed as `050b185`/
`03c870e` on the now-merged branch) was cherry-picked as `6e96481`/
`d950d4e` onto a fresh branch cut from the merged `941c1a7`, so it ships
as its own small follow-up rather than being lost or silently dropped.

- **Fixed**: `save()`/`delete()` now each wrap their filesystem calls in
  `try/except OSError`, raising `StorageError` with a message built only
  from the caller-supplied `key` — never the resolved absolute path.
  `read()` keeps its existing `FileNotFoundError` → "not found" `StorageError`
  for that specific case, with a second, broader `except OSError` beneath
  it for anything else. `_resolve()`'s own `.resolve()` call is now
  wrapped too, as defense-in-depth against a resolution-time `OSError`
  (e.g. a stale network-mount handle) — see the finding below on why this
  branch isn't provably reachable by a test, kept anyway since it's cheap
  and correct.
- **A second, related gap found empirically, not by inspection**: the
  original code assumed (and said in a comment) that `Path.is_file()`
  swallows `OSError` internally, so `exists()` needed no guard of its
  own. Actually running a permission-denied test against this project's
  real Python version (3.13.15) disproved that — `is_file()` calls
  `stat()` directly and lets `PermissionError` propagate raw. `exists()`
  now has its own `try/except OSError` too, exactly like the other three
  methods; the comment that had claimed otherwise is corrected.
- **What was empirically disproven along the way** (recorded so a future
  session doesn't re-assume it): neither `Path.resolve()` nor
  `Path.is_file()` reliably swallow `OSError` on this runtime for a
  blocked-containing-directory scenario — `resolve()` succeeds lexically
  regardless (even across a symlink inside a directory with no execute
  permission), and `is_file()`'s failure surfaces only when it actually
  calls `stat()` on the final path. The one place a permission problem
  reliably raises is at each operation's own terminal filesystem call —
  which is exactly where each method's own guard now sits.
- **7 new tests** (`tests/test_storage_provider.py`, 14 → 21): a symlink
  planted inside the root that would resolve outside it (`StorageKeyError`,
  proving the traversal check works against symlinks, not just literal
  `".."` segments — separately from the existing literal-`".."` cases);
  permission-denied `save()`/`read()`/`delete()`/`exists()` each raising
  `StorageError`, never a raw `OSError`/`PermissionError`, and never
  containing the configured `tmp_path` root in the message; `exists()`
  still correctly returning `True` when only a *file's own* permission
  bits (not its containing directory) are restricted, since that doesn't
  block `stat()` the way it blocks `read()`. Permission-based tests are
  skipped under `os.geteuid() == 0` (root bypasses filesystem permissions
  entirely, which would make them fail or test nothing meaningful) —
  both this environment and the CI runner (a GitHub-hosted `ubuntu-latest`
  VM, not a container) run as non-root, so none of the 7 new tests were
  actually skipped this session; the guard exists for robustness, not
  because it was needed here.
- Also reviewed and confirmed already correct, no change needed: unsafe
  keys are rejected on every operation, not just `save()` (already
  covered by the pre-existing
  `test_unsafe_key_rejected_on_read_exists_and_delete_too`); storage keys
  remain always server-generated upstream, never a user-supplied
  filename (no code path in this module accepts one); no upload endpoint
  exists yet, so no HTTP surface/authentication/rate-limiting/workspace-
  authorization is applicable to add; no secrets or file contents are
  logged anywhere in this module (it has no logging at all).
- **`get_storage_provider()`'s factory test reviewed for determinism**
  (the review specifically asked whether it might accidentally depend on
  an already-cached global `Settings` instance): confirmed already
  deterministic and left unchanged — `storage_provider` is
  `Literal["local"]`, the only legal value, and no other test in the
  suite touches `STORAGE_PROVIDER`/`STORAGE_LOCAL_ROOT`, so
  `get_storage_provider()` returns a `LocalStorage` instance regardless
  of process-wide cache state or test execution order; there is no
  second branch for a differently-configured cache to select.
- `ruff`/`mypy` clean (88 source files, no new findings). **21/21 storage
  tests passing**; the complete backend suite **294/294 passing** (273
  pre-existing + 21 new), **3 consecutive runs**, no regression in any
  existing test.
- **Docs updated this pass**: `docs/SECURITY.md` ("Upload & document
  safety" — a new "Implemented" paragraph documenting the enforced
  generated-identifier/path-traversal requirement and the error
  contract), `PROJECT_STATE.md`, `CHANGELOG.md`, this file.

- **Docs updated this slice**: `docs/ARCHITECTURE.md` (as above),
  `PROJECT_STATE.md`, `CHANGELOG.md`, this file.

## Completed work (Issue #3 — Slice 3.3: document upload API)

**This work has since been merged into `main` as squash commit
`a6762e2` via PR #20, by the repository owner (not by this agent). The
record below is kept as accurate history of the implementation/
validation itself, not as current status — see "Current task" above.**
Adds exactly
one capability: `POST /api/v1/workspaces/{workspace_id}/documents`
(`multipart/form-data`, field `file`). A successful upload authenticates,
authorizes (MEMBER), rate-limits, validates, checksums, checks for a
workspace-scoped duplicate, writes to `StorageProvider`, creates the
`documents` row, emits the audit event, commits, and returns `201`. The
document stays in `UPLOADED` — no later lifecycle state, no extraction,
chunking, embedding, or background processing.

- **`backend/app/api/v1/documents.py`** (new): the route. Resolves
  authorization via the existing `require_workspace_role(WorkspaceRole.MEMBER)`
  dependency (no duplicate workspace-authorization logic written) and
  `StorageProvider`/`redis.Redis | None` via `Depends(get_storage_provider)`/
  `Depends(get_redis_client)` — both already dependency-injection-shaped,
  so tests override them exactly like `get_db` is already overridden.
  Calls `enforce_document_upload_rate_limit()` explicitly in the route
  body (after the workspace-authorization dependency has already run,
  matching the intended "authorize, then rate-limit" order) rather than
  as its own `Depends()` — see the rate-limiting entry below for why.
- **`backend/app/services/document_service.py`** (new): the
  orchestration. Ordering: extension/MIME check (no body read yet) →
  stream-read the body in 1 MiB chunks, computing the SHA-256 digest and
  aborting as soon as the running total exceeds `max_upload_size_bytes`
  (never buffers an oversized payload first) → magic-byte signature
  check on the now-fully-read content → workspace-scoped duplicate
  pre-check → generate a storage key from trusted identifiers only
  (`{workspace_id}/{document_id}{validated_extension}` — the client
  filename never contributes) → `storage.save()` → `_persist_document()`.
  - **File-type validation**: extension allowlist (`.pdf`/`.docx`/`.txt`/
    `.md`/`.csv`, case-insensitive), a matching MIME allowlist per
    extension (including named real-world browser variants for `.md`/
    `.csv` — `text/plain` for both, `text/x-markdown` for `.md`,
    `application/vnd.ms-excel` for `.csv` — never an arbitrary/wildcard
    MIME), and a magic-byte signature check for the two binary formats
    with a real, stable signature (`%PDF-` for PDF, the ZIP local-file
    header `PK\x03\x04` for DOCX — DOCX's signature also matches any
    other ZIP-based file, an accepted limitation of a byte-level
    heuristic). Plain-text formats have no reliable signature — the
    check is skipped for them, documented as a real gap, not silently
    pretended otherwise. None of these three signals, individually or
    together, prove the file is well-formed or safe to parse.
  - **Storage/database consistency** (the design's own explicit focus):
    storage always succeeds before any database write is attempted. If
    the subsequent `document_repository.create()` (`add()` + `flush()`,
    never `commit()` — matching every other repository's convention)
    then fails for any reason — a losing race against another request's
    identical `(workspace_id, checksum_sha256)`, or any other genuine DB
    error — `_persist_document()` catches it, calls `db.rollback()`
    (required before the session can be used again after a failed
    flush), attempts a best-effort `storage.delete()` of the
    just-written object (logging identifiers, never a path, if that
    delete itself fails — never letting a cleanup failure replace or
    mask the original error), and either raises the documented `409`
    (if a race-lost duplicate — re-queries for the winning row and
    references its `id`) or re-raises the original exception unmodified
    (any other DB failure, surfacing as `500` through the existing
    global exception handler, never a raw `OSError`/SQL error/stack
    trace). `record_audit_event()`'s own `db.commit()` — confirmed by
    reading `audit_log_repository.create()` directly, not assumed —
    commits on the *same* `Session`, so the document insert (already
    flushed) and the new audit row commit together as one Postgres
    transaction; no second, independent commit call was needed for the
    document row itself.
  - **Duplicate uploads**: `409` with `code: "duplicate_document"`,
    referencing the existing document's `id` in the message (the shared
    error-response shape has no room for extra structured fields, so the
    id is embedded in the human-readable message text rather than
    extending `app/core/errors.py`). A pre-check (before any storage
    write) handles the common case cheaply; the existing
    `UNIQUE(workspace_id, checksum_sha256)` constraint (Slice 3.1)
    remains the authoritative backstop for the race window between the
    pre-check and the insert. Both are workspace-scoped — the same
    checksum in a different workspace is unaffected, never even visible.
- **`backend/app/repositories/document_repository.py`** (new):
  `get_by_workspace_and_checksum()` and `create()`. `create()` takes an
  explicit `id: uuid.UUID` parameter (the caller generates it) rather
  than relying on the model's own `default=uuid.uuid4` — the storage key
  is built from that same document ID *before* this insert ever runs
  (storage must succeed first), so the row's actual `id` and the file's
  actual location have to agree; a genuine bug caught and fixed during
  implementation, before any test ran, not left for a test to discover.
- **`backend/app/schemas/document.py`** (new): `DocumentRead` — never
  includes `storage_key`.
- **`backend/app/core/audit.py`** (additive): one new constant,
  `AuditEvent.DOCUMENT_UPLOADED`.
- **`backend/app/core/rate_limit.py`** (additive): `upload_rate_limiter`
  (20/60s) and `enforce_document_upload_rate_limit()` — Tier A (falls
  back to the in-process limiter on a genuine Redis outage, never fails
  open, matching `login`/`refresh`/`forgot-password`/`reset-password`,
  not `register`'s Tier B), dimensioned by IP and the authenticated
  user's ID. Deliberately a **plain function, not itself a
  `Depends()`-shaped dependency**: it needs the authenticated caller's
  ID, only available after `require_workspace_role` has run, and
  importing `get_current_user` from `app.core.dependencies` into this
  module would create a circular import (`dependencies.py` already
  imports `client_ip` from `rate_limit.py`) — the same class of cycle
  `token_bucket_types.py` was extracted to solve for the abuse layer in
  an earlier slice. The route calls it explicitly instead. No
  abuse-decision-layer (R1–R5) consultation — that rule table targets
  the login/forgot-password/reset-password credential-stuffing threat
  model specifically; extending it for uploads wasn't warranted.
- **`backend/app/core/config.py`** (additive): `max_upload_size_bytes`
  (default 50 MiB).
- **`backend/app/api/v1/router.py`** (modified): registers the new
  `documents_router`.
- **New dependency**: `python-multipart` (`backend/pyproject.toml`/
  `uv.lock`) — required by FastAPI/Starlette for any `UploadFile`/`File`
  route parameter; the app fails to start without it (`RuntimeError`
  caught during a pre-test `create_app()` smoke check, not discovered
  via a failing test).
- **`backend/tests/test_document_service.py`** (new, 37 unit tests, no
  database, no HTTP): extension normalization/allowlisting (including
  that `../../etc/passwd.pdf` normalizes to just `.pdf` — a pure string
  operation, not filesystem path handling), every allowed/disallowed
  MIME combination including the named browser variants, magic-byte
  match/mismatch for PDF and DOCX, the "no signature check" behavior
  for the three text formats, storage-key generation (trusted
  identifiers only, never a filename fragment), and the streamed
  checksum/size-limit reader (via a minimal fake `UploadFile`
  stand-in) — both the correct-checksum case and the
  aborts-before-buffering-the-whole-oversized-payload case.
- **`backend/tests/test_document_upload.py`** (new, 30 HTTP-level
  tests, real Postgres/Redis/filesystem, no mocks): every item from the
  task's own 27-point list is covered — see `docs/API_CONTRACT.md`'s
  and `docs/SECURITY.md`'s updated sections for the security-relevant
  subset, and `PROJECT_STATE.md`'s Testing row for the full enumeration.
  Two things worth flagging specifically:
  - **A real Starlette/FastAPI behavior, not a bug**: `TestClient`'s
    default `raise_server_exceptions=True` re-raises a truly unhandled
    exception straight to the test (for debugging visibility) instead of
    letting the app's own registered `Exception` handler convert it to
    a response. The one test that deliberately provokes an unhandled
    `StorageError` (a broken storage backend) needs
    `TestClient(app, raise_server_exceptions=False)` — with the
    original client's cookies copied over — to observe the actual
    client-visible `500` response instead of the raw Python exception.
    Every other test uses the normal shared `client` fixture; `409`s,
    `404`s, etc. are ordinary `HTTPException`s and were never affected
    by this.
  - **Per-test storage isolation**: an autouse fixture overrides
    `get_storage_provider` to a `tmp_path`-backed `LocalStorage` for
    every test in the file — no test writes into the real configured
    dev storage root (`./data/documents`).
  - `ruff`/`mypy` clean (94 source files). **67/67 new tests passing**;
    the complete backend suite **361/361 passing** (294 pre-existing +
    67 new), **3 consecutive runs**, no regression in any existing
    test. Frontend (`npm run lint`/`typecheck`/`test`) re-confirmed
    unaffected — no frontend file changed. Full manual smoke test
    against the real Docker Compose stack (after rebuilding the
    previously-stale `compose-backend-1` image — see "Blockers" above):
    register → create workspace → upload a real PDF via `curl`,
    verified `201` with the correct body, and the file landing at the
    expected path inside the container's own filesystem.
- **Docs updated this slice**: `docs/API_CONTRACT.md` (new
  `/api/v1/workspaces/{workspace_id}/documents` implemented section;
  the "Target namespaces" table's flat `/api/v1/documents` entry
  corrected to the nested path actually used), `docs/SECURITY.md`
  ("Upload & document safety" extended with the Slice 3.3 detail;
  "Audit logging" and "Security testing" bullets updated from their
  previous "not implemented yet" state), `PROJECT_STATE.md`,
  `CHANGELOG.md`, this file.

### Pre-merge correctness review, and the fix it produced

A dedicated review of the above, still on PR #20 before merge, traced
the full upload sequence's failure paths explicitly (storage failure,
DB failure after a successful storage write, a race-lost duplicate
insert, and — the one that surfaced a genuine gap — a *compensating
cleanup* failure) and found one real issue:

- **`_cleanup_orphaned_storage_object()` only caught `StorageError`.**
  `StorageProvider` is a `Protocol`, not an enforced base class — nothing
  guarantees every implementation's `delete()` only ever raises
  `StorageError` (today's `LocalStorage` does, by its own Slice 3.2
  contract, but this function shouldn't depend on that holding for every
  future implementation). A cleanup-time failure of any other exception
  type would have propagated uncaught out of the `except` block that
  calls it, silently replacing the real error (e.g. a genuine
  race-lost-duplicate `409`) with whatever the cleanup attempt itself
  raised — exactly the "cleanup failure masks the original error"
  failure mode this function's own docstring already said must never
  happen, just not fully guarded against.
- **Fixed**: broadened the `except StorageError` to `except Exception` —
  still never re-raises, still only logs (`storage_key` only, never a
  path), so the calling code's original exception is always what
  actually propagates.
- **New regression test**
  (`test_cleanup_failure_of_any_exception_type_never_masks_the_original_error`,
  `tests/test_document_upload.py`): a storage stand-in whose `delete()`
  raises a plain `RuntimeError` (not `StorageError`), forcing the
  race-lost-duplicate path against real Postgres. Confirms the client
  still sees the original `409` referencing the winning document's id —
  never the `RuntimeError`, never a `500`.
- **Also verified and confirmed correct, no change needed** (per the
  review's own explicit checklist): the audit-commit atomicity claim —
  traced `document_repository.create()` (`add()`+`flush()`, no commit)
  →  `record_audit_event()` → `audit_log_repository.create()`'s own
  `db.commit()`, confirming it commits on the *same* `Session`, so the
  already-flushed document row and the new audit row land in one
  Postgres transaction, exactly as previously documented — not merely
  re-asserted, actually re-traced line by line this pass; the
  `client_ip()`/`resolve_client_ip()` split (audit vs. rate-limit
  dimensions) matches the codebase's own existing, deliberate
  convention; five additional path-traversal-style filenames
  (`..\..\secret.pdf`, an absolute Unix path, a Windows-style path, and
  a repeated-dot-slash pattern, beyond the one already covered) all
  reduce to just the extension, the same as the original case, since
  `_normalize_extension()` has no special-casing for path separators at
  all; the streamed size-limit check depends only on bytes actually
  read via `.read()`, never any length hint, so a missing or misleading
  `Content-Length` cannot bypass it (verified with a 1-byte-at-a-time
  fake reader, the worst case for that assumption).
- **Two new boundary-precision tests**
  (`tests/test_document_service.py`): content of exactly
  `max_size_bytes` succeeds (the check is `> max`, not `>= max` — an
  off-by-one here would have wrongly rejected a file of exactly the
  configured maximum); content one byte over is rejected.
- `ruff`/`mypy` clean (94 source files, no new findings). **9 new
  tests, 67 → 76** (46 unit + 30 HTTP-level — the unit count includes
  the parametrized 5-filename case as 5 collected tests). **76/76
  passing.** Complete backend suite: **370/370 passing** (361
  pre-review + 9 new), **3 consecutive runs**, no regression in any
  existing test. Frontend re-confirmed unaffected (48/48 vitest,
  lint/typecheck clean — no frontend file changed). Docker Compose
  services confirmed healthy and reachable (`compose-backend-1` still
  the image rebuilt during the prior checkpoint); this specific fix was
  validated through the automated test suite against real Postgres, not
  through a fresh manual smoke test against the container — stated
  explicitly rather than implied.

## Completed work (Issue #3 — Slice 3.4: text extraction)

**Implemented, tested, committed (`b01cd24`/`8f72916`), pushed, and
open as PR #21** — CI 4/4 green, not yet merged — on branch
`issue-3-slice-3-4-text-extraction` (cut from `main` at `a6762e2`, the
now-merged Slice 3.3). **Two dedicated pre-merge correctness/security
reviews then each found and fixed a real gap**: the extracted-text
budget (committed as `105ec72`), and a synchronous call blocking the
event loop (committed as `eb14287`) — see the two "Independent
correctness/security review" sections immediately after this one for
the full detail. Adds exactly one capability:
`POST /api/v1/workspaces/{workspace_id}/documents/{document_id}/process`
— synchronous text extraction moving a document from
`UPLOADED`/`PROCESSING`/`FAILED` to `PARSED` or `FAILED`. No chunking,
embedding, vector indexing, or background/queued processing.

- **`backend/app/ingestion/extraction.py`** (new — the package existed
  as an empty placeholder since Slice 3.1; this is its first real
  content, matching GitHub Issue #3's own text naming this exact
  location for parsers). Pure: `extract(*, extension, content: bytes) ->
  ExtractedDocument`, no database/storage/HTTP import, so it's fully
  unit-testable in isolation. `ExtractedDocument` (`sections:
  list[ExtractedSection]`, `page_count: int | None`) /
  `ExtractedSection` (`text`, `page: int | None`, `heading: str |
  None`) — structure-aware, not raw-text-only, per Issue #3's own
  explicit requirement. Every failure path raises `ExtractionError`
  with a short, generic, storage-safe message — never a raw pypdf/
  python-docx/`zipfile`/`csv` exception, filesystem path, or storage
  key.
  - **PDF** (new dependency: `pypdf`): one section per page; page count
    capped at 2000 (`_MAX_PDF_PAGES`); each page's `extract_text()` call
    is individually wrapped so one malformed page's parser exception
    doesn't crash the rest of the document — normalized to
    `ExtractionError` naming the specific page, not a raw traceback.
  - **DOCX** (new dependency: `python-docx`): sections split on
    heading-styled paragraphs (style name starting with `"Heading"`,
    matching python-docx's own convention — verified empirically, not
    assumed, via `add_heading()` round-tripping through `Document()`).
    **DOCX is a ZIP container, so a signature match at upload time
    (Slice 3.3) proves nothing about parse-time safety** —
    `_validate_docx_archive_safety()` runs first, reading only
    `zipfile.ZipInfo` central-directory metadata (`file_size`/
    `filename` — no member is decompressed) and rejecting: a member
    name containing `..` or starting with `/` (path traversal — even
    though python-docx only ever reads members in-memory via
    `ZipFile.read()`, never extracts to disk, this is defense in depth
    against relying on that library's internals never changing); a
    single member's declared uncompressed size over 50 MiB; a total
    declared uncompressed size over 200 MiB (the zip-bomb case — the
    check is against *declared* size, not on-disk/compressed size, so a
    highly compressible member can't hide behind a small file); more
    than 2000 members. Only after every check passes does
    `python-docx` actually parse the content, and only via in-memory
    `BytesIO`.
  - **TXT**: decoded with `errors="replace"` — an invalid byte sequence
    substitutes the Unicode replacement character rather than raising.
  - **Markdown**: sections split on top-level headings (`#`/`##`/etc.,
    a line starting with `#` followed by a space); same safe-decode
    approach as TXT; an empty document still returns one well-formed
    (empty-text) section rather than an empty list.
  - **CSV**: kept deliberately simple (one section, the raw decoded rows
    rendered as text) — a richer table-aware structure would edge into
    chunking-strategy territory, out of this slice's scope. Uses the
    stdlib `csv` module; `csv.Error` (e.g. a field exceeding the
    module's own default 128 KiB field-size limit — a real, reachable
    malformed-input case, verified empirically) is normalized to
    `ExtractionError`, never a crash.
  - **Output-size budget** (`_MAX_EXTRACTED_TEXT_BYTES`, 20 MiB): applied
    to every format's extracted text, independent of the
    already-enforced 50 MiB upload-size limit — truncates on a UTF-8
    boundary rather than raising, since a very large but genuinely valid
    document should still produce useful, bounded output.
- **`backend/app/services/document_service.py`** (extended):
  `process_document()` — looks up the document scoped to its workspace
  (`document_repository.get_by_id_for_workspace()`, the same
  IDOR-safe "scope in the query itself" pattern every other
  workspace-scoped lookup in this codebase uses; `404` if absent or
  belonging to a different workspace, mirroring `require_workspace_role`'s
  own non-leaking 404). Rejects `PARSED` and any later lifecycle state
  with `409` (`document_already_processed`); allows `UPLOADED`,
  `PROCESSING` (a prior attempt was interrupted — see crash-safety
  below), and `FAILED` (explicit retry) to proceed.
  - **Crash safety, the central design decision of this slice**: the
    `PROCESSING` transition (`document_repository.mark_processing()`) is
    committed as **its own transaction**, before extraction is even
    attempted — not just held in-memory and committed together with the
    eventual `PARSED`/`FAILED` result. If the process crashes or is
    killed mid-extraction (a large PDF, a slow parse), the document is
    left honestly at `PROCESSING`, which the reprocessable-status set
    above treats as retriable — never falsely appears `PARSED`, never
    silently reverts to looking like it was never attempted. Directly
    verified by a dedicated regression test (see below), not just
    asserted in a docstring.
  - Extraction proper: `storage.read(key=document.storage_key)` (the
    server-generated key, never the filename) → derive the extension
    from the storage key's own suffix (`_extension_from_storage_key()`
    — the key is server-generated as
    `f"{workspace_id}/{document_id}{extension}"`, so this never touches
    the client-supplied filename again) → `extraction.extract()`. A
    `StorageError`, an `ExtractionError`, or any other unexpected
    exception is caught in one `try` block (in that order) and
    recorded as `FAILED` with a short, generic `failure_reason` —
    **never the `StorageError`'s own message**, since that embeds the
    storage key (see `storage_provider.py`); `ExtractionError` messages
    are already storage-safe by construction. The endpoint always
    returns `200` — a parsing failure is an expected, handled outcome
    on the document row, not a request-level error.
- **`backend/app/repositories/document_repository.py`** (extended):
  `get_by_id_for_workspace()`, `mark_processing()`, `mark_parsed()`
  (also clears `failure_reason`, for the retry-then-succeed case),
  `mark_failed()` — all follow the existing add/flush/no-commit
  convention (the service layer controls transaction boundaries, per
  this codebase's established pattern).
- **`backend/app/schemas/document.py`**: additive `failure_reason: str |
  None` on `DocumentRead` (previously missing — identified during this
  slice's design phase as needed so API clients can see why a document
  failed).
- **`backend/app/core/audit.py`**: additive
  `AuditEvent.DOCUMENT_PARSED`/`DOCUMENT_PARSING_FAILED`.
- **`backend/app/core/rate_limit.py`**: additive `process_rate_limiter`
  + `enforce_document_process_rate_limit()` — same shape as
  `document_upload` (IP + authenticated user ID, Tier A, 20/60s, a
  plain function rather than `Depends()`-shaped for the same
  circular-import reason documented on the upload version). Extraction
  is CPU-bound, not just I/O like upload, so a member repeatedly
  triggering re-processing of the same (or a large) document is a
  genuine self-service resource-exhaustion vector on shared
  infrastructure — the same defensive treatment as upload was judged
  warranted, not scope creep, given Phase E's explicit resource-safety
  requirement.
- **`backend/app/api/v1/documents.py`**: new `process_document` route in
  the same router as upload (one file, related resource, per this
  slice's own design decision rather than a second router module).
- **`backend/tests/test_extraction.py`** (new, 27 unit tests, no
  database/HTTP/filesystem — pure `extract()` calls): PDF valid
  (correct page count)/no-extractable-text/malformed/a page-count-limit
  test (via a monkeypatched smaller `_MAX_PDF_PAGES`, avoiding a
  2000-page fixture)/a simulated single-page parser exception (patches
  `pypdf._page.PageObject.extract_text` directly — a real
  malformed-content-stream PDF that fails on exactly one page isn't
  reliably constructible by hand, so the library seam is patched to
  prove this specific defensive path); DOCX valid (heading-split
  sections)/malformed-zip/four archive-traversal member-name
  patterns/member-count/per-member-size/total-size limits (via
  monkeypatched smaller thresholds for deterministic, fast, small
  fixtures) **plus one real highly-compressible 60 MB→~50 KB member
  proving the real, unmodified 50 MiB default threshold rejects a
  genuine zip-bomb-shaped payload, not just a monkeypatched one**/a
  DOCX that passes the archive-safety check but isn't real OOXML content
  (proving python-docx's own parse failure is normalized too, not just
  the pre-flight check); TXT valid UTF-8/invalid-byte-sequence
  (asserts the replacement character appears, never a crash); Markdown
  heading-splitting/no-headings-single-section/empty-document; CSV
  valid/a genuine field-size-limit failure (200 KB single field,
  verified empirically to trigger Python's own real
  `csv.Error`, not simulated); the unsupported-extension dispatch path;
  the output-text budget (monkeypatched smaller for a fast, small-input
  test).
- **`backend/tests/test_document_processing.py`** (new, 24 HTTP-level
  tests, real Postgres/Redis/filesystem via an isolated per-test
  `get_storage_provider` override, no mocks — every document is
  uploaded through the real upload endpoint first, then processed,
  exercising both slices together the way a real client would): every
  format's success path (PARSED, correct `page_count`, exactly one
  `DOCUMENT_PARSED` audit row with `page_count`/`section_count`
  metadata); malformed PDF/DOCX/CSV and a DOCX archive-traversal attempt
  each → FAILED with a `200` (not `500`), a non-empty generic
  `failure_reason` that never contains the document ID, the storage
  key, or the archive member name, and exactly one
  `DOCUMENT_PARSING_FAILED` audit row; a storage-read failure (via a
  `_ReadFailsStorage` wrapper around a real `LocalStorage`, mirroring
  the existing `_BrokenStorage`/`_DeleteFailsStorage` test-double
  pattern from `test_document_upload.py`) → FAILED, the simulated
  error's own message never reaching the response; an unexpected
  (non-`ExtractionError`, non-`StorageError`) exception monkeypatched
  into `extraction.extract` → FAILED, not a `500`, the raw exception
  message never reaching the response; **the crash-safety regression
  test** — monkeypatches `extraction.extract` to itself query the
  document's current status through the *same* database session
  `process_document()` is using, before performing the real extraction,
  and asserts that status is already `PROCESSING` — this would fail if
  the `PROCESSING` transition weren't committed as its own transaction
  before extraction runs; authorization (unauthenticated `401`, VIEWER
  `403`, non-member `404`, a document ID from workspace A rejected
  through workspace B's ID even for a real member of workspace B
  `404`, a nonexistent document ID `404`); lifecycle (reprocessing an
  already-`PARSED` document `409`; reprocessing a `FAILED` document is
  allowed — proven by actually calling it again and getting `200`/
  `FAILED` again, not a `409`); `document_process` rate-limit key
  creation, threshold enforcement (20/60s), and Tier A Redis-unavailable
  fallback — each implemented by reprocessing a single `FAILED`
  document repeatedly (retriable, per the lifecycle rule above) rather
  than uploading 25 distinct documents, since uploading that many would
  have also tripped the separate, identically-sized `document_upload`
  rate limit and made the test assert the wrong thing.
- `ruff`/`mypy` clean (97 source files, no new findings). **51 new
  tests** (27 + 24), **51/51 passing**. Complete backend suite:
  **421/421 passing** (370 pre-Slice-3.4 + 51 new), **3 consecutive
  runs**, no regression in any existing test. Frontend re-confirmed
  unaffected (`eslint`/`tsc --noEmit` both clean — no frontend file
  changed; vitest not re-run since nothing in its scope changed).
  **Full manual smoke test against the real Docker Compose stack**: the
  backend image was rebuilt (`docker compose build backend`) to pick up
  the new `pypdf`/`python-docx` dependencies, the container came up
  healthy, and a real end-to-end `curl` sequence (register → create
  workspace → upload a genuine 2-page PDF generated via `pypdf.PdfWriter`
  → process) returned `PARSED` with `page_count: 2` and
  `failure_reason: null` — confirming the rebuilt image, the real
  Postgres/Redis/filesystem, and the full route wiring all work together,
  not just the test suite in isolation.
- **Documentation updated this slice**: `docs/API_CONTRACT.md` (the
  `/process` endpoint's full contract — method, role, request/response
  shape, retry/lifecycle semantics, security summary, rate limiting,
  audit); `docs/SECURITY.md` ("Upload & document safety" extended with
  the extraction-time threat model exactly as implemented — the DOCX
  archive-safety limits, PDF/output-size caps, safe decoding, the known
  no-CPU-timeout limitation stated explicitly rather than hidden;
  "Audit logging" and "Security testing" updated from their previous
  "not yet"/"no code parses file content yet" state to reflect what's
  now actually tested); `PROJECT_STATE.md`, this file, `CHANGELOG.md`.

## Independent correctness/security review (Issue #3 — Slice 3.4, pre-merge)

**Committed as `105ec72` on branch `issue-3-slice-3-4-text-extraction`,
same PR #21.** A dedicated, line-by-line review of the Slice 3.4 diff
(not just a re-run of the existing 51 tests) — extraction.py,
document_service.py, document_repository.py, the schema/audit/
rate-limit additions, and both test files — against the specific
threat model Issue #3's own security section names (untrusted PDF/DOCX/
TXT/Markdown/CSV, DOCX-as-ZIP-container zip-bomb risk, resource/time
limits, workspace isolation).

**Finding (real, fixed): the extracted-text budget was enforced
per-section, not per-document.** `_enforce_text_budget()` was called
independently on each `ExtractedSection.text` with no running total
across sections. For a single-section format (TXT) this is harmless,
but PDF (up to 2000 sections, one per page) and DOCX (one section per
heading) can produce many sections — a document with many sections
each individually under the per-section cap could still sum to far
more than the documented `_MAX_EXTRACTED_TEXT_BYTES` (20 MiB) total.
This is not merely theoretical for PDF specifically: pypdf decompresses
each page's content stream internally when `extract_text()` is called,
so a page's share of the already-capped 50 MiB *compressed* upload says
nothing about that page's *decompressed* text output — a small,
highly-compressible content stream (repeated text-drawing operators)
can expand substantially on decompression, the same class of risk the
DOCX archive-safety check was already built to defend against, just
via a different mechanism pypdf doesn't expose a pre-flight hook for.
Markdown has the identical multi-section structure (heading-split), but
since Markdown decoding is ~1:1 with input bytes (no decompression),
its worst case is bounded by the 50 MiB upload cap — a real but
lower-severity instance of the same documentation-accuracy gap (the
"20 MiB regardless of format" claim in `docs/SECURITY.md` wasn't
literally true for Markdown either, just less exploitable).

**Verified before fixing, not assumed**: `git stash`ed the fix, re-ran
the new regression tests against the pre-fix code, and confirmed the
PDF/DOCX/Markdown tests genuinely fail (40 bytes produced against a
10-byte budget in each case) while the CSV test passes even without the
fix — confirming CSV's *final* output was already correctly bounded by
the old single-call `_enforce_text_budget(rendered)` (the string was
just built in one large intermediate allocation before being truncated,
a separate, lower-severity transient-memory concern addressed in the
same fix for consistency, not because the final result was wrong).

**Fix**: `_extract_pdf`, `_extract_docx`, and `_extract_markdown` now
track a running byte total across sections via a new
`_truncate_to_budget(text, *, max_bytes)` helper (returns both the
truncated text and its actual encoded length, so a caller can
accumulate precisely); once the running total reaches the budget,
further pages/sections are skipped entirely — for PDF this also stops
paying the decompression/`extract_text()` cost for pages whose output
would only be discarded. `_extract_csv` was rewritten to render
row-by-row with exact separator-byte accounting (each `"\n"` join
counted), rather than joining every row into one large string first —
this also closes a secondary, narrower issue: without separator
accounting, a CSV with a very large number of tiny rows could let the
newline separators alone push the final size past the budget even
though every individual row was itself within it.

**A related question was investigated and found NOT to be a bug**:
whether the DOCX archive-safety check (which reads only the declared
`ZipInfo.file_size` from ZIP central-directory metadata, never
decompressing anything itself) could be bypassed by a crafted ZIP that
*lies* about a member's declared uncompressed size — e.g., declaring a
tiny size while the member's real compressed data actually decompresses
to something huge, letting `python-docx` pay the full decompression
cost once it later calls `.read()` on that member. This was tested
directly, not assumed: a ZIP was hand-built (via `zlib.compressobj` and
raw local-file-header/central-directory `struct.pack` construction,
bypassing `zipfile.ZipFile.write()`'s own automatic, honest size
bookkeeping) with a 5 MiB real payload but a declared `file_size` of
100 bytes. Reading it back confirmed Python's `zipfile.ZipExtFile`
internally caps *decompressor output* at the declared size (via its own
`_left` accounting), independent of how much more the underlying
compressed stream could actually produce — attempting to read past that
point raises `BadZipFile` (a CRC mismatch against the truncated output)
rather than silently returning more data. A lied-about size cannot be
used to extract more real content than declared; it can only make the
member unreadable. No code change was needed for this path — it was a
real question worth answering empirically rather than leaving as an
unverified assumption, and the answer was "already sound."

**Other review areas confirmed correct, not just assumed**:

- **Crash safety**: re-confirmed by reading (not just trusting the
  existing test) that `mark_processing()` + `db.commit()` happens
  before the `try` block that reads storage and calls `extraction.extract()`
  — a crash mid-extraction genuinely leaves the document at
  `PROCESSING`, which `_REPROCESSABLE_STATUSES` treats as retriable.
- **Information leakage**: `StorageError`'s own message is never used
  as `failure_reason` (it embeds the storage key) — a fixed generic
  string is used instead; `ExtractionError` messages are all hardcoded
  literals or contain only safe, bounded values (a page index, a
  fixed extension name) — never a filename, path, or raw library
  exception text; the fully-unexpected-exception branch logs the real
  exception server-side (`logger.exception`) and returns a fixed
  generic reason, never `str(exc)`.
- **Workspace isolation**: `get_by_id_for_workspace()` scopes the
  lookup in the query itself (`Document.id == document_id,
  Document.workspace_id == workspace_id`), not as a post-hoc check —
  the same IDOR-safe shape as every other workspace-scoped lookup in
  this codebase; already covered by
  `test_cross_workspace_document_id_rejected_with_404` (a document ID
  from workspace A is unreachable through workspace B's ID, even for a
  real member of workspace B).
- **Rate limiting**: `enforce_document_process_rate_limit()` mirrors
  `enforce_document_upload_rate_limit()` exactly (IP + user-ID
  dimensions via the trusted-proxy-aware `resolve_client_ip()`, Tier A,
  `fail_open_on_redis_error=False`) — no leaked sensitive data in the
  rate-limit keys (a UUID and a resolved IP, the same shape every other
  dimension in this codebase already uses).
- **Byte-vs-character confusion**: `_truncate_to_budget()` measures via
  `.encode("utf-8")`, never `len(text)` — confirmed the budget is
  genuinely bytes, matching its own "20 MiB" documentation, and that a
  truncation on a split multibyte UTF-8 boundary is handled
  (`errors="ignore"` on the re-decode) rather than raising or silently
  keeping one extra malformed byte.
- **DOCX traversal check**: re-verified `info.filename.replace("\\",
  "/").split("/")` correctly catches `..` in any position (leading,
  middle, or via a Windows-style backslash), and that even though the
  check is currently unreachable in practice (`python-docx`/`zipfile`
  only ever read members in-memory via `.read()`, never extract to a
  filesystem path), it remains correct, low-cost defense in depth
  against that assumption changing in a future library version — as
  the code's own comment already stated, now independently confirmed
  rather than taken on faith.

**Reviewed and accepted as a known, low-severity limitation, not
fixed**: two (or more) concurrent `/process` calls against the same
document are not prevented by any row-level lock. Traced the actual
behavior: PostgreSQL's own row-level locking serializes the competing
`UPDATE`s from `mark_processing()`, so there is no data corruption or
torn state — but each request still independently performs its own
extraction attempt (duplicate CPU cost) and its own `record_audit_event()`
call (duplicate `DOCUMENT_PARSED`/`DOCUMENT_PARSING_FAILED` audit rows
for one logical operation). Since the underlying content is
deterministic, both requests converge on the same final `PARSED`/
`FAILED` outcome — the imperfection is wasted work and audit-log
duplication, not incorrect data. No pessimistic locking exists anywhere
else in this codebase (the established pattern is "accept the race,
use a database constraint as backstop where correctness genuinely
depends on it" — e.g. upload's duplicate-checksum handling), and adding
one here would be a new architectural pattern not justified by this
slice's actual risk. Bounded in practice by the `document_process` rate
limit (20/60s per user+IP) regardless.

**Verification**: `ruff`/`mypy` clean (97 source files, no new
findings). 4 new regression tests, each independently confirmed (via
`git stash`) to fail against the pre-fix code and pass against the fix.
Complete backend suite: **425/425 passing** (421 pre-review + 4 new),
**3 consecutive runs**. Frontend not re-run (no frontend file touched
by this fix).

## Second independent correctness/security review (Issue #3 — Slice 3.4, final pre-merge)

**Committed as `eb14287` on branch `issue-3-slice-3-4-text-extraction`,
same PR #21.** A further, separate review focused specifically on
resource-exhaustion resistance, concurrency, and the async/threading
model of the request-handling layer itself — areas the first review
(above) didn't cover, since it focused on the extraction module's own
per-format logic.

**Finding (real, significant, fixed): `process_document()` called
synchronous, CPU-bound work directly inside its `async def` body,
blocking the single event loop for every concurrent request.**
`storage.read()` and `extraction.extract()` were called directly, not
via any thread/executor offload. This project runs exactly one
`uvicorn` process with no `--workers` (confirmed by reading
`infra/docker/backend.Dockerfile`'s entrypoint script directly, not
assumed from the earlier `rate_limit.py` docstring alone). Since
Python's asyncio event loop is single-threaded, a genuinely blocking
call anywhere in an awaited coroutine chain — not just an infinite
loop, but any call that doesn't hand control back to the scheduler —
prevents *every other* coroutine (every other in-flight request: other
users' logins, unrelated workspaces' health checks and uploads) from
making progress until that call returns. `async def` route handlers
are not automatically thread-offloaded by FastAPI/Starlette the way
plain `def` handlers are; only the code declared `async def` needs to
avoid blocking calls, and this endpoint's whole chain (`documents.py`'s
route → `process_document()` → `extraction.extract()`) was `async def`
all the way down to a plain synchronous call at the bottom.

**Verified empirically, not assumed**: wrote a real concurrency test
using `httpx.AsyncClient` with `ASGITransport(app=app)` — sharing the
actual event loop the application runs on, not `TestClient`'s
synchronous-per-call wrapper, which cannot observe this class of bug at
all. Two coroutines were run via `asyncio.gather()`: one triggering
`/process` with a monkeypatched `extraction.extract` that does
`time.sleep(2.0)` (simulating real CPU-bound parser work), the other
issuing `/api/v1/health` after a 0.2–0.3s delay. Timings were measured
from one shared `t=0` reference (an earlier draft of this same
diagnostic measured elapsed time *relative to each coroutine's own
start*, which — caught during this review, not shipped — silently hides
this exact bug: if the health check never even gets scheduled to start
until the slow request finishes, its own *internal* duration still
looks fast). With the absolute-clock version: pre-fix, the health check
(scheduled at t≈0.3s) didn't actually complete until t≈2.0s — proving
it was blocked, not just slow. Post-fix, it completed at t≈0.31s,
regardless of the still-in-flight 2-second extraction.

**Fix**: `_read_and_extract()` (new, in `document_service.py`) wraps
`storage.read()` + `extraction.extract()` as one plain synchronous
function; `process_document()` now calls it via `await
asyncio.to_thread(...)` instead of calling it directly. No new
dependency, no new infrastructure, no architecture change — `to_thread`
is a Python 3.9+ stdlib facility built exactly for this situation
(occasional blocking calls inside async code), not a background-job
system.

**A second, related correctness hazard this introduced was caught and
fixed in the same pass, before it could ship**: the existing
crash-safety regression test
(`test_processing_transition_is_committed_before_extraction_is_attempted`)
monkeypatched `extraction.extract` with a spy that queried
`document_repository.get_by_id_for_workspace(db_session, ...)` — safe
when everything ran on one thread, but once extraction moved to a
`to_thread()` worker thread, that spy would now execute on a *different*
thread than the one that owns `db_session`. SQLAlchemy `Session`
objects are documented as not safe for reuse across threads (even
non-concurrently) — this would have been a latent, non-deterministic
test hazard shipped alongside the real fix if not caught. Rewritten to
avoid any cross-thread session access: it now monkeypatches
`db_session.commit` itself to record "a commit happened" and
`extraction.extract` to record "extraction started", both via plain
`list.append()` calls (safe across threads under CPython's GIL — the
GIL serializes the append operation itself even though it runs on
different OS threads), and asserts the recorded order. Verified this
rewritten test still means what it claims: temporarily removed the
`db.commit()` call preceding extraction (via `Edit`, confirmed restored
correctly afterward — not `git checkout`, which was tried once during
this review and mistakenly reverted the then-uncommitted
`asyncio.to_thread` fix itself, caught immediately by re-grepping for
it and redone via `Edit`) and confirmed the test fails as expected; a
new, permanent regression test
(`test_slow_extraction_does_not_block_unrelated_concurrent_requests`)
encodes the concurrency proof above and was itself confirmed to fail
against the pre-fix code before being confirmed to pass against the fix.

**Item E (concurrent `/process` calls on the same document) — reviewed
again with the production session model explicitly confirmed, not just
assumed**: read `app/core/db.py`'s `get_db()` directly — it creates a
fresh `SessionLocal()` per request via FastAPI's dependency injection
(the test suite's *shared* `db_session` fixture is a test-only
isolation artifact, not representative of production). This confirms
the earlier conclusion: two concurrent `/process` calls on the same
document each get their own database session/connection in production;
PostgreSQL's own row-level locking serializes the competing
`mark_processing()` `UPDATE`s (the second blocks until the first
commits, then proceeds against the now-current row — no error, no
corruption); the extraction step's own content is deterministic, so
both converge on the same final `PARSED`/`FAILED` outcome regardless of
ordering. The `asyncio.to_thread()` fix in this same review changes
*how* the wasted duplicate extraction work happens — it can now run in
genuine OS-thread parallelism instead of being serialized behind the
(now-freed) event loop — but does not change whether it's safe: the
imperfection remains bounded to duplicate CPU cost and duplicate
`DOCUMENT_PARSED`/`DOCUMENT_PARSING_FAILED` audit rows for one logical
operation, not data corruption, and remains bounded in practice by the
existing `document_process` rate limit (20/60s per user+IP). No lock
was added — consistent with this codebase's established
no-pessimistic-locking convention, and not justified by this slice's
actual risk.

**Item A (whether a CPU/wall-clock timeout should be added now) —
considered and deliberately deferred, not silently skipped**: the
severe failure mode (one document freezing the entire server for every
other request) is exactly what the threading fix above closes. What
remains is narrower: a single pathological document could still tie up
one worker thread for a long time, bounded in practice by the existing
page-count (2000) and output-size (20 MiB) caps on the *amount of work
performed*, and by the `document_process` rate limit on how many such
requests one actor can trigger per minute. A true wall-clock
interruption of arbitrary synchronous Python code cannot be done
safely by killing a thread (Python provides no safe API for this); the
correct mechanism would be process-based isolation (a
`ProcessPoolExecutor`) or an external supervisor/timeout at the
infrastructure layer — either a materially larger architectural change
than this slice's own scope, explicitly out of bounds per this review's
own instructions ("do not redesign the architecture").

**Verification**: `ruff`/`mypy` clean (97 source files, no new
findings). 1 new regression test, confirmed (via a temporary,
`Edit`-based revert, not `git checkout`) to fail against the pre-fix
code and pass against the fix; the rewritten crash-safety test also
re-verified the same way. Complete backend suite: **426/426 passing**
(425 pre-final-review + 1 new), **3 consecutive runs**. Frontend not
re-run (no frontend file touched by this fix).

**Both fixes above were later confirmed included when PR #21 merged
into `main` as squash commit `2961b62`.**

## Completed work (Issue #3 — Slice 3.5: structure-aware chunking)

**Implemented, tested; not yet committed, pushed, or opened as a PR**,
on branch `issue-3-slice-3-5-structure-aware-chunking` (cut from `main`
at `2961b62`, the now-merged Slice 3.4). Adds exactly one new module,
`backend/app/ingestion/chunking.py`: a `ChunkingConfig`, a `Chunk`
output dataclass, a `ChunkingStrategy` protocol, and one concrete
implementation, `StructureAwareChunker`. Pure `ExtractedDocument ->
list[Chunk]` transformation — no database, HTTP, filesystem, or
lifecycle dependency; nothing is persisted, no document status
transition happens. Wiring `Chunk`s into `document_chunks` rows and the
`PARSED -> CLEANED -> CHUNKED` lifecycle transition is explicitly
**not** this slice's job (Slice 3.6).

- **Design starting point**: before writing any code, read
  `app/ingestion/extraction.py`'s actual output types
  (`ExtractedDocument`/`ExtractedSection` — `sections: list[...]`,
  `page_count`; each section has `text`/`page`/`heading`) and
  `app/models/document_chunk.py`'s actual schema (`chunk_index: int`,
  `page: int | None`, `section: str | None`, `content: str`, one value
  each per row, no array/range type) directly, rather than trusting
  older planning documents (`docs/RAG_DESIGN.md`/`docs/REQUIREMENTS.md`)
  to still match the current implementation exactly. They did, for the
  concepts that matter (chunk metadata fields, the three named
  strategies), but the schema's single-value-per-row shape is the
  detail that actually drove the module's central design decision
  below — confirmed by reading the model file, not assumed from the
  docs' higher-level description.
- **The central design decision, forced by that schema shape**: a
  `Chunk` never spans more than one `ExtractedSection`. Each
  `ExtractedSection` already carries exactly one `page`/`heading` pair
  (one page for PDF, one heading for DOCX/Markdown, `None`/`None` for
  TXT/CSV's single section); every `Chunk` inherits that section's
  values unchanged. Merging content across two different sections to
  reach `target_chunk_size` for a short section would require inventing
  a `page`/`section` value that doesn't honestly describe the chunk's
  content (e.g. claiming "page 3" for text that's actually pages 3 and
  4) — the exact kind of misleading representation the task's own
  instructions warned against inventing. A short section instead simply
  produces its own short chunk. Overlap follows the same rule: it never
  carries text across a section boundary, only between consecutive
  chunks within the same section. This is the module's own docstring's
  first, load-bearing paragraph — read that before changing anything
  about cross-section behavior in a later slice.
- **`Chunk`** is a new, small, frozen dataclass — deliberately not the
  `DocumentChunk` SQLAlchemy model, so this module stays free of a
  SQLAlchemy dependency (a pure transformation shouldn't need to import
  the ORM to be unit-tested). Field names match `document_chunks`'
  columns 1:1 (minus `document_id`/`workspace_id`/`id`, which only exist
  once a document/workspace context is applied by whatever later slice
  persists these), so mapping to that model when it happens is a
  trivial 1:1 copy — not a redesign.
- **`ChunkingConfig`**: `target_chunk_size`/`chunk_overlap`/
  `min_chunk_size`/`max_chunk_size`, all **character counts** (`len(text)`),
  explicitly not tokens — no tokenizer is used or implied anywhere in
  this module (see "Dependency discipline" below for why one wasn't
  added). Validated eagerly in `__post_init__` via `ValueError` (matching
  `app/core/config.py`'s own existing `ValueError`-on-bad-value
  convention, not a new pattern): every size must be positive; `max_chunk_size`
  is capped at an absolute ceiling (100,000 characters — a sane bound, a
  "chunk" larger than this defeats the purpose of chunking, not a tuned
  value); `min_chunk_size <= target_chunk_size <= max_chunk_size`;
  `chunk_overlap < min_chunk_size` (also transitively rules out
  `chunk_overlap >= max_chunk_size`, and structurally guarantees every
  new chunk after the first contains at least some genuinely new
  content, not just carried-over overlap).
- **`StructureAwareChunker`**: chunks each section independently.
  Boundary preference, exactly as specified: section (never crossed) ->
  paragraph (a blank line; when none exists, falls back to a single
  newline, since most of this project's own extractors join lines with
  `\n` not `\n\n` — confirmed by reading `extraction.py` directly, not
  assumed) -> sentence (a `.`/`!`/`?` followed by whitespace — a
  punctuation heuristic, explicitly documented as not real sentence
  segmentation) -> word (whitespace) -> a hard character cut, reached
  only for a single "word" with no internal whitespace that alone still
  exceeds `max_chunk_size` (a long URL or base64 blob). Splitting
  (`_split_into_pieces`/`_split_oversized`) guarantees every piece is
  `<= max_chunk_size` before packing ever starts; packing
  (`_pack`/`_close_buffer`) greedily accumulates pieces toward
  `target_chunk_size`, closes a chunk once reached, carries
  `chunk_overlap` characters of the closed chunk's tail into the next
  chunk, and merges an undersized trailing remainder into the previous
  chunk when doing so keeps it within `max_chunk_size` (so
  `min_chunk_size` is a target, not an absolute guarantee — the one
  documented exception is an unavoidable, unmergeable small remainder;
  `max_chunk_size` **is** an absolute guarantee, verified never violated
  in tests).
- **Deterministic by construction**: no randomness, no wall-clock/ID
  generation, no reliance on set iteration order (only stable `list`/
  `dict` ordering); verified directly, not just assumed, by a test
  calling `chunk()` twice on the same input/config (and again via a
  fresh chunker instance) and asserting byte-identical results.
- **`backend/tests/test_chunking.py`** (new, 45 unit tests, no
  database/HTTP/filesystem — pure, fast): basic paragraph chunking;
  deterministic repeated execution across calls and instances; gapless
  zero-based chunk indexes; section/page metadata preserved from the
  source section and never mixed across two different sections (the
  central design decision's own regression test); multiple
  pages/multiple headed sections each keeping their own metadata;
  sentence-boundary splitting and hard-character-fallback splitting for
  a 500-character single "word"; a ~100,000-character pathological
  paragraph never producing a chunk over `max_chunk_size`; overlap-tail-
  appears-in-the-next-chunk and zero-overlap-produces-no-shared-text
  behavior, and overlap never producing an over-`max_chunk_size` chunk;
  a short section standing alone as its own chunk; a small trailing
  remainder merging into the previous chunk when it fits; every
  `ChunkingConfig` validation rule (7 non-positive-size parametrized
  cases, `chunk_overlap` >= `min_chunk_size` twice, `min_chunk_size` >
  `target_chunk_size`, `target_chunk_size` > `max_chunk_size`, an
  absurdly large `max_chunk_size`, and the default config's own
  validity); empty/whitespace sections and an empty document producing
  no chunks, and no chunk ever being empty/whitespace-only across a
  mixed batch; a pathological-`min_chunk_size` document proven bounded
  (no infinite loop, chunk count either within the ceiling or a raised
  `ChunkingError`); a monkeypatched-ceiling test proving `ChunkingError`
  is raised, not a crash; a 50-section, ~250,000-character document
  chunking in well under 5 seconds (no hidden quadratic behavior); the
  `Chunk` dataclass's frozen immutability and the
  `StructureAwareChunker`/`ChunkingStrategy` protocol shape; and two
  tests feeding this module **real** `extraction.extract()` output
  (Markdown with two headings, and a real 2-page blank PDF) rather than
  only hand-built fixtures, to prove the two modules' contracts actually
  compose, not just that this test file's own assumptions about
  `ExtractedDocument`'s shape happen to be self-consistent.
- **A dedicated post-implementation quality review (not just re-running
  the tests) found and fixed two genuine gaps**, both discovered by
  reasoning through edge cases the initial test suite hadn't yet
  covered, then verified empirically:
  1. **Orphaned overlap fragment.** When a chunk closed for reaching
     `target_chunk_size` exactly at (or very near) `max_chunk_size` — the
     common shape for a run of hard-split pieces from one oversized
     "word" — the small overlap tail carried into the next iteration
     sometimes couldn't combine with the next (large) piece, and was
     being emitted as its own standalone tiny chunk: below
     `min_chunk_size`, and containing nothing that wasn't already the
     previous chunk's own tail (a near-duplicate fragment, not new
     information). Reproduced directly (a 500-character single "word",
     `max_chunk_size=50`, `chunk_overlap=5`, `min_chunk_size=10`
     produced a genuine 5-character orphan chunk at index 1). Fixed by
     tracking whether the current buffer is "pure carried-over overlap
     with no new piece content yet"; when the next piece still doesn't
     fit alongside it, that pure-overlap buffer is now discarded rather
     than emitted, since it adds no new information over the previous
     chunk's own tail. Verified via `git stash` (this fix was applied
     before any commit existed, so an unstash/restash round-trip proved
     the before/after difference directly) that the regression test
     (`test_overlap_does_not_produce_an_orphaned_tiny_fragment_chunk`)
     fails without the fix and passes with it.
  2. **The chunk-count resource-safety ceiling (`_MAX_CHUNKS_PER_DOCUMENT`,
     50,000) was checked only once per section**, in `chunk()`'s own
     loop, after each `_chunk_section()` call fully returned. TXT and
     CSV always produce **exactly one** section for the whole document —
     the single most common shape for a large plain-text upload — so a
     pathological configuration (a very small `min_chunk_size`) applied
     to one large section could build far more than the stated ceiling
     internally before the check ever ran. Reproduced directly: a
     5,000,000-character single-section document with
     `min_chunk_size=1` produced roughly 500,000+ intermediate chunks
     (ten times the ceiling) before the old between-sections check would
     have fired, confirmed by timing (took ~1.0s to raise) versus the
     fix (~0.24s). Fixed by threading a running `index_offset` (the
     count of chunks already produced by earlier sections) into `_pack()`
     and checking the ceiling after every single chunk this section
     closes, not just once at the end. Verified with a temporary,
     `Edit`-based revert (setting the check to `if False and ...`, never
     `git checkout` on uncommitted work) that both the pre-existing
     cross-section ceiling test and a new, timing-asserting
     single-large-section regression test
     (`test_chunk_count_ceiling_is_enforced_within_a_single_large_section`)
     fail without the fix and pass with it, then restored the fix the
     same way and re-confirmed both pass.
- **Other review areas confirmed correct, not just assumed**: no hidden
  quadratic behavior in `_pack_words`/`_pack` (buffer concatenation is
  bounded by `max_chunk_size`, a constant, not by total document size —
  confirmed by the 50-section timing test completing in well under 5
  seconds); no accidental lifecycle/database/HTTP coupling (the module's
  only import beyond the stdlib is `app.ingestion.extraction`, confirmed
  by reading the file's own import block); no unnecessary dependency
  added (stdlib `re`/`dataclasses`/`typing` only — see "Dependency
  discipline" below); `_split_oversized`'s recursion always terminates
  (each fallback level either finds a real split or falls through to
  hard-character splitting, which always makes guaranteed progress —
  confirmed both by direct code reading and by the pathological-input
  tests actually completing rather than hanging).
- **Dependency discipline**: no third-party tokenizer or chunking
  framework was added. A real tokenizer (e.g. `tiktoken`) was
  considered and explicitly rejected for this slice: this module's own
  `ChunkingConfig` is documented as character-based, not token-based,
  matching what `docs/RAG_DESIGN.md`/`docs/REQUIREMENTS.md` actually
  require at this stage (configurable chunk size/overlap/min/max — none
  of those documents mandate token-aware sizing); adding a tokenizer
  dependency now would tie chunk sizing to a specific
  model/tokenizer choice before the `EmbeddingProvider` abstraction
  (Slice 3.7) even exists to consume it, the same "don't lock in a
  choice before the thing that needs it is designed" reasoning
  `docs/DATA_MODEL.md` already applied to deferring the embedding
  column itself.
- `ruff`/`mypy` clean (99 source files, no new findings). **45 new
  tests, 45/45 passing.** Complete backend suite: **471/471 passing**
  (426 pre-Slice-3.5 + 45 new), **3 consecutive runs**, no regression in
  any existing test. Frontend confirmed unaffected (`eslint`/
  `tsc --noEmit` both clean — no frontend file changed; vitest not
  re-run since nothing in its scope changed). No dependency added, so
  no Docker image rebuild was performed for this slice (Slice 3.4's own
  rebuild+smoke-test remains the most recent Docker verification,
  unaffected by this slice's changes) — stated explicitly rather than
  implying a verification that wasn't done.
- **Documentation updated this slice**: `PROJECT_STATE.md` (component
  status, testing row, immediate priorities), this file, `CHANGELOG.md`.
  No ADR was added — nothing here is a genuinely architectural decision
  beyond what the module's own docstring already documents (the
  schema-compatibility constraint is a direct, load-bearing consequence
  of the already-existing `document_chunks` schema, not a new decision
  being made).

## Final independent review (Issue #3 — Slice 3.5, same PR #22)

Stress-tested the already-merged-into-this-branch implementation
against every area the review brief named, beyond what the original 45
tests covered. **No new correctness or security bug was found**; two
genuine test/documentation gaps were found and closed.

- **Unicode/multi-script correctness, verified directly, not assumed**:
  chunked real Tamil (`தமிழ்`), Kannada (`ಕನ್ನಡ`), Hindi (`हिन्दी`), emoji
  (including multi-codepoint ZWJ sequences like `👨‍👩‍👧‍👦`), CJK text
  (space-free, so it exercises the hard-character-fallback path via
  `_split_oversized`'s word-split branch failing to find any spaces),
  and combining-character sequences (`e` + U+0301) — `max_chunk_size`
  held in every case. Confirmed via direct inspection that the module
  never calls `.encode()`/`.decode()`/`bytes()` anywhere (`grep` came up
  empty), so `len(text)` and all slicing are Python's native
  codepoint-based `str` operations throughout — sizing is genuinely
  character-based, never accidentally byte-based. A zero-overlap CJK
  reconstruction test confirmed no content loss or corruption (only the
  inserted `"\n\n"` piece-join separators account for any length
  difference from the original).
- **Overlap attacked specifically**: overlap=1, overlap=`min_chunk_size`-1,
  overlap after hard-character splitting (a 1000-character single
  "word"), a short trailing remainder, and — most importantly — overlap
  across two different sections. Confirmed directly: a chunk from
  section 2 never starts with section 1's overlap tail, and no chunk
  from one page/section ever contains a substring unique to a different
  page/section's content. No orphan chunks, no `max_chunk_size`
  violations, no index gaps, in any of these configurations.
- **`min_chunk_size` exception verified genuinely unavoidable, not just
  accepted because documented**: reproduced directly — ten 9-character
  words packed at `target_chunk_size=18`/`max_chunk_size=20` fill each
  chunk to 19 characters, leaving no room (19+2+1=22 > 20) for an
  11th, 1-character word to merge back. Considered whether a smarter
  global-redistribution algorithm (rebalancing across multiple already-
  closed chunks, not just the immediately-previous one) could close
  this exactly, and judged it not worth the added complexity: it would
  require re-splitting an earlier chunk's content at a non-boundary
  point (undermining the paragraph/sentence/word boundary preference
  for that shaved-off portion) for a purely cosmetic improvement (one
  undersized chunk at a section's end) that never violates the one hard
  guarantee (`max_chunk_size`) or causes data loss — not a correctness/
  security issue, and a materially larger change than this finding
  warrants. **No regression test previously locked this behavior
  in — added one** (`test_unmergeable_trailing_remainder_is_emitted_below_min_chunk_size`).
- **Resource safety re-verified with algorithmic reasoning, not just a
  timing test**: confirmed `_split_into_pieces()`'s cost is inherently
  single-pass/O(n) per section (each regex split and recursive
  `_split_oversized()` call partitions its input with no overlapping
  re-scans — verified by direct code reading, and by measuring
  wall-clock time at 5M/20M/50M-character inputs, which scaled
  proportionally: ~0.39s/~1.7s/~4.3s, confirming linear, not
  quadratic). Found a real gap in what the *ceiling* actually bounds,
  though not a correctness bug: `_MAX_CHUNKS_PER_DOCUMENT`'s incremental
  check (added by the prior review) bounds accumulated *packing*
  output correctly, but the upfront *splitting* phase for one section
  still always completes in full before packing (and this ceiling)
  ever runs — at extraction's own real worst case (a single ~20 MiB
  section built from many short space-separated tokens, the
  pathological shape for the word-split fallback), splitting alone
  measured ~1.7s and ~250 MiB peak. Judged this an accepted, bounded,
  input-proportional cost — not a fix-worthy defect — since it's
  strictly linear (not quadratic/unbounded) and already bounded by
  extraction's own pre-existing 20 MiB cap, matching this codebase's
  established "each layer bounds what it controls" pattern; Review Area
  11's own stated expectation is exactly "approximately linear... if
  performance is already sound, leave it alone." The
  `_MAX_CHUNKS_PER_DOCUMENT` constant's comment was corrected to state
  this precisely (what it bounds, what it doesn't, and why the
  unbounded part is still acceptable) rather than leave the earlier,
  slightly-overclaiming comment as the only record. **No existing test
  exercised a genuinely large *single* section's performance — the
  existing timing test used 50 *small* sections — added one**
  (`test_single_large_section_chunks_in_bounded_linear_time`, ~1.1M
  characters, one section, asserting completion well under 5s and every
  invariant intact).
- **Other areas confirmed sound, no bug found**: punctuation-heavy text
  (ellipses, stacked `?!`), repeated whitespace, CRLF (`\r\n`) and
  many-consecutive-blank-line newline variations, and a mixed
  paragraph+sentence input — all produced correct, bounded,
  non-empty, gapless-indexed chunks. One initially-suspicious result (a
  chunk's content spanning what was originally two separate paragraphs,
  via the overlap+packing mechanism) was traced and confirmed to be
  correct, intended behavior: the documented "boundary preference"
  governs where *oversized* content gets *split*, not a promise that
  packing never *combines* two already-small pieces from different
  paragraphs — that combination is the whole point of `target_chunk_size`
  packing, and forbidding it would defeat `min_chunk_size` entirely.
  Security sweep (`grep` for `eval`/`exec`/`subprocess`/`os.system`/
  `open(`/`__import__`/`pickle`/`marshal`) found none; the module's only
  imports remain stdlib `re`/`dataclasses`/`typing` plus its own sibling
  `app.ingestion.extraction` — confirmed by reading the import block
  directly, not assumed.
- **Verification**: `ruff`/`mypy` clean (99 source files, no new
  findings). 2 new regression tests. Complete backend suite:
  **473/473 passing** (471 pre-review + 2 new), **3 consecutive runs**.
  Frontend confirmed unaffected (`eslint`/`tsc --noEmit` both clean).

## Completed work (Issue #3 — Slice 3.6: processing lifecycle)

**Uncommitted, working-tree-only, on branch
`issue-3-slice-3-6-ingestion-lifecycle` (cut from `237be97`).** Extends
the existing `process_document()` service function and its endpoint —
no new endpoint, no new migration. Reuses the existing `document_process`
Redis rate-limit dimension, the existing MEMBER-role authorization check,
and the existing workspace-scoped 404/409 patterns unchanged.

- **`backend/app/ingestion/cleaning.py`** (new): a pure
  `ExtractedDocument -> ExtractedDocument` transformation
  (`clean(document)`), matching `extraction.py`/`chunking.py`'s own
  shape — no database/HTTP/lifecycle dependency, independently unit
  tested. Deterministic, conservative, loss-minimizing normalization
  only: CRLF/CR → LF, per-line trailing-whitespace strip, leading/
  trailing section whitespace strip, collapsing 3-or-more consecutive
  blank lines down to exactly one (never to zero — a single blank line
  is preserved, since `chunking.py`'s own paragraph-boundary detection
  depends on it). Never rewrites, summarizes, or removes semantic
  content, punctuation, or Unicode; within-line whitespace is untouched.
  Deliberately has no `CleaningError` — the function is total (never
  raises for any valid `ExtractedDocument`), matching this module's own
  narrow, always-safe scope; the service layer's existing generic
  exception handling is the safety net for a truly unexpected failure.
  No third-party dependency — pure stdlib `re`.
- **`backend/app/repositories/document_chunk_repository.py`** (new):
  `bulk_create()` (add/flush/no-commit, same convention as every other
  repository — the calling service controls the transaction boundary)
  and `get_by_document()`. `chunk_index` values are taken directly from
  `chunking.py`'s own zero-based, gapless `Chunk.chunk_index` — never
  regenerated by the repository.
- **`backend/app/repositories/document_repository.py`** (additive):
  `mark_cleaned()` and `mark_chunked()`, mirroring the existing
  `mark_parsed()`/`mark_failed()` shape exactly. `mark_chunked()`'s own
  docstring states explicitly that callers must insert the chunk rows in
  the same transaction and commit them together — this function alone
  does not make that atomic.
- **`backend/app/core/audit.py`** (additive): three new
  `AuditEvent` constants — `DOCUMENT_CLEANING_FAILED`, `DOCUMENT_CHUNKED`,
  `DOCUMENT_CHUNKING_FAILED`. Deliberately **no** `DOCUMENT_CLEANED`
  success event — cleaning is an internal, always-conservative stage
  with nothing distinct to report before chunking actually completes;
  adding one would be audit noise, not signal.
- **`backend/app/services/document_service.py`** (the core of this
  slice): `process_document()` continues past its existing extraction
  stage rather than stopping at `PARSED`/`FAILED`:
  - **Cleaning stage**: `clean()` runs via `asyncio.to_thread()` (CPU-
    bound, same reasoning as extraction's own established pattern) on
    the freshly extracted `ExtractedDocument`. On success:
    `mark_cleaned()` + `db.commit()` — a durable checkpoint before
    chunking (the next, more expensive stage) begins. On any exception:
    `mark_failed()` + `DOCUMENT_CLEANING_FAILED` audit event + commit,
    returned as an ordinary `200` with a generic `failure_reason`, never
    a raw `500`.
  - **Chunking stage**: `StructureAwareChunker().chunk()` runs via
    `asyncio.to_thread()` on the cleaned document. A `ChunkingError`
    (validation/config-shape failure) or any other unexpected exception
    both land in `mark_failed()` + `DOCUMENT_CHUNKING_FAILED` + commit,
    same generic-`200` contract — a `ChunkingError`'s own message is
    used as the failure reason (it is already a safe, generic,
    user-facing string by that module's own design; an unexpected
    exception instead gets a fixed generic string, never `str(exc)`, to
    avoid leaking internals).
  - **Persistence + final transition, atomic**: `document_chunk_repository.bulk_create()`
    followed by `document_repository.mark_chunked()` followed by the
    `DOCUMENT_CHUNKED` audit event (`chunk_count` metadata), all inside
    one transaction, `db.commit()` once at the end. A crash between the
    chunk inserts and the final commit rolls the whole transaction back —
    a document can never be observed as `CHUNKED` without its chunks, or
    with only some of them.
  - **Concurrency**: a genuine race between two concurrent `/process`
    calls on the same document reaching the chunk-insert step
    simultaneously is caught via `document_chunks`' own
    `UniqueConstraint(document_id, chunk_index)` — `IntegrityError` is
    caught, `db.rollback()`'d, and the document is re-fetched via
    `document_repository.get_by_id_for_workspace()` so the response
    reflects the actual (concurrent winner's) persisted state rather
    than erroring. This is the same established pattern already used and
    reviewed for the upload flow's own duplicate-checksum race — no new
    mechanism introduced. Bounded, rate-limited duplicate work from two
    near-simultaneous calls is possible (deterministic re-extraction/
    re-cleaning/re-chunking of the same input) but never produces
    corrupted or partial state; this is a deliberate, documented
    trade-off rather than added locking/queueing infrastructure.
  - **A new helper, `_mark_failed_and_audit()`**, factors out the
    repeated mark-failed-plus-audit-plus-commit pattern now used at
    three failure points (extraction, cleaning, chunking) instead of
    duplicating it inline three times.
  - **`_REPROCESSABLE_STATUSES`** extended from `{UPLOADED, PROCESSING,
    FAILED}` to `{UPLOADED, PROCESSING, PARSED, CLEANED, FAILED}` —
    `CHUNKED` (and any later status) is now the terminal, `409`-rejected
    state for this endpoint's scope, since the pipeline no longer stops
    at `PARSED`.
  - **A deliberate architectural simplification, documented in code and
    here**: no extracted or cleaned *text content* is persisted anywhere
    between requests — only the document's `status` (plus `page_count`/
    `failure_reason`) is durable. This means resuming a document sitting
    at `PARSED` or `CLEANED` (interrupted mid-pipeline by a crash or a
    prior failed call) cannot literally skip already-completed stages;
    there is no stored content to resume *from*. Instead, calling
    `/process` again on such a document always re-runs extraction (and,
    if past `PARSED`, cleaning) from scratch against the same stored
    bytes. This is safe specifically because extraction and cleaning are
    both pure, deterministic functions of the same input — re-running
    them produces the same result, just at the cost of repeated work.
    This was a deliberate choice to avoid introducing new
    content-persistence infrastructure (no new column, no new table) for
    a resumability property the existing pure/deterministic stages
    already provide for free.
  - **`document_processing_jobs` — evaluated, not added.** `docs/DATA_MODEL.md`
    names this as a "potential entity" *if* the ingestion pipeline needs
    durable, queryable job records beyond the `documents.status` field.
    This slice's implementation confirms it does not: the single
    `status` column plus the client-triggered, idempotent-on-retry
    `/process` endpoint together already provide everything this
    project's synchronous, single-process architecture needs (resumability,
    retry, and observability via the existing audit events) — a separate
    job-tracking table would duplicate that state without adding a
    capability this architecture actually uses. `docs/DATA_MODEL.md` is
    updated to record this decision and its reasoning explicitly. No new
    ADR was written for it — the reasoning is a direct, narrow
    application of already-documented architecture (the modular-monolith/
    no-premature-infrastructure principle, and `docs/DATA_MODEL.md`'s own
    framing of the entity as conditional), not a new architectural
    decision in its own right.
- **`backend/tests/test_document_processing.py`** (modified): six
  pre-existing tests whose assertions assumed `PARSED` was the pipeline's
  terminal success state were renamed and updated to assert `CHUNKED`
  instead — an intended consequence of this slice's change, not a
  regression (`process_document()` now continues past `PARSED` by
  design).
- **`backend/tests/test_cleaning.py`** (new, 17 tests): CRLF/CR
  normalization, trailing-whitespace/leading-trailing/excess-blank-line
  cleanup, single-blank-line preservation, within-line-whitespace/
  punctuation/Unicode (Tamil/Kannada/Hindi/emoji-ZWJ)/combining-character
  preservation, page/heading/page_count metadata pass-through, multiple
  sections cleaned independently, empty/whitespace-only section and empty-
  document handling, determinism, and idempotence
  (`clean(clean(doc)) == clean(doc)`).
- **`backend/tests/test_document_lifecycle.py`** (new, 17 HTTP-level
  tests, real Postgres/Redis/filesystem, no mocks): full pipeline to
  `CHUNKED` with persisted-chunk ordering/metadata verification (PDF,
  TXT), no-duplicate-chunk-rows, cascade-delete of chunks on document
  deletion, resume-from-`PARSED`, resume-from-`CLEANED` (both simulated
  by directly setting `document.status` in the database to model an
  interrupted prior run), `CHUNKED`-rejected-with-`409`, cleaning-failure/
  chunking-`ChunkingError`/chunking-unexpected-exception all landing
  safely in `FAILED` with a generic reason and never a raw `500`, exactly
  one `DOCUMENT_CHUNKED` audit event with a correct `chunk_count`,
  confirmation that no `DOCUMENT_CLEANED` success event exists (locking
  in that deliberate design decision), VIEWER-role rejection (`403`),
  cross-workspace chunk isolation (`404` plus a check that persisted
  chunks carry the correct `workspace_id`), a concurrent-duplicate-
  chunk-insert-race recovery test (pre-seeding a winning row to force the
  `IntegrityError` path and asserting a clean `200`, never a `500`, with
  no duplicate `chunk_index`), a commit-order regression test proving the
  `CLEANED` transition commits *before* chunking is attempted (not just
  before the response is returned), and a slow-chunking event-loop-non-
  blocking test mirroring Slice 3.4's own precedent (`httpx.AsyncClient`
  + `ASGITransport`, an absolute shared clock, an unrelated concurrent
  request proven to finish without waiting on the slow chunking call).
- **Verification**: `ruff`/`mypy` clean (103 source files). Complete
  backend suite: **507/507 passing** (473 pre-Slice-3.6 + 34 new), **3
  consecutive runs**, real Postgres + real Redis, no regression in any
  existing test. No new dependency added.
- **Documentation updated this slice**: `PROJECT_STATE.md` (Slice 3.5
  moved to merged, Slice 3.6 described as implemented/not-yet-merged, the
  `document_processing_jobs` decision recorded), this file, `CHANGELOG.md`,
  `docs/DATA_MODEL.md`/`docs/API_CONTRACT.md` (where Slice 3.6 actually
  establishes behavior).

## Completed work (Issue #3 — Slice 3.7: embedding + vector indexing)

**Uncommitted, working-tree-only, on branch
`issue-3-slice-3-7-embeddings-indexing` (cut from `aa68079`).** Extends
`process_document()` past `CHUNKED` through `EMBEDDED`/`INDEXED` to
`READY` — completing GitHub Issue #3's full documented ingestion
lifecycle. No new endpoint.

- **`backend/app/ingestion/embedding.py`** (new): `EmbeddingProvider`
  protocol (`model_name`/`model_version`/`dimension`/`embed_batch()`),
  `EmbeddingError`/`EmbeddingTransientError` exceptions,
  `embed_with_retry()` (exponential backoff, retries only
  `EmbeddingTransientError`, bounded attempts), and one concrete
  implementation, `LocalHashingEmbeddingProvider` — deterministic,
  offline, no external API/key: tokenizes on Unicode word boundaries,
  hashes each token via `blake2b` (stable across process restarts,
  unlike Python's randomized built-in `hash()`), accumulates a ±1
  feature-hashed vector (the same "hashing trick" scikit-learn's
  `HashingVectorizer` uses), L2-normalizes it. 384 dimensions — chosen
  to match common small real embedding models (all-MiniLM-L6-v2/
  BGE-small) so a future swap needs no further migration. Chosen
  specifically so the whole pipeline is testable/demoable without a
  paid external API; the `EmbeddingProvider` abstraction lets a real
  hosted provider be added later (branch in `get_embedding_provider()`,
  matching `get_storage_provider()`'s/`get_email_provider()`'s own
  precedent) without touching any caller.
- **`backend/alembic/versions/0005_add_document_chunk_embeddings.py`**
  (new): adds `document_chunks.embedding` (`pgvector` `Vector(384)`,
  nullable), `embedding_model`/`embedding_dimension` (Text/Integer,
  nullable, per-row provenance), and an **HNSW** index
  (`vector_cosine_ops`) — chosen over IVFFlat since it needs no
  separate training/list-count step and stays correct under this
  project's incremental (not bulk-loaded) ingestion pattern. **Verified
  reversible directly, not just assumed**: `alembic downgrade 0004`
  (columns/index removed, confirmed via `sqlalchemy.inspect`) then
  `alembic upgrade head` (both recreated, index confirmed present via a
  direct `pg_indexes` query), followed by a clean full-suite re-run.
- **`backend/app/models/document_chunk.py`** (modified): the three new
  mapped columns (`pgvector.sqlalchemy.Vector(384)` for `embedding`).
- **`backend/app/core/config.py`** (modified): `embedding_provider:
  Literal["local"]` (matches `storage_provider`'s pattern) and
  `embedding_batch_size: int = 64` (validated `> 0`).
- **`backend/app/repositories/document_chunk_repository.py`**
  (modified): `set_embeddings()` — updates already-persisted rows in
  place (never inserts), same add/flush/no-commit convention as every
  other repository; trusts the caller's `chunks`/`embeddings` pairing
  (`zip(..., strict=True)`) rather than re-deriving it.
- **`backend/app/repositories/document_repository.py`** (modified):
  `mark_embedded()` (same atomicity contract as `mark_chunked()` —
  callers must update every chunk's embedding in the *same* transaction
  and commit together), `mark_indexed()` (no separate work — pgvector's
  HNSW index is maintained transactionally by the same `UPDATE`
  `mark_embedded()`'s caller already committed; this transition exists
  only to preserve the documented lifecycle and give an explicit,
  auditable signal), `mark_ready()` (the pipeline's terminal success
  state).
- **`backend/app/core/audit.py`** (modified): two new constants,
  `DOCUMENT_EMBEDDING_FAILED`, `DOCUMENT_READY`. Deliberately no
  `DOCUMENT_INDEXED` event — indexing performs no distinct work to
  report (same "no audit noise for an internal checkpoint" philosophy
  as Slice 3.6's missing `DOCUMENT_CLEANED`).
- **`backend/app/services/document_service.py`** (the core of this
  slice): `process_document()` restructured —
  - `_ALREADY_CHUNKED_STATUSES` (`CHUNKED`/`EMBEDDED`/`INDEXED`): a
    document at any of these already has real, durable
    `document_chunks` rows, so `process_document()` **skips**
    extraction/cleaning/chunking entirely for these statuses (unlike
    `PARSED`/`CLEANED`, where nothing but `status` is durable and the
    text stages must always re-run) and fetches the existing chunks via
    `document_chunk_repository.get_by_document()` before continuing
    straight into embedding. The extraction→cleaning→chunking portion
    was factored into a new helper, `_extract_clean_and_chunk()`, so
    `process_document()`'s own top-level control flow (branch on
    already-chunked, converge on the shared embedding phase) stays
    readable.
  - `_REPROCESSABLE_STATUSES` extended to include `CHUNKED`/`EMBEDDED`/
    `INDEXED` — only `READY` is now the terminal, `409`-rejected state.
  - **Embedding phase**: `_embed_chunks()` (new helper) batches chunk
    content into groups of `embedding_batch_size`, calling
    `embed_with_retry()` per batch, run via `asyncio.to_thread()` —
    matching extraction/cleaning/chunking's own established
    non-blocking-event-loop pattern. On success:
    `document_chunk_repository.set_embeddings()` +
    `document_repository.mark_embedded()` + commit, **atomically
    together** (a crash between writing vectors and committing
    `EMBEDDED` rolls the whole transaction back — a document is never
    observably `EMBEDDED` with only some chunks vectorized). On
    failure (`EmbeddingError` or any unexpected exception): `FAILED` +
    `DOCUMENT_EMBEDDING_FAILED` audit event + commit, same generic-`200`
    contract as every other stage.
  - **A genuine design question resolved, not assumed**: a document
    whose chunking legitimately produces **zero** chunks (an empty
    file, or e.g. a scanned, text-layer-less PDF — confirmed reachable,
    not hypothetical, by `chunking.py`'s own `_chunk_section()`, which
    correctly returns `[]` for empty/whitespace-only sections) has
    nothing to embed and can never be meaningfully retrieved. Rather
    than silently marking it `READY` with zero chunks (which would look
    successful while being permanently unretrievable), this is reported
    as an honest `FAILED` with a clear, specific reason ("The document
    contains no extractable text content to process."), audited as
    `DOCUMENT_EMBEDDING_FAILED`. See `SOLVING.md` for how this was
    actually discovered (an existing test fixture, not a design review).
  - `document_repository.mark_indexed()` then `mark_ready()` +
    `DOCUMENT_READY` audit event (metadata: `chunk_count`/
    `embedding_model`/`embedding_dimension`) + commit, each its own
    transaction, completing the pipeline.
  - **Concurrency**: two concurrent `/process` calls writing embeddings
    for the same already-persisted chunk rows are a plain, idempotent
    `UPDATE` (no unique constraint involved, unlike the chunk-insert
    race) — both compute the identical, deterministic vector from the
    same chunk content, so there is nothing to reconcile; no new
    locking/queueing mechanism was added, per this project's own
    "document bounded-safe concurrent duplicate work rather than adding
    unnecessary infrastructure" principle.
- **`backend/app/api/v1/documents.py`** (modified): the `/process`
  endpoint gained `embedding_provider: EmbeddingProvider =
  Depends(get_embedding_provider)`, matching `StorageProvider`'s own DI
  pattern exactly (testable via `app.dependency_overrides`, though no
  test needed an override since the local provider is already fast and
  deterministic); `embedding_batch_size` is read from settings and
  passed through explicitly, matching `max_upload_size_bytes`'s own
  convention.
- **`backend/tests/test_embedding.py`** (new, 14 unit tests, no
  database/HTTP/filesystem): dimension, cross-instance determinism,
  different-text-differs, L2-normalization, empty/whitespace-text
  zero-vector, Unicode, batch-order-matches-input-order, case
  insensitivity, provider self-description, and `embed_with_retry()`'s
  three behaviors (returns on first success, retries only
  `EmbeddingTransientError` with backoff then succeeds, gives up after
  `max_attempts`, does *not* retry a non-transient exception).
- **`backend/tests/test_document_lifecycle.py`** (extended, +6 tests,
  3 existing tests extended with embedding-shape assertions): embedding-
  provider-failure → `FAILED` + chunks preserved + no embedding written
  + exactly one `DOCUMENT_EMBEDDING_FAILED` audit row; zero-extractable-
  content → `FAILED` with the exact clear reason; exactly one
  `DOCUMENT_READY` audit event with correct `chunk_count`/
  `embedding_model`/`embedding_dimension` metadata; resume-from-`CHUNKED`
  **proven** to skip re-chunking (asserts the exact same chunk row IDs
  survive the resume, not a fresh duplicate set); resume-from-`EMBEDDED`
  reaches `READY`; `READY`-rejected-with-`409` after a resumed run
  (complementing `test_document_processing.py`'s equivalent for a
  fresh, non-resumed document — the old, now-incorrect
  "already-chunked-rejected-with-409" test was replaced, since `CHUNKED`
  is no longer terminal). The three existing full-pipeline-success tests
  now also assert `embedding is not None`/`len(embedding) == 384`/
  `embedding_model == "local-hashing"`/`embedding_dimension == 384`/
  L2-normalized magnitude ≈ 1.0.
- **`backend/tests/test_document_processing.py`** (3 tests renamed/
  updated): the Slice 3.4-era per-format success tests and the
  already-processed-rejection test now assert `READY`, not `CHUNKED` —
  an intended consequence of this slice, not a regression.
- **A genuine test-fixture bug found and fixed during this slice's own
  validation** (not a production defect — see `SOLVING.md` for the full
  root-cause writeup): both test files' shared `_blank_pdf()` helper
  produced a PDF with a real page but **zero extractable text**
  (`PdfWriter().add_blank_page()`), which every prior slice's tests
  happily accepted as a valid "successful" PDF fixture since nothing
  before Slice 3.7 ever inspected chunk *content*. Once Slice 3.7's
  zero-chunk safety check landed, these same fixtures legitimately
  failed at that check — correctly, not spuriously. Fixed by replacing
  the fixture with a hand-built `_pdf_with_text()` (byte offsets
  computed in code, not hand-copied) that embeds a real, minimal
  content stream, verified independently via `pypdf.PdfReader` before
  being wired into the tests.
- **Verification**: `ruff`/`mypy` clean (106 source files). Complete
  backend suite: **527/527 passing** (507 pre-Slice-3.7 + 20 new), **3
  consecutive runs**, real Postgres + real Redis, no regression in any
  existing test. No new dependency (`pgvector` already present since
  Slice 3.1).
- **Documentation updated this slice**: `PROJECT_STATE.md` (Slice 3.6
  moved to merged, Slice 3.7 described as implemented/not-yet-merged,
  the 5-day timeline noted), this file, `CHANGELOG.md`,
  `docs/DATA_MODEL.md`/`docs/API_CONTRACT.md`/`docs/RAG_DESIGN.md`/
  `docs/ARCHITECTURE.md`/`docs/SECURITY.md` (where Slice 3.7 actually
  establishes behavior), `SOLVING.md` (the blank-PDF-fixture discovery).

## Completed work (Issue #4 — Slice 4.1: conversation/message/citation/retrieval-event schema)

**Uncommitted, working-tree-only, on branch
`issue-4-slice-4-1-conversation-schema` (cut from `7241ec8`).** Schema
only — no service/API code reads or writes these tables yet; that is
the rest of Issue #4 (Slices 4.2+). Per the Issue #4 GitHub issue's own
"Explicit deliverables": `conversations`, `messages`, `citations`,
`retrieval_events` SQLAlchemy models + migration.

- **`backend/alembic/versions/0006_add_conversations_messages_citations_retrieval_events.py`**
  (new): creates all four tables in one migration, in FK-dependency
  order (`conversations` → `messages` → `citations`, `retrieval_events`
  last since it references both `conversations` and `messages`).
  `message_role` is a native Postgres enum (`USER`/`ASSISTANT`),
  matching `workspace_role`'s convention. Verified reversible directly:
  `alembic downgrade 0005` / `upgrade head` round-tripped cleanly, all
  four tables confirmed removed then recreated via direct
  `sqlalchemy.inspect()` queries.
- **`backend/app/models/conversation.py`** (new): `Conversation` —
  `workspace_id` (FK CASCADE), `created_by` (FK users, **SET NULL** —
  matches `Document.uploaded_by`'s precedent: a conversation should
  outlive the account that started it), `title` (nullable — auto-titling
  and rename are Issue #5).
- **`backend/app/models/message.py`** (new): `Message` + `MessageRole`
  enum. `workspace_id` is denormalized (reachable via `conversation_id`
  but stored directly anyway), matching `DocumentChunk.workspace_id`'s
  own precedent exactly — every workspace-scoped retrieval/security
  query needs to filter without an extra join.
  `role`/`content`/`created_at`.
- **`backend/app/models/citation.py`** (new): `Citation` — `ON DELETE
  CASCADE` from both `messages` and `document_chunks` (a citation has no
  independent meaning once either is gone, matching the project's
  existing "child dies with parent" convention). `document_id`/`page`/
  `section` are captured redundantly at citation-creation time (copied
  from the cited chunk), so `docs/REQUIREMENTS.md`'s "each citation
  references document, page, and section" is answerable directly from
  this row without a join. `workspace_id` denormalized too, same
  reasoning as `messages`. `rank` — 0-based position within its
  message's citation list, for deterministic display ordering (not a
  relevance score; that lives on `retrieval_events`).
- **`backend/app/models/retrieval_event.py`** (new): `RetrievalEvent` —
  `conversation_id`/`message_id` use **`ON DELETE SET NULL`**, not
  CASCADE, matching `AuditLog`'s own precedent: an observability/
  evaluation record should outlive the conversation/message it was made
  for. Both nullable — a standalone `/search` call has no conversation/
  message to attach to. `query_text` (the original user query, always
  preserved) is a separate column from `rewritten_query_text`
  (nullable, set only when rewriting actually changed the query) — per
  docs/REQUIREMENTS.md "Query handling": "preserving the original user
  query for transparency/debugging." `results` is `JSONB` (a ranked-
  candidate-list snapshot: `[{chunk_id, document_id, score, rank}, ...]`),
  matching `AuditLog.event_metadata`'s existing `JSONB` precedent — no
  new column-type pattern introduced. `method` is a plain string, not a
  native enum, matching `AuditLog.event_type`'s own reasoning (this
  taxonomy will grow).
- **`backend/app/models/__init__.py`** (modified): registers all four
  new models on `Base.metadata` (required for Alembic/tests to see
  them), matching the existing registration pattern exactly.
- **`backend/tests/test_conversation_schema.py`** (new, 23 tests,
  mirrors `tests/test_document_schema.py`'s own structure): table
  existence (parametrized across all four tables), FK validity/rejection
  for each table, cascade-delete chains (`conversations`→`messages`→
  `citations`, `document_chunks`→`citations`, `workspaces`→each new
  table), `ON DELETE SET NULL` behavior (`conversations.created_by`,
  `retrieval_events.conversation_id`), both `MessageRole` values
  persisting correctly, `retrieval_events.results` `JSONB` round-trip,
  `rewritten_query_text` staying distinct from `query_text`, nullable-
  field defaults, database-assigned timestamps — real Postgres, no
  mocks.
- **Verification**: `ruff`/`mypy` clean (112 source files). Complete
  backend suite: **550/550 passing** (527 pre-Slice-4.1 + 23 new), **3
  consecutive runs**, real Postgres, no regression in any existing
  test. No new dependency.
- **Documentation updated this slice**: `PROJECT_STATE.md` (Slice 3.7
  moved to merged, Issue #3 marked functionally complete, Slice 4.1
  described as implemented/not-yet-merged), this file, `CHANGELOG.md`,
  `docs/DATA_MODEL.md`.

## Completed work (Issue #4 — Slice 4.2: retrieval module)

**Uncommitted, working-tree-only, on branch
`issue-4-slice-4-2-retrieval` (cut from `5e4a626`).** Per the Issue #4
GitHub issue's own "Explicit deliverables": `backend/app/retrieval/` —
dense retrieval, BM25, fusion, reranker interface + implementation,
metadata filtering. Not yet wired to any API endpoint or the generation
module — that's the rest of Issue #4.

- **`backend/alembic/versions/0007_add_document_chunks_fts_index.py`**
  (new): a GIN functional index on `to_tsvector('english', content)` —
  `lexical_search()` below must use this exact expression or Postgres
  falls back to a sequential scan instead of using the index. Verified
  reversible directly (downgrade/upgrade round-tripped, index confirmed
  removed then recreated via `pg_indexes`).
- **`backend/app/retrieval/types.py`** (new): `RetrievalCandidate` — a
  frozen dataclass, not the `DocumentChunk` ORM model (matching
  `chunking.py`'s own `Chunk` precedent, Issue #3): a read-only,
  already-scored snapshot, no accidental database dependency for
  callers that only need the value. `score` is always "higher is
  better," consistently, at every stage (dense similarity, lexical
  rank, RRF score, reranked score) — callers never need to know which
  stage produced a given list.
- **`backend/app/retrieval/dense.py`** (new): `dense_search()` — pgvector
  `Vector.cosine_distance()` (the `<=>` operator), backed by the
  existing HNSW index (migration `0005`, Issue #3 Slice 3.7).
- **`backend/app/retrieval/lexical.py`** (new): `lexical_search()` —
  Postgres full-text search (`to_tsvector`/`plainto_tsquery`/
  `ts_rank_cd`), backed by migration `0007`'s new GIN index.
  `plainto_tsquery` (not `to_tsquery`) is used deliberately: it never
  interprets `&`/`|`/`!`/`:*` operator syntax a user might accidentally
  type, so a query like "cost & benefit" searches the literal words,
  never an unexpectedly narrowed boolean expression.
- **Both `dense_search()` and `lexical_search()` share the same two
  invariants**, each enforced at the SQL level (never a post-hoc
  filter): workspace-scoped (`WHERE workspace_id = ...`) and joined to
  `documents` requiring `status = READY` — a document still mid-
  pipeline (e.g. `CHUNKED` but not yet `EMBEDDED`) never surfaces
  partial/inconsistent results. Both accept an optional `document_id`
  filter (metadata filtering's currently-available dimension —
  collection-based filtering is deferred until `collections` exists).
  See `docs/SECURITY.md`'s new "Retrieval workspace isolation" section
  for the full security reasoning.
- **`backend/app/retrieval/fusion.py`** (new): `reciprocal_rank_fusion()`
  — standard RRF (`k=60`, the Cormack et al. 2009 default), deduplicates
  by `chunk_id` across input rankings, summing each list's own
  `1/(k+rank)` contribution. Chosen over combining raw scores because
  dense cosine similarity and lexical `ts_rank_cd` live on incomparable
  scales — RRF only looks at rank order, never score magnitude, so no
  cross-method score normalization is needed.
- **`backend/app/retrieval/reranker.py`** (new): `Reranker` protocol +
  `LexicalOverlapReranker` — deterministic, offline (Jaccard token-
  overlap between the query and each candidate's content), no
  commercial vendor/model selected yet, matching
  `LocalHashingEmbeddingProvider`'s own precedent (Issue #3, Slice 3.7)
  so the whole pipeline stays testable/demoable without a paid API. A
  real, explainable signal, not a stub — but genuinely weaker than a
  trained cross-encoder; swapping one in later is additive (implement
  `Reranker`, branch in `get_reranker()`), not a rewrite. Ties (the
  common zero-overlap case) preserve the input's own relative order
  (Python's sort is stable) — a sensible fallback to the fused ranking
  rather than an arbitrary reshuffle.
- **`backend/app/repositories/retrieval_event_repository.py`** (new):
  `create()` — same add/flush/no-commit convention as every other
  repository; the caller controls the transaction boundary.
- **`backend/app/retrieval/service.py`** (new): `hybrid_search()` — the
  single entry point: embed the query (reusing `EmbeddingProvider`/
  `embed_with_retry()` from Issue #3, Slice 3.7 unchanged) -> dense +
  lexical retrieval -> RRF fusion -> rerank a wider pool (3x
  `final_top_k`) down to `final_top_k` -> optionally record a
  `RetrievalEvent` (query, method, ranked results with scores, latency).
  Does not commit — matching every other service/repository function's
  own convention, the caller (a future endpoint) controls the
  transaction boundary.
  - **Query rewriting deliberately not implemented here**: a meaningful
    rewrite (e.g. resolving "it"/"that" from a prior turn) needs
    conversation history, which doesn't exist until a conversation-aware
    caller has it (later Issue #4 work, once the generation/context-
    builder layer exists). `hybrid_search()` accepts an optional
    already-computed `rewritten_query_text` and always records both it
    and the original `query_text` distinctly on the `RetrievalEvent`
    row, per docs/REQUIREMENTS.md's "preserving the original user query
    for transparency/debugging" — the original always drives retrieval
    when no rewrite is supplied, and the rewrite (when supplied) drives
    retrieval instead, but the original is never lost either way.
  - **Note for the next slice (endpoint wiring)**: `hybrid_search()` is
    a plain synchronous function, deliberately -- like every other
    CPU/IO-bound pipeline stage in this codebase (extraction, cleaning,
    chunking, embedding), it must be called via `asyncio.to_thread()`
    from an `async def` endpoint, never directly, or a slow query would
    block the single event loop for every other concurrent request.
- **`backend/tests/test_retrieval.py`** (new, 23 tests, real Postgres,
  no mocks): `dense_search()` (ranks the most similar chunk first using
  real `LocalHashingEmbeddingProvider` embeddings, excludes no-embedding
  chunks, excludes non-`READY` documents, workspace-scoped, `document_id`
  filter, `top_k` respected), `lexical_search()` (matches/no-match,
  workspace-scoped, excludes non-`READY` documents, `document_id`
  filter), `reciprocal_rank_fusion()` (a candidate in both rankings
  outranks one in only one, dedup, empty-input handling),
  `LexicalOverlapReranker` (exact match ranks above unrelated content,
  empty query is a no-op, never drops/adds candidates), and
  `hybrid_search()` end-to-end (results + a matching `RetrievalEvent`
  row, `record_event=False` skips persistence, workspace-scoped,
  `document_id` filter, original query preserved distinctly from a
  rewrite, `conversation_id`/`message_id` threaded through to real rows).
  - **A genuine test-design bug found and fixed during this slice's own
    validation** (not a retrieval-code defect): the initial "ranks the
    most similar chunk first" test used an "unrelated" comparison
    sentence that coincidentally shared three common stopwords ("the",
    "is", "for") with the query — since `LocalHashingEmbeddingProvider`
    has no IDF weighting (every token contributes equally regardless of
    whether it's a stopword or a meaningful word), this produced an
    exact score tie against the genuinely-relevant sentence's own
    3-meaningful-word overlap, purely by coincidence of matching
    *token count*, not semantic relevance. Root-caused by inspecting the
    actual tokens each sentence shared with the query, not by guessing.
    Fixed by choosing comparison content with *zero* token overlap
    (not even stopwords) with the query, for a deterministic,
    unambiguous assertion. This is a real, documented limitation of the
    un-weighted local hashing provider (not something Slice 4.2's own
    retrieval code should try to work around), recorded here and in
    `PROJECT_STATE.md`.
- **Verification**: `ruff`/`mypy` clean (121 source files). Complete
  backend suite: **573/573 passing** (550 pre-Slice-4.2 + 23 new), **3
  consecutive runs**, real Postgres, no regression in any existing
  test. No new dependency — pure stdlib (`re`, `dataclasses`) plus
  SQLAlchemy/pgvector/Postgres full-text search, all already present.
- **Documentation updated this slice**: `PROJECT_STATE.md` (Slice 4.1
  moved to merged, Slice 4.2 described as implemented/not-yet-merged),
  this file, `CHANGELOG.md`, `docs/RAG_DESIGN.md`, `docs/ARCHITECTURE.md`
  (`retrieval/` module + `Reranker` provider status), `docs/SECURITY.md`
  (new "Retrieval workspace isolation" section).

## Completed work (Issue #4 — Slice 4.3: generation module + conversations endpoint)

**Uncommitted, working-tree-only, on branch
`issue-4-slice-4-3-generation` (cut from `378fec4`).** Per the Issue #4
GitHub issue's own "Explicit deliverables": `backend/app/generation/`
(context builder, LLM provider interface + implementation, citation
engine) and minimal `/api/v1/conversations` endpoints sufficient to
invoke the pipeline. **This is the first slice composing Issue #3's
ingestion output with Issue #4's retrieval (Slice 4.2) and generation
(this slice) into one demonstrable "question -> grounded answer with
citations" flow — Issue #4's primary Definition-of-Done item.**

- **`backend/app/generation/context_builder.py`** (new):
  `build_context()` — packs ranked `RetrievalCandidate`s (best-first,
  never re-ranked here) into a citation-marked (`[1]`, `[2]`, ...)
  evidence string, deduplicating exact-content repeats and respecting a
  character budget (`max_chars`, default 4000 — character counts, not
  tokens, matching `chunking.py`'s own established convention). The
  first eligible candidate is always included, truncated if necessary,
  even if it alone exceeds the budget, so one long relevant chunk never
  produces an empty context when real evidence exists.
- **`backend/app/generation/llm_provider.py`** (new): `LLMProvider`
  protocol (`generate(*, system_prompt, context, query)` — three
  structurally separate arguments, never concatenated into one string)
  plus `LocalGroundedExtractiveProvider` — deterministic, offline, no
  external API/key: returns the provided evidence verbatim (still
  citation-marked), framed as an answer, never paraphrasing or
  inventing content beyond what `context` already contains. Grounded
  *by construction* (nothing in its output didn't come from the
  evidence) and immune to prompt injection *by construction* (it never
  interprets `context` as anything but inert text to quote — see the
  package's own `__init__.py` docstring for the full reasoning and
  `tests/test_generation.py`'s dedicated test locking this in). Empty
  context -> a fixed, honest "I don't have enough information" answer,
  never a fabricated one.
- **`backend/app/generation/service.py`** (new): `generate_answer()` —
  composes `build_context()` + `LLMProvider.generate()` behind a fixed
  system prompt that explicitly instructs evidence-only answers and
  frames the EVIDENCE section as untrusted data, not instructions (per
  `docs/SECURITY.md` §"Prompt injection defense") — stated explicitly
  for the benefit of a future real provider implementation, even though
  the shipped local provider doesn't need it (it never interprets
  `context` at all).
- **`backend/app/repositories/citation_repository.py`** (new):
  `bulk_create()` — same add/flush/no-commit convention as every other
  repository; takes plain `(marker, RetrievalCandidate)` tuples rather
  than importing from `app.generation` (repositories stay a leaf layer,
  never importing from `services`/higher-level packages).
- **`backend/app/generation/citation_engine.py`** (new):
  `create_citations()` — turns a `BuiltContext`'s evidence blocks into
  persisted `Citation` rows tied to the specific message and the exact
  chunks the answer actually drew from. Does not commit — the caller
  persists this together with the assistant `Message` row in one
  transaction (see below).
- **`backend/app/repositories/conversation_repository.py`** and
  **`message_repository.py`** (new): `create()`/`get_by_id_for_workspace()`
  (workspace-scoped in the query itself, matching
  `document_repository`'s own IDOR-defense shape) and
  `create()`/`list_for_conversation()` respectively — same conventions
  as every other repository.
- **`backend/app/services/conversation_service.py`** (new): the
  orchestrator.
  - `create_conversation()` — creates and commits a `Conversation` row.
  - `post_message()` — persists the user's `Message` (commit), runs
    retrieval + generation off the event loop via `asyncio.to_thread()`,
    then persists the assistant `Message` + its `Citation` rows
    together in one final transaction (commit). A crash between
    generating the answer and that final commit loses only the
    in-flight answer — the user's own question is already durably
    recorded, and no citation is ever left without its message or vice
    versa.
  - **A real thread-safety question, reasoned through explicitly, not
    assumed**: `hybrid_search()` (which touches the SQLAlchemy `Session`
    for its own SQL queries) is called from inside the
    `asyncio.to_thread()`-offloaded function, alongside the pure-CPU
    `generate_answer()` call — both in the *same* worker thread,
    sequentially. This is safe because the calling coroutine is fully
    suspended for the duration of `await asyncio.to_thread(...)` and
    does not touch `db` again until it returns, so there is never
    concurrent access to the same `Session` from two threads at once —
    the specific hazard Issue #3 Slice 3.4's own review flagged
    ("SQLAlchemy Sessions aren't thread-safe") was genuinely *concurrent*
    cross-thread access in a test harness, not this sequential
    hand-off-and-return pattern, which is the standard technique for
    using a sync SQLAlchemy `Session` from inside an async FastAPI
    route. Documented directly in `_run_retrieval_and_generation()`'s
    own docstring so this reasoning isn't lost.
- **`backend/app/schemas/conversation.py`** (new): `ConversationRead`,
  `MessageRead` (with a nested `citations: list[CitationRead]`),
  `CitationRead` (`document_id`/`page`/`section`/`rank` — never the raw
  chunk content or ID), `MessageCreate` (`content`, 1–4000 chars).
- **`backend/app/api/v1/conversations.py`** (new) + registered in
  `app/api/v1/router.py`: `POST /workspaces/{workspace_id}/conversations`
  (MEMBER), `POST .../conversations/{conversation_id}/messages` (MEMBER,
  rate-limited), `GET .../conversations/{conversation_id}/messages`
  (VIEWER) — role minimums match the established MEMBER-for-write/
  VIEWER-for-read convention exactly (document upload/process precedent
  for MEMBER; workspace member-list precedent for VIEWER).
- **`backend/app/core/rate_limit.py`** (modified): a new
  `conversation_message_rate_limiter` (`FixedWindowRateLimiter(limit=20,
  window_seconds=60)`) and `enforce_conversation_message_rate_limit()` —
  identical Tier A shape (IP + user ID) and rationale to
  `enforce_document_process_rate_limit()` (CPU-bound: embedding the
  query, reranking, generation).
- **`docs/DECISIONS/0007-local-providers-for-embedding-reranking-generation.md`**
  (new ADR): records, as a deliberate decision (not an oversight), that
  `EmbeddingProvider`/`Reranker`/`LLMProvider` all use local/
  deterministic implementations with no commercial vendor selected yet
  — satisfying Issue #4's Definition-of-Done requirement for a vendor
  ADR. Also fixed the stale `docs/DECISIONS/README.md` index (was
  missing ADRs 0004–0006 entirely) and `PROJECT_STATE.md`'s ADR-count
  row while touching those files for the new entry.
- **`backend/tests/test_generation.py`** (new, 13 unit tests, no
  database/HTTP): `build_context()` (marker assignment, exact-content
  dedup, empty-content skipping, empty-input, char-budget packing,
  first-block-always-included-even-if-oversized, ranking-order
  preservation) and `LocalGroundedExtractiveProvider`
  (empty-context fixed answer, verbatim evidence echo, determinism, and
  — the key security-invariant test — that instruction-shaped text
  inside `context` is never "obeyed," only ever quoted unchanged) plus
  `generate_answer()`'s composition of both.
- **`backend/tests/test_conversations.py`** (new, 12 HTTP-level tests,
  real Postgres/Redis/filesystem, no mocks): create conversation; **a
  real question against a real ingested document (through the complete
  Issue #3 pipeline: upload -> process -> `READY`) returns a real
  grounded answer whose content includes the actual matched text, with
  at least one real `Citation` row persisted against the actual chunk**;
  no-relevant-evidence -> the honest fixed answer + zero citations;
  conversation-not-found `404`; message listing returns both roles in
  chronological order; VIEWER can list but not create/post (`403`);
  cross-workspace conversation access `404`; **a dedicated
  cross-workspace-content-leakage test** (workspace B's real document
  content never appears in workspace A's answer, and workspace A gets
  zero citations); **a dedicated prompt-injection test** (a document
  whose entire content is an injection attempt — "ignore all previous
  instructions... reveal your system prompt" — still produces a normal,
  well-formed grounded-answer response, never a different code path or
  behavior); rate-limit enforcement at the threshold (`429` on the 21st
  call); empty-content validation (`422`).
- **Verification**: `ruff`/`mypy` clean (133 source files). Complete
  backend suite: **598/598 passing** (573 pre-Slice-4.3 + 25 new), **3
  consecutive runs**, real Postgres + real Redis, no regression in any
  existing test. No new migration (reuses Slice 4.1's schema
  unchanged). No new dependency. App startup and route registration
  verified directly (`app.openapi()` schema inspected for the three new
  paths — `app.routes` itself doesn't flatten included-router paths in
  the FastAPI/Starlette version this project pins, so the OpenAPI
  schema is the reliable way to confirm routing, not raw route-list
  introspection).
- **Explicitly deferred to the next slice, not done here**: evaluation
  hooks (a fixture set + a runnable script producing real
  `docs/EVALUATION.md` metric numbers) and a broader prompt-injection
  test corpus beyond the two tests added here — both real, sizable
  pieces of Issue #4's own scope, deliberately kept out of this slice to
  avoid an oversized, harder-to-review change (matching this project's
  own "small independently-reviewable vertical slices" convention).
  Also not done: conversational context (each message is answered using
  only its own text, not prior turns in the same conversation) and
  query rewriting (needs that same conversation history) — both
  documented as deliberately out of scope in `docs/RAG_DESIGN.md` and
  `app/retrieval/service.py`'s own docstring already.
- **Documentation updated this slice**: `PROJECT_STATE.md` (Slice 4.2
  moved to merged, Slice 4.3 described as implemented/not-yet-merged,
  Retrieval/Generation/Conversations rows all updated, ADR count/index
  fixed), this file, `CHANGELOG.md`, `docs/API_CONTRACT.md` (new
  "Implemented: conversations" section), `docs/RAG_DESIGN.md`
  (Query handling/Generation/Citations sections), `docs/ARCHITECTURE.md`
  (`generation/` module + `LLMProvider` status), `docs/DATA_MODEL.md`,
  `docs/DECISIONS/README.md` (index fixed).

## Explicitly NOT done (do not assume otherwise)

- **Slice 3c is merged** (`75dd466`, PR #15) — `AuditEvent.RATE_LIMITED`
  and `AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED` are both emitted,
  exactly once per escalation, from `login`/`forgot-password`/
  `reset-password`. This remains deterministic, rule-based logic
  throughout — never call it "AI" or claim ML/statistical evaluation
  unless an actual evaluated model backs that claim, per the ADR's
  explicit non-goal.
- **Playwright E2E is merged** (`e1c4858`, PR #16) — see "Completed work
  (Playwright E2E — authentication/password-recovery)" above. Covers
  only the authentication/password-recovery surface; no document/chat/
  search UI exists yet for E2E coverage to extend to.
- **Issue #3 (all seven slices) is merged** (`79d4787` PR #17, `941c1a7`
  PR #18, correctness-fix `5e6fdc2` PR #19, `a6762e2` PR #20, `2961b62`
  PR #21, `237be97` PR #22, `aa68079` PR #23, `7241ec8` PR #24) — the
  full ingestion pipeline (`UPLOADED → READY`) is functionally complete.
  `AuditEvent.DOCUMENT_UPLOADED`/`DOCUMENT_PARSED`/`DOCUMENT_PARSING_FAILED`/
  `DOCUMENT_CLEANING_FAILED`/`DOCUMENT_CHUNKED`/`DOCUMENT_CHUNKING_FAILED`/
  `DOCUMENT_EMBEDDING_FAILED`/`DOCUMENT_READY` are implemented — the
  broader document-lifecycle taxonomy (delete, etc.) still doesn't
  exist; those land with a later Issue #3 slice, if ever prioritized.
- **Issue #4 (Hybrid RAG Pipeline) has started**: Slice 4.1
  (`conversations`/`messages`/`citations`/`retrieval_events` schema) is
  merged (`5e4a626`, PR #25). Slice 4.2 (the retrieval module —
  dense/lexical/fusion/reranking) is merged (`378fec4`, PR #26). Slice
  4.3 (generation module + a minimal conversations ask-flow endpoint) is
  implemented and fully tested, on branch
  `issue-4-slice-4-3-generation` — not yet committed, pushed, or opened
  as a PR. **A real question against a real ingested document now
  returns a real grounded answer with citations, end-to-end.**
  Explicitly not done yet: evaluation hooks, a broader prompt-injection
  test corpus, conversational context/query rewriting, and everything in
  `docs/REQUIREMENTS.md` "Chat" beyond the bare ask flow (rename/delete/
  search conversations, regenerate/retry, feedback — Issue #5).
- **`client_ip()` (unconditional, no trusted-proxy handling) is still
  used elsewhere** — `app/api/v1/auth.py`'s audit/session IP recording
  and `app/core/dependencies.py`'s authorization-denial audit events
  still call `client_ip()`, not `resolve_client_ip()`. Only the
  rate-limit dimensions switched to the trusted-proxy-aware resolver;
  changing what IP audit logs/sessions record is a separate decision,
  deliberately out of scope here.
- **No multi-instance/concurrent-HTTP-load test exists** — the wiring is
  verified correct sequentially (tests) and against a single running
  backend instance (Docker). The distributed-coordination property this
  whole ADR exists for (§2.1) has not been exercised with more than one
  backend process under real concurrent load, since no such deployment
  exists.
- **Evaluation hooks and a broader prompt-injection test corpus (Issue
  #4, next slice)** — not started. This is the very next work once
  Slice 4.3 merges.
- **Endpoint-driven concurrency test under real HTTP load** — not added
  in the Slice 2 review-fix pass either; the property is proven at the
  engine level (`test_redis_rate_limiter.py`, merged with Slice 1) and
  sequentially at the endpoint level, not under genuinely concurrent HTTP
  traffic.
- **Ordinary `THROTTLE`/429 rejections still aren't logged** (ADR §15) —
  only the Redis-failure *fallback* path gained logging in this pass; a
  broader, pre-existing gap belonging with the future abuse-detection/
  observability work, not a Slice 2 regression.
- **Both Slice 1 (`46ef03b`, PR #11) and Slice 2 (`5391a78`, PR #12) are
  merged into `main`.** Both feature branches were deleted on `origin`
  after their respective merges.

## Next major task: GitHub Issue #4 — evaluation hooks + prompt-injection corpus (Slice 4.4)

**ADR 0006's deterministic abuse-protection layer is functionally
complete end-to-end and fully merged (Slices 1–3c).** Browser E2E
coverage for the authentication/password-recovery flows is implemented,
validated, and merged (PR #16, `e1c4858`). **GitHub Issue #3 (Knowledge
Ingestion) is fully merged and functionally complete end-to-end**
(PR #17 `79d4787` through PR #24 `7241ec8`). **Issue #4, Slices 4.1 and
4.2 are merged** (PR #25 `5e4a626`, PR #26 `378fec4`).

**Slice 4.3 (generation module + a minimal conversations ask-flow
endpoint — the first end-to-end "question -> grounded answer with
citations" flow) is implemented and fully tested** on branch
`issue-4-slice-4-3-generation` (cut from `378fec4`) — not yet
committed, pushed, or opened as a PR.

**Before anything else starts**: commit Slice 4.3, push the branch,
open a PR, confirm CI green, and **merge it promptly** — the 5-day
timeline (see "Current task" above) authorizes merging as soon as a
slice/issue is reviewed and CI-green, without waiting for a separate
per-PR instruction.

**Immediately after merging, with no further go-ahead needed:**
continue Issue #4 with the two deliverables deliberately deferred out of
Slice 4.3 (see that slice's own "Completed work" entry for why):

1. **Evaluation hooks** — a small fixture set (a handful of documents +
   known-relevant query/answer pairs) plus a runnable script that
   computes real (never fabricated — `docs/EVALUATION.md`'s explicit
   "Rule: never fabricate results") retrieval metrics (Recall@K,
   Precision@K, MRR, nDCG, Hit Rate, using `hybrid_search()`'s own
   output) and generation metrics (faithfulness, answer relevance,
   context relevance, citation correctness/completeness, using
   `RetrievalEvent`/`Citation` rows already being recorded). This
   proves the pipeline is measurable — it is explicitly NOT the full
   evaluation/experiment-tracking system (that's Issue #7).
2. **A broader prompt-injection test corpus** — Slice 4.3 added two
   targeted tests (`test_instruction_like_document_content_is_never_followed`
   in `test_conversations.py`, and a unit-level equivalent in
   `test_generation.py`); the Issue #4 GitHub issue's own testing
   requirements call for a corpus (plural, varied injection shapes —
   attempts to leak the system prompt, cross-workspace data
   exfiltration attempts phrased as document content, etc.), not just
   one or two examples.

Once these land, Issue #4's explicit deliverables/Definition-of-Done are
complete and the 5-day plan moves to Day 3 (Issue #5, product
experience) — see the Issue #4 GitHub issue (`gh issue view 4`) for the
complete, authoritative list before declaring it done; inspect
`docs/RAG_DESIGN.md`/`docs/API_CONTRACT.md`/`docs/EVALUATION.md` before
implementing. **Critical, explicitly restated security requirement**:
retrieved document content is untrusted data, never instructions — see
`docs/SECURITY.md` §"Prompt injection defense", now backed by real
tests (Slice 4.3) proving the shipped `LocalGroundedExtractiveProvider`
upholds it; workspace isolation at retrieval time is implemented and
tested (Slice 4.2, see `docs/SECURITY.md` §"Retrieval workspace
isolation") — nothing further needed there, just don't regress it.

## Blockers

None currently. `gh` CLI access is confirmed working in this
environment. Docker was not touched this session — Slice 4.3 adds no
new pip dependency and no Docker-relevant file changed (`git diff main
-- backend/pyproject.toml backend/uv.lock` is empty), so no rebuild was
needed; no new migration either (Slice 4.3 reuses Slice 4.1's schema
unchanged). Slice 4.2's own migration (`0007`), Slice 4.1's own
migration (`0006`), and Slice 3.7's own migration (`0005`) were all
verified reversible directly against the real running Postgres — a
stronger check than a Docker rebuild would add on its own.

## Tests run

- Baseline (before Redis, per Slice 1's explicit instruction):
  `uv run ruff check .` (pass), `uv run mypy .` (pass, 67 files),
  `uv run pytest -v` (**119/119 pass**, real Postgres).
- **Slice 1 (merged, `46ef03b`): 170/170 pass** (119 existing + 51 new),
  `mypy` clean (74 files) — independently re-validated in an isolated
  worktree before that commit; see PR #11's own record.
- **Slice 2, before this checkpoint's review-fix pass:** `uv run ruff
  check .` (pass), `uv run mypy .` (pass, 75 files), `uv run pytest -v`
  (**175/175 pass** — 170 from Slice 1 + 5 HTTP-level wiring tests,
  against real Postgres **and** real Redis).
- **Slice 2, after the review's P1/P2 fixes, pre-merge:** `uv run ruff
  check .` (pass), `uv run mypy .` (pass, **75 files**), `uv run pytest
  -v` (**183/183 pass** — 170 from Slice 1 + 13 from
  `test_rate_limit_wiring.py`, against real Postgres **and** real
  Redis). Re-ran the full suite 3 times to check for flakiness — none
  observed. This was the exact code committed as `f61737f` and merged
  as `5391a78` — **this 183/183 figure now describes the committed
  codebase on `main`**, not just a working tree.
- **PR #12, GitHub Actions CI (post-merge verification, independent of
  the local run above):** 3/3 checks passed — backend lint/typecheck/
  tests, frontend lint/typecheck/tests/build, Docker build check. This
  session's own Docker/WSL integration became unavailable shortly after
  the local 183/183 run above, so this CI result is the first
  re-verification of the merged code since then.
- New tests this checkpoint (8, added to `test_rate_limit_wiring.py`):
  Redis-key-creation tests for `refresh` and `forgot-password`; a
  `reset-password` test proving IP-only dimension creation; Tier A
  fallback tests for `refresh`/`forgot-password`/`reset-password`; an
  endpoint-driven multi-dimension atomicity test for `login`; a
  cross-user account-isolation test. See the "Slice 2 read-only
  security/architecture review" entry above for what each proves.
- Docker: full stack live-verification of the original wiring is
  unchanged from the prior checkpoint (see "Completed work" above) — not
  re-run this checkpoint, since the fixes were logging/docstring/test
  additions only, not a change to the wiring's runtime behavior.
- Frontend: untouched across every Redis checkpoint — not re-run (no
  frontend file changed).
- **Slice 3a (this checkpoint, uncommitted): `uv run ruff check .`**
  (pass, 78 files) and **`uv run mypy .`** (pass, "Success: no issues
  found in 78 source files") both clean, covering all three new files.
  **`uv run pytest --collect-only -q`** succeeded: **215 tests collected**
  (183 existing + 32 new) — this confirms imports/wiring are structurally
  correct, it is **not** a passing-test count. Actually running
  `uv run pytest tests/test_abuse_state.py -q` produced **32 errors**,
  every one a `sqlalchemy.exc` connection failure from the shared
  session-scoped `_migrated_database` autouse fixture (it requires a real
  Postgres for an Alembic migration, gating every test file including the
  Redis-only ones). Confirmed this is purely environmental, not a code
  defect: `docker compose ... up -d db redis` failed with "docker: command
  not found"; `/mnt/wsl/` contains only `resolv.conf` (no
  `docker-desktop` integration socket); direct TCP connection attempts to
  both `127.0.0.1:6379` and `127.0.0.1:5432` returned "Connection
  refused." Per explicit prior instruction, no Docker-level workaround
  (installing Docker Engine in WSL, editing Docker config) was attempted.
  **This particular attempt never got the 32 new tests executed against a
  real Redis** — superseded by the real-Redis validation recorded
  immediately below, from a later checkpoint in this same slice.

- **Slice 3a real-Redis validation (later checkpoint, still uncommitted):**
  once Docker Desktop/WSL integration came back, the *host shell's own*
  path to the running containers' published ports (`127.0.0.1:5432`,
  `127.0.0.1:6379`) was tested and found broken — TCP handshake succeeds,
  but the protocol-level read is reset immediately (`psycopg.OperationalError:
  server closed the connection unexpectedly`; `redis.ConnectionError:
  Connection reset by peer`) — confirmed as an environment/networking
  fault (not Postgres/Redis/code) via `/api/v1/health/ready` and
  `redis-cli ping` both succeeding from **inside** the Docker network, and
  via a previously-passing, unrelated Redis test file
  (`test_redis_rate_limiter.py`) failing identically. Worked around by
  running the tests **inside the already-running `compose-backend-1`
  container** instead, over its internal `db`/`redis` hostnames (the same
  values `docker-compose.yml` already sets as that container's own
  `DATABASE_URL`/`REDIS_URL` — no override needed). Since that container's
  image predates the uncommitted Slice 3a files (no bind mount), the three
  new files were `docker cp`'d into the container's writable layer for the
  duration of the validation, then removed afterward — no image rebuild,
  no compose/file change, no host repo change.
  - `uv run pytest tests/test_abuse_state.py -v` **32 passed**, 3
    consecutive times (5.6–5.8s each run, no flakiness).
  - Live Redis inspection (calling `record_login_failure`/
    `record_ip_failure` directly, before any cleanup fixture ran)
    confirmed real `abuse:*` keys of every expected type/TTL
    (`abuse:failcount:*` strings TTL 60s, `abuse:distinct_ips:acct:*`
    string/HLL TTL 60s with correct `PFCOUNT`, `abuse:strict:*` hashes TTL
    1200s, `abuse:block:*` string flags TTL 600s) — every key observed had
    a finite, positive TTL, and no raw email substring appeared in any key
    name or value (scanned directly, not assumed).
  - `ruff check .` / `mypy .` also re-run inside the container: both
    clean, matching the host results.
  - **This container's image was itself stale relative to `main` HEAD**
    (missing exactly the 8 tests Slice 2's review-fix pass added to
    `test_rate_limit_wiring.py` — confirmed by diffing collected test IDs
    against the host's 215) — so the full-suite run inside that container
    collected 207, not 215. That run initially showed 5 failures, all in
    `test_password_reset.py`, root-caused to the container's
    `EMAIL_PROVIDER=smtp` app-runtime setting (for manual Mailpit testing)
    versus the test suite's implicit expectation of `EMAIL_PROVIDER=console`
    (`conftest.py` doesn't default this one, unlike `DATABASE_URL`/
    `REDIS_URL`/`SECRET_KEY`) — confirmed via a one-off invocation-level
    override (`EMAIL_PROVIDER=console`, no file changed): 207/207 passed.
    **Neither 207 number should be read as "the current 215-test suite
    passed"** — that still requires either a fixed host-to-container
    network path or a freshly rebuilt container image, neither done this
    checkpoint.
  - **Net result: the 32 Slice 3a tests are real-Redis validated.** Slice
    3a has since committed/merged (`026dcf3`, PR #13).
- **Slice 3b (this checkpoint, uncommitted): `uv run ruff check .`**
  (pass, 81 files) and **`uv run mypy .`** (pass, 81 source files) both
  clean, host and container. **`tests/test_abuse_decision.py` (33 tests)
  plus the unaffected `tests/test_abuse_state.py` (32 tests) — 65/65
  passed, 3 consecutive runs**, inside `compose-backend-1` over
  Docker-internal hostnames (the host shell's own published-port path
  was tested again this session and remained broken, same symptom as
  before — TCP handshake succeeds, protocol read reset). Two test-design
  bugs (not implementation bugs) were found and fixed during this
  validation — see "Completed work (Redis abuse layer — Slice 3b)" for
  exactly what and why.
  - **Circular-import fix verified**: `from app.main import create_app;
    create_app()` succeeds; `mypy .` passes across all 81 files
    (including the explicit-reexport fix `DimensionSpec as DimensionSpec`
    needed for `no_implicit_reexport` compliance after the
    `token_bucket_types.py` extraction).
- **Test-isolation fix (commit `46a2860`, same branch)**: full
  pre-existing suite, run inside the container from a freshly flushed
  Redis, `EMAIL_PROVIDER=console` overridden to match CI's own
  environment (confirmed via `.github/workflows/ci.yml` that CI never
  sets `EMAIL_PROVIDER`) — before the fix, 238 passed/2 failed locally
  (240 collected); CI itself independently hit 245 passed/3 failed on
  PR #14 (the same root cause, landing on one extra test due to a
  different execution order). After the fix: **the complete 248-test
  suite (215 pre-abuse-layer + 32 Slice 3a + 33 Slice 3b — `conftest.py`
  changes don't add tests, they just fix isolation) passed 248/248, 3
  consecutive runs**, real Postgres + real Redis. `ruff check .`/`mypy .`
  both clean after the fix too (81 source files — the fixture change is
  test-only). **Slice 3b subsequently merged into `main` as `42529e3`
  (PR #14) with CI green (3/3 checks).**
- **Slice 3c (this checkpoint, uncommitted): `uv run ruff check .`**
  (pass, 82 files) and **`uv run mypy .`** (pass, 82 source files) both
  clean, host and container. **`tests/test_abuse_audit.py` (6 new
  HTTP-level tests) — 6/6 passed, 3 consecutive runs**, plus every
  related focused suite (`test_abuse_state.py`, `test_abuse_decision.py`,
  `test_auth.py`, `test_rate_limit_wiring.py`, `test_redis_rate_limiter.py`,
  `test_password_reset.py` — 138/138 combined) and the **complete
  254-test backend suite passing 254/254, 3 consecutive runs**, all
  against real Redis + real PostgreSQL inside `compose-backend-1` (the
  host shell's own published-port path was tested again this session and
  remained broken, same symptom as every prior session). Two test-design
  bugs (not implementation bugs) were found and fixed during this
  validation — see "Completed work (Redis abuse layer — Slice 3c)" for
  exactly what and why. **Slice 3c subsequently merged into `main` as
  `75dd466` (PR #15) with CI green (3/3 checks).**
- **Playwright E2E (this checkpoint, uncommitted): `npx eslint e2e/
  playwright.config.ts`** and **`npx tsc --noEmit -p .`** both clean.
  **19 tests across 3 spec files (`app-availability.spec.ts`,
  `auth.spec.ts`, `password-recovery.spec.ts`) — 19/19 passed, 3
  consecutive clean runs**, against the real frontend/backend/
  PostgreSQL/Redis/Mailpit stack (already-running `docker compose`
  services this session; host-shell HTTP connectivity to the published
  `3000`/`8000`/`8025` ports was tested and confirmed working this
  session — unlike the raw Postgres/Redis wire-protocol issue seen in
  earlier sessions, plain HTTP was reachable here). An initial attempt
  at 3 back-to-back runs with no gap hit a real, correctly-working `429`
  from the backend's own `register` rate limiter (not flakiness — see
  "Completed work (Playwright E2E...)" for the exact mechanism and fix).
  Existing **48 vitest tests** and `npm run lint` confirmed unaffected.
  **Since merged into `main` as squash commit `e1c4858` via PR #16.**
- **Issue #3, Slice 3.1 (document schema): `uv run ruff check .`** (pass)
  and **`uv run mypy .`** (pass, 86 source files — 2 findings surfaced
  and fixed along the way: `sa.inspect(db_session.bind)` typed
  `Any | None`, switched to `sa.inspect(engine)`). **19 new tests
  (`tests/test_document_schema.py`) — 19/19 passed** (one test-design bug
  found and fixed during validation, not a schema defect: a
  cascade-delete assertion read a stale ORM identity-map object after a
  DB-level `ON DELETE CASCADE`, before `db_session.expire_all()` was
  added — see "Completed work (Issue #3 — Slice 3.1...)" above for the
  full explanation). **Complete backend suite: 273/273 passing** (254
  pre-existing + 19 new), **3 consecutive runs**, real Postgres + real
  Redis, no regression in any existing auth/workspace/rate-limit/abuse
  test. **Migration `0004` explicitly verified reversible**: `alembic
  downgrade 0003` (both tables + the `document_status` enum removed,
  confirmed via `sqlalchemy.inspect`) then `alembic upgrade head` (both
  tables recreated with the correct columns), followed by a clean full
  suite re-run. This session hit a genuine, resolved environment
  interruption partway through (Docker Desktop's WSL integration
  dropped, then was restored on the Windows side) — documented in
  "Blockers" above; not a code defect. Schema/model/migration/tests
  committed as `36fe8b0`; documentation reconciliation as a second,
  separate commit — pushed on branch `issue-3-slice-3-1-document-schema`
  (cut from `e1c4858`), opened as PR #17, **since merged into `main` as
  squash commit `79d4787`, CI green (4/4 checks).**
- **Issue #3, Slice 3.2 (StorageProvider abstraction): `uv run ruff
  check .`** (pass) and **`uv run mypy .`** (pass, 88 source files, no
  new findings). **14 new tests (`tests/test_storage_provider.py`) —
  14/14 passed**, against a real filesystem (`tmp_path`, no mocks) — no
  test-design bugs found this time. **Complete backend suite: 287/287
  passing** (273 pre-existing + 14 new), **3 consecutive runs**, no
  regression in any existing test. This slice touches no
  database/Redis state directly, so no dedicated Postgres/Redis
  validation beyond the full suite's own existing real-Postgres/
  real-Redis coverage was applicable. Committed as `91d98b7` + docs
  commit `d57ccdb`, pushed on branch `issue-3-slice-3-2-storage-provider`
  (cut from `79d4787`), opened as PR #18, **since merged into `main` as
  squash commit `941c1a7`, CI green (4/4 checks).**
- **Correctness/security review of Slice 3.2**: `uv run ruff
  check .`/`uv run mypy .` both clean (88 source files, no new findings)
  after the fix. **7 new tests, 14 → 21 in `tests/test_storage_provider.py`
  — 21/21 passed**, against a real filesystem (permission bits via
  `chmod`, a real symlink escaping the root) — no mocks. Two
  stdlib-behavior assumptions from the original implementation were
  empirically disproven this pass (see "Correctness/security review"
  above for detail) — a genuine, useful correction, not a test-design
  bug. **Complete backend suite: 294/294 passing** (273 pre-existing +
  21 new), **3 consecutive runs**, no regression in any existing test.
  Originally committed as `050b185`/`03c870e` on the now-merged Slice
  3.2 branch (too late to land in PR #18 — see "Current task" above for
  why); **cherry-picked cleanly (verified: zero diff between the
  pre-fix tree and merged `main`'s tree for both changed files) as
  `6e96481`/`d950d4e` onto a fresh branch,
  `issue-3-slice-3-2-storage-error-handling-fix`, cut from the merged
  `941c1a7`, pushed, and opened as PR #19, **since merged into `main` as
  squash commit `5e6fdc2`, CI green (4/4 checks).**
- **Issue #3, Slice 3.3 (document upload API): `uv run ruff check .`**
  (pass) and **`uv run mypy .`** (pass, 94 source files). **67 new
  tests — 37 unit (`tests/test_document_service.py`) + 30 HTTP-level
  (`tests/test_document_upload.py`) — 67/67 passed**, real
  Postgres/Redis/filesystem for the HTTP-level tests, no mocks (a
  per-test `get_storage_provider` override for storage isolation, an
  explicit `raise_server_exceptions=False` client for the one test that
  deliberately provokes an unhandled exception — see "Completed work
  (Issue #3 — Slice 3.3...)" for why). **Complete backend suite:
  361/361 passing** (294 pre-existing + 67 new), **3 consecutive runs**,
  no regression in any existing test. Frontend (`npm run
  lint`/`typecheck`/`test`) re-confirmed unaffected: 48/48 vitest
  passing, lint/typecheck clean — no frontend file changed. **Docker/
  Compose verification**: `compose-backend-1` was found crash-looping
  on a stale image (see "Blockers" above); rebuilt
  (`docker compose build backend && docker compose up -d backend`), came
  up healthy, and a full manual smoke test against the real running
  stack (register → create workspace → upload a real PDF via `curl`)
  succeeded end-to-end, with the file verified on disk inside the
  container at the expected, correctly-generated path. Committed as
  `b81b7d2` (implementation) + `b3cf3cf` (docs), pushed, and opened as
  **PR #20**.
- **Pre-merge correctness review of Slice 3.3 (same PR #20)**: `uv run
  ruff check .`/`uv run mypy .` both clean (94 source files, no new
  findings) after the fix. **9 new tests, 67 → 76 — 76/76 passed**
  (46 unit in `tests/test_document_service.py` + 30 HTTP-level in
  `tests/test_document_upload.py`), real Postgres for the one
  regression test that needed it (a genuine race-lost duplicate insert
  with a deliberately broken compensating-cleanup delegate). See
  "Completed work (Issue #3 — Slice 3.3...)" → "Pre-merge correctness
  review" above for the finding. **Complete backend suite: 370/370
  passing** (361 pre-review + 9 new), **3 consecutive runs**, no
  regression in any existing test. Frontend re-confirmed unaffected
  (48/48 vitest, lint/typecheck clean). Docker Compose services
  confirmed healthy and reachable; this specific fix was validated
  through the automated suite against real Postgres, not a fresh manual
  container smoke test. Committed as `1cc760f` on the same branch.
- **Issue #3, Slice 3.6 (processing lifecycle): `uv run ruff check .`**
  (pass) and **`uv run mypy .`** (pass, 103 source files, no new
  findings). **34 new tests — 17 unit (`tests/test_cleaning.py`) + 17
  HTTP-level (`tests/test_document_lifecycle.py`) — 34/34 passed**, real
  Postgres/Redis/filesystem for the HTTP-level tests, no mocks. Six
  pre-existing tests in `tests/test_document_processing.py` were updated
  (not newly added) to assert `CHUNKED` instead of `PARSED` as the
  pipeline's terminal success state — an intended consequence of this
  slice, not a regression. **Complete backend suite: 507/507 passing**
  (473 pre-Slice-3.6 + 34 new), **3 consecutive runs**, no regression in
  any existing test. Frontend not re-run as a fresh command this
  session, but no frontend file changed — expected unaffected,
  consistent with every prior backend-only slice. Docker/Compose: not
  rebuilt this slice — no dependency and no Docker-relevant file changed
  (`git diff main -- backend/pyproject.toml backend/uv.lock` is empty),
  matching the same reasoning already recorded for Slice 3.5 in
  "Blockers" above. Since merged — PR #23, squash commit `aa68079`,
  CI 4/4 green.
- **Issue #3, Slice 3.7 (embedding + vector indexing): `uv run ruff
  check .`** (pass) and **`uv run mypy .`** (pass, 106 source files, no
  new findings). **20 new tests — 14 unit (`tests/test_embedding.py`) +
  6 new HTTP-level (`tests/test_document_lifecycle.py`), plus 3 existing
  tests extended with embedding-shape assertions — all passed**, real
  Postgres/Redis/filesystem for the HTTP-level tests, no mocks. 3
  pre-existing tests in `tests/test_document_processing.py` updated
  (not newly added) to assert `READY` instead of `CHUNKED` as the
  pipeline's terminal success state — an intended consequence of this
  slice, not a regression. Migration `0005` verified reversible
  directly against the real database (`alembic downgrade 0004` /
  `upgrade head`, columns and the HNSW index confirmed removed then
  recreated via direct schema/`pg_indexes` queries), not just assumed
  from the migration file's own correctness. **Complete backend suite:
  527/527 passing** (507 pre-Slice-3.7 + 20 new), **3 consecutive
  runs**, no regression in any existing test. Frontend not re-run as a
  fresh command this session, but no frontend file changed — expected
  unaffected, consistent with every prior backend-only slice. Docker/
  Compose: not rebuilt this slice (see "Blockers" above for why). Since
  merged — PR #24, squash commit `7241ec8`, CI 4/4 green.
- **Issue #4, Slice 4.1 (conversation/message/citation/retrieval-event
  schema): `uv run ruff check .`** (pass) and **`uv run mypy .`** (pass,
  112 source files, no new findings). **23 new tests
  (`tests/test_conversation_schema.py`) — 23/23 passed**, real Postgres,
  no mocks. Migration `0006` verified reversible directly against the
  real database (`alembic downgrade 0005` / `upgrade head`, all four
  tables confirmed removed then recreated via direct schema inspection).
  **Complete backend suite: 550/550 passing** (527 pre-Slice-4.1 + 23
  new), **3 consecutive runs**, no regression in any existing test.
  Frontend not re-run as a fresh command this session, but no frontend
  file changed — expected unaffected. Docker/Compose: not rebuilt this
  slice — no new dependency, no Docker-relevant file changed. Since
  merged — PR #25, squash commit `5e4a626`, CI 4/4 green.
- **Issue #4, Slice 4.2 (retrieval module): `uv run ruff check .`**
  (pass) and **`uv run mypy .`** (pass, 121 source files, no new
  findings). **23 new tests (`tests/test_retrieval.py`) — 23/23
  passed**, real Postgres, no mocks. Migration `0007` verified
  reversible directly against the real database (`alembic downgrade
  0006` / `upgrade head`, the GIN index confirmed removed then
  recreated via `pg_indexes`). One genuine test-design bug found and
  fixed during validation (a coincidental score tie from stopword
  overlap in a test fixture, not a retrieval-code defect — see
  "Completed work (Issue #4 — Slice 4.2...)" above for the full
  root-cause). **Complete backend suite: 573/573 passing** (550
  pre-Slice-4.2 + 23 new), **3 consecutive runs**, no regression in any
  existing test. Frontend not re-run as a fresh command this session,
  but no frontend file changed — expected unaffected. Docker/Compose:
  not rebuilt this slice — no new dependency, no Docker-relevant file
  changed. Since merged — PR #26, squash commit `378fec4`, CI 4/4 green.
- **Issue #4, Slice 4.3 (generation module + conversations endpoint):
  `uv run ruff check .`** (pass) and **`uv run mypy .`** (pass, 133
  source files, no new findings). **25 new tests — 13 unit
  (`tests/test_generation.py`) + 12 HTTP-level
  (`tests/test_conversations.py`) — all passed**, real
  Postgres/Redis/filesystem for the HTTP-level tests, no mocks; the
  HTTP-level tests exercise the complete Issue #3 ingestion pipeline
  (upload -> process -> `READY`) before asking a real question against
  the ingested content. No test-design bugs this time — all 25 passed
  on first execution. App startup and route registration verified
  directly via `app.openapi()`'s schema (see "Completed work" above for
  why raw `app.routes` introspection was misleading in this FastAPI/
  Starlette version). **Complete backend suite: 598/598 passing** (573
  pre-Slice-4.3 + 25 new), **3 consecutive runs**, no regression in any
  existing test. Frontend not re-run as a fresh command this session,
  but no frontend file changed — expected unaffected. Docker/Compose:
  not rebuilt this slice — no new dependency, no new migration, no
  Docker-relevant file changed. Not yet committed, pushed, or opened as
  a PR — see "Exact next recommended action" below.

## Exact next recommended action

Redis Slices 1/2/3a/3b/3c, Playwright E2E, all of Issue #3 (Slices
3.1–3.7, including Slice 3.2's and Slice 3.4's own correctness-review
fixes, and Slice 3.5's own two-round final review), and Issue #4 Slices
4.1–4.2 are all merged into `main` (`46ef03b` PR #11, `5391a78` PR #12,
`026dcf3` PR #13, `42529e3` PR #14, `75dd466` PR #15, `e1c4858` PR #16,
`79d4787` PR #17, `941c1a7` PR #18, `5e6fdc2` PR #19, `a6762e2` PR #20,
`2961b62` PR #21, `237be97` PR #22, `aa68079` PR #23, `7241ec8` PR #24,
`5e4a626` PR #25, `378fec4` PR #26) — nothing pending for any of them.
`main`/`origin/main` are at `378fec4`. **GitHub Issue #4, Slice 4.3
(generation module + conversations endpoint) is implemented and fully
tested**, on branch `issue-4-slice-4-3-generation` (cut from `378fec4`)
— not yet committed, pushed, or opened as a PR. See "Completed work
(Issue #4 — Slice 4.3...)" above. The next work, in order:

1. **Commit Slice 4.3** on the current branch, push it, and open a PR
   against `main`. This slice's own real-stack validation (25 new
   focused tests, full 598-test suite × 3 runs, `ruff`/`mypy` clean) is
   already done locally. Get CI green, then **merge it promptly** — the
   5-day timeline authorizes this without waiting for a separate
   per-PR instruction (see "Current task"/"Next major task" above).
2. **Immediately after merging, with no further go-ahead needed:**
   switch to `main`, pull, confirm a clean tree, then continue Issue #4
   with the two deliberately-deferred deliverables (evaluation hooks,
   a broader prompt-injection test corpus) — see "Next major task"
   above for the concrete starting points. Once those land, Issue #4's
   explicit deliverables/Definition-of-Done are complete; move to
   Issue #5 (product experience) per the 5-day plan's Day 3 scope.
