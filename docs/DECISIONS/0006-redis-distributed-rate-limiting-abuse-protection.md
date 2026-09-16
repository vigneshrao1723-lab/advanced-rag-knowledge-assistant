# 0006. Redis-backed distributed rate limiting + deterministic abuse protection

**Status:** Accepted (design approved; implementation in progress —
Slice 1 (Redis engine + supporting infrastructure) is implemented and
**committed** (`b1f1b00`, not yet pushed/merged); Slice 2 (wiring that
engine into every `enforce_*_rate_limit` dependency) is implemented but
**uncommitted, working-tree-only**; the deterministic abuse layer §11/§12
is not started in either form; see "Implementation status" at the end of
this document and `HANDOFF.md`)
**Date:** 2026-09-14

## 1. Context

[ADR 0001](0001-modular-monolith-over-microservices.md) excludes Redis and
other premature infrastructure "unless a documented, measured requirement
justifies them via a new ADR." `docs/SECURITY.md` §"Rate limiting
approach" already anticipated this moment: "if horizontal scaling later
makes in-process/PostgreSQL-backed limiting inadequate, that is revisited
through a new ADR backed by measured evidence, not decided in advance."

**Honest framing, after adversarial review of this ADR's first draft:**
this project has no production deployment, no measured multi-instance
traffic, and no incident history. Calling horizontal scale-out a
"measured requirement" in the first draft of this ADR overstated the
evidence — there is no telemetry, load test, or production incident to
point to, and this document does not pretend otherwise.

What *is* true, and does not require fabricating measurements to justify:
the current in-process limiter's single-process assumption is a
verified, deterministic architectural fact (§2), not a hypothesis, and
running more than one backend process — for ordinary reasons like
zero-downtime deploys or basic availability, not necessarily high load —
is a normal, expected shape for any deployment of this kind of system.
Redis is introduced here for two honestly-stated reasons, neither of
which claims production evidence that doesn't exist:

1. **Architectural preparedness.** The moment this backend ever runs as
   more than one process, the current limiter silently stops enforcing
   its configured limits (§2.1) — a correctness gap worth designing away
   *before* it's hit, per `AGENTS.md` §1's "documented ADR first, not a
   silent architectural drift," rather than as a response to an incident.
2. **This is the explicitly commissioned next engineering phase** for
   this project (an organizational/roadmap decision, stated here as
   exactly that — a decision to do this design work now, not an
   independent technical proof that the project has outgrown in-process
   limiting under real load).

This ADR treats architectural certainty about an ordinary future
deployment shape as sufficient justification for a *design* — distinct
from, and a lower bar than, the empirical "measured evidence" ADR 0001
and `docs/SECURITY.md` describe for justifying *production* adoption.
Implementation and actual production use of this design should still be
weighed against real evidence as it accumulates (see "Implementation
status").

This document is a **design ADR** — it records and justifies the
architecture, not the fact of its implementation. Per the task that
produced it, this document itself added no Redis code, dependency, or
Docker service; implementation is tracked separately, one reviewed slice
at a time, in `HANDOFF.md` — see "Implementation status" for exactly
which parts of this design exist in the repository as of the most recent
slice.

## 2. Problem

`backend/app/core/rate_limit.py`'s `FixedWindowRateLimiter` stores hit
timestamps in an in-process Python `dict` (`defaultdict(list)`). This has
two independent problems, verified directly from the code (`git show
ec4225d:backend/app/core/rate_limit.py`) and its tests
(`backend/tests/test_rate_limit.py`), not assumed:

1. **No cross-instance coordination.** Each backend process has its own
   dict. Two instances behind a load balancer each independently allow up
   to `limit` requests in a window, so the *effective* limit scales with
   instance count — an attacker distributing requests across instances (or
   simply hitting different instances via normal load-balancer round-robin)
   sees a multiple of the intended limit. This is a deterministic
   consequence of the code as written (§1) — it does not require
   attack traffic or production load to demonstrate, only more than one
   process; it has not been observed in production because no production
   multi-instance deployment of this project exists.
2. **Fixed-window boundary doubling.** `FixedWindowRateLimiter.check`
   evicts hits older than `window_seconds` from a list and counts what
   remains — a standard fixed-window counter. This allows up to `2 ×
   limit` requests within a short span straddling a window boundary (e.g.,
   `limit` requests at `t=59.9s` and another `limit` at `t=60.1s`, inside
   one real 60-second span, since the two batches fall in different fixed
   windows). This is a known, general property of fixed-window counters,
   not something introduced by this implementation — noted here because
   the Redis replacement should not reintroduce it if a better-bounded
   algorithm is equally simple to implement atomically (see §8).

Neither problem is a defect in how the code was written — the module's
own docstring already documents the single-process assumption as
deliberate. This ADR addresses both by design, once Redis is justified.

## 3. Goals

- Rate limiting that is correct and coordinated across any number of
  backend instances sharing one Redis.
- A bounded, deterministic abuse/risk layer that can escalate response to
  patterns a single-request rate limit cannot see (e.g., credential
  stuffing spread across many IPs against one account).
- An explicit, operation-aware Redis failure policy — no uncontrolled
  exceptions, no silently-disabled protection on security-sensitive
  endpoints, no self-inflicted denial of service on non-critical ones.
- Preserve everything the current limiter already gets right: per-endpoint
  isolation, IP-keyed limiting, fast in-memory-speed checks, no DB
  round-trip on the hot path.
- A design that a future, more sophisticated risk model (still not
  ML/statistical unless separately evaluated and decided) can extend
  without a rewrite.

## 4. Non-goals

- **Not** replacing PostgreSQL as the durable, authoritative datastore for
  users, sessions, workspaces, authorization, or audit logs. Redis holds
  only ephemeral rate-limit and abuse state (§7).
- **Not** an ML/statistical risk model. Every decision in this design is a
  deterministic rule evaluated against counters — see §11 for why, and
  the extension point that keeps a future model possible without
  retrofitting.
- **Not** implementing anything as part of *this document*. This ADR
  itself adds no Redis dependency, Docker service, or application code —
  those were added, once design review was complete, by a separate,
  reviewed implementation task (tracked in `HANDOFF.md`, currently at
  "slice 1" — see "Implementation status" for exactly what exists and
  what doesn't).
- **Not** rate-limiting every current or future endpoint uniformly. This
  design covers the five endpoints the current limiter already protects
  (`register`, `login`, `refresh`, `forgot-password`, `reset-password`);
  extending it to future expensive operations (uploads, embeddings, LLM
  calls — `docs/SECURITY.md` principle 8) is a decision for those
  features' own implementation, using this same mechanism.
- **Not** designing a general-purpose queueing or backpressure system.
  Exhausted capacity is rejected (`429`) or temporarily blocked, never
  queued — see §12.

## 5. Existing system (verified from code, not assumed)

| Property | Current behavior | Evidence |
|---|---|---|
| Storage | In-process Python `dict` (`defaultdict(list)`), one per `FixedWindowRateLimiter` instance | `backend/app/core/rate_limit.py` |
| Algorithm | Fixed window: evict hits older than `window_seconds`, count remainder, reject if `>= limit` | Same file, `.check()` |
| Burst behavior | Up to `2×` the configured limit possible across a window boundary (§2.2) | Inherent to the algorithm; not separately tested |
| Dimensions supported | One: a single string key. In practice, always `client_ip` (`request.client.host`, `"unknown"` if absent) | `client_ip()` and every `enforce_*_rate_limit` function |
| Per-user/session/workspace limiting | **Not supported.** No limiter is keyed by anything but IP. | Same |
| Endpoint scoping | Five separate limiter instances (`login`, `register`, `refresh`, `forgot_password`, `reset_password`), each with its own limit/window, so a burst on one doesn't lock out another | Module-level instantiations |
| Concurrency behavior | A single process's dict access from `async def` FastAPI handlers is effectively serialized per request (no `await` inside `.check()`), so no in-process race exists today | Code inspection — `.check()` has no `await` |
| Multi-instance behavior | **Broken as designed** — each instance has an independent dict; no coordination. See §2.1. | Architectural, not a test result |
| Process-restart behavior | All counters reset to empty on restart — a restart is a free reset for every client | In-memory-only storage |
| Configuration | Hardcoded `limit`/`window_seconds` per limiter at module load; no environment variable controls any of them | Module-level constants |
| Failure behavior | None to speak of — there is no external dependency that can fail; `.check()` either returns or raises `HTTPException(429)` | Same |
| Test coverage | 4 unit tests (`tests/test_rate_limit.py`): under-limit, over-limit, per-key independence, window-expiry-resets. Plus integration tests in `tests/test_auth.py`/`tests/test_password_reset.py` that drive real endpoints past their limits and assert `429`. **No concurrency test, no multi-instance test, no boundary-doubling test exist.** | Test files |
| Security limitations | IP-only keying means a botnet (many IPs, one target account) is invisible to this limiter — each IP gets its own quota; **addressed by §9's account/session dimensions and §11's R3.** Also, `client_ip()` trusts `request.client.host` directly with no reverse-proxy/`X-Forwarded-For` handling — behind a reverse proxy (the ordinary production shape), every request could resolve to the proxy's own IP, collapsing all clients into one shared bucket. This is a real, verified gap (there is no `X-Forwarded-For` handling anywhere in the codebase — confirmed by `grep -r "X-Forwarded-For\|x_forwarded_for" backend/`, zero results); **designed in §9a**, not left as a stated-but-unsolved gap. | `client_ip()`; grep confirms no proxy-header handling exists |
| Reserved-but-unused observability hook | `AuditEvent.RATE_LIMITED` (`app/core/audit.py`) is already defined as a constant but is **never emitted anywhere** — confirmed via repository-wide grep. A rate-limit rejection today produces no audit trail at all, only the `429` response itself (and whatever the standard access log captures). | `grep -rn RATE_LIMITED backend/` |

## 6. Chosen architecture

Evolve, not replace. `backend/app/core/rate_limit.py`'s public shape
(`enforce_*_rate_limit(request) -> None`, raising `HTTPException(429)`)
stays the integration point every route already depends on
(`app/api/v1/auth.py`'s `Depends(enforce_*_rate_limit)`). Underneath that
same interface:

- A new Redis-backed limiter becomes the primary implementation once
  Redis is available and healthy — evaluating **all** of an operation's
  dimensions (§9) as one atomic, all-or-nothing decision (§8, §10), not
  one independent check per dimension.
- The existing `FixedWindowRateLimiter` becomes the **fallback**
  implementation used when Redis is not available, for the endpoints
  where a fail-open response would be unacceptable (§13's operation-aware
  policy) — not deleted, not dead code.
- A new, separate deterministic abuse/risk layer (§11) sits alongside the
  rate limiter, consulted by the same `enforce_*` dependencies, and is
  the only component allowed to escalate a request past ordinary
  throttling into a temporary block (§12).
- A new client-IP resolution function (§9a) replaces `client_ip()`
  everywhere it's used today, applying the trusted-proxy model before
  any dimension in this design ever sees an IP address.

```
enforce_login_rate_limit(request)
  ├─ resolve_client_ip(request)                    — §9a: trusted-proxy-aware, never trusts a bare header
  ├─ AbuseDecisionEngine.check(dimensions)          — is any of this request's dimensions currently blocked?
  │    └─ blocked  → 429 (TEMPORARY_BLOCK; audited)  [a read-only check — no state is consumed here]
  ├─ RedisRateLimiter.check_all(operation, keys=[ip_key, acct_key])
  │    │    — ONE Lua invocation over every dimension key this operation has (§8, §10):
  │    │      all pass → all consumed, allowed; any fails → none consumed, rejected.
  │    │      This is deliberately not "check(ip_key)" then separately "check(acct_key)" —
  │    │      see §10 for the partial-consumption race that shape allows.
  │    └─ Redis unavailable/timeout → fall back to FixedWindowRateLimiter (§13)
  └─ AbuseDecisionEngine.record(outcome)            — feed the rule engine (async-safe, non-blocking to the caller's response)
```

## 7. Redis responsibilities (and explicit non-responsibilities)

**Deployment boundary, stated explicitly: this design targets a single
Redis instance (or a primary-replica pair for availability), not a Redis
Cluster.** Nothing in this ADR requires, assumes, or has been evaluated
against a sharded/clustered Redis deployment. This matters concretely for
§10's multi-key atomicity: `EVAL` across multiple keys is unconditionally
safe on a single (or primary-replica, non-sharded) Redis, because there
is no key-slot partitioning to worry about — every key lives on the one
node the script runs against. §10 separately documents what would change
*if* a cluster were introduced later (hash-tagging keys so they land on
the same slot), but that is future-facing, explicitly not a claim that
this design is cluster-compatible today, and not a decision this ADR
makes now. If Redis Cluster is ever adopted, it needs its own
implementation-time verification (and likely its own ADR addendum), not
an assumption carried over silently from this document.

Redis holds **only**:

- Rate-limit bucket state (§8): current token count / window position per
  key, always TTL-bound.
- Abuse/risk counters and temporary-block flags (§11–§12), always
  TTL-bound.

Redis does **not** hold, and this design must not grow to hold:

- Users, sessions, workspaces, membership, or any of PostgreSQL's existing
  entities (ADR 0002 stands unchanged).
- Audit logs — those remain exclusively in `audit_logs`
  (PostgreSQL), which is the durable, queryable historical record. Redis
  counters are ephemeral inputs *to* audit decisions (§14), never a
  replacement for the record itself.
- Anything needed to reconstruct application state after Redis data loss.
  Losing all Redis rate-limit/abuse state at any moment must be equivalent
  to every client's limiter resetting to empty — annoying at worst
  (temporary loss of accumulated throttling/blocks), never a correctness
  or security-invariant violation, since PostgreSQL-backed authorization
  and the fallback in-process limiter (§13) remain intact regardless.

## 8. Rate-limiting algorithm

**Chosen: token bucket, evaluated atomically per *operation* (over every
dimension key that operation has — one key for a single-dimension
operation, several keys together for a multi-dimension one) via a single
Redis Lua script (`EVAL`) invocation.** (Corrected from an earlier
per-*key* framing during adversarial review — see the worked race in
§10 for exactly why per-key atomicity alone is insufficient for a
multi-dimension operation.)

Rationale:

- Fixes the fixed-window boundary-doubling problem identified in §5 —
  token bucket enforces a true rolling rate rather than counting within
  discrete windows.
- Naturally expresses "burst up to capacity, then a steady refill rate,"
  which is a strict superset of what the current fixed-window limiter
  provides (a fixed window is a degenerate token bucket that refills all
  at once at the window boundary).
- A single Lua script makes the whole read-check-write sequence atomic
  server-side inside Redis (§10) — no separate `GET`/`SET` round trip that
  could race under concurrent requests from multiple backend instances.

Per-key state (a Redis hash): `tokens` (float, tokens currently available)
and `last_refill_at` (float, Unix timestamp of the last time the script
ran for this key).

**Single-dimension operations (`register`, `reset-password` — §9 has only
one dimension for each):** one key, one script invocation, exactly as
below.

**Multi-dimension operations (`login`, `refresh`, `forgot-password` — §9
lists two dimensions for each):** this ADR's first draft ran one
independent script invocation *per dimension key* and treated "each
key's own check is atomic" as sufficient for the combined policy. **That
was wrong and is corrected here** — see the worked race condition in
§10. The corrected design runs **one Lua script invocation per
operation, parameterized over all of that operation's dimension keys
together** (Redis's `EVAL script numkeys key1 key2 ... arg1 arg2 ...`
natively supports multiple keys in one atomic invocation). For an
operation with dimension keys `K_1..K_n`:

1. For each `K_i`, read `tokens_i`/`last_refill_i` (defaulting to a full
   bucket if absent — a first request is never penalized for a Redis
   restart or key expiry), and compute the refilled
   `tokens_i' = min(capacity_i, tokens_i + elapsed_i × refill_rate_i)`.
2. Check, **for every `i`**, whether `tokens_i' >= cost_i` (§9). If **any**
   dimension fails this check, the script returns "rejected" and **writes
   nothing at all** — no dimension's bucket is touched, and no
   previously-nonexistent key is created (§10 explains why this matters
   for both correctness and cardinality; see also §18).
3. Only if **every** dimension passes does the script write
   `tokens_i' - cost_i` back to every `K_i` (refreshing each one's TTL,
   §10) and return "allowed."

This is an all-or-nothing decision across every dimension of one
operation, computed inside Redis in a single round trip, with no
partial side effects on a rejected request.

**Continuity with today's numbers:** `capacity` and `refill_rate` are
derived directly from the existing, already-justified `(limit,
window_seconds)` pairs — `capacity = limit`, `refill_rate = limit /
window_seconds` — so no new arbitrary numbers are introduced by adopting
this algorithm. Only the algorithm changes (fixed-window → token bucket);
the effective steady-state rate per endpoint is unchanged from what's
already running in this codebase today (no production deployment of
either version exists yet — see §1).

## 9. Hierarchical dimensions and operation/cost model

Not every dimension applies to every operation — each is chosen because a
specific, articulable attack pattern needs it, per the task's explicit
instruction not to add dimensions uniformly:

| Operation | Dimensions checked (independently — each must pass) | Why |
|---|---|---|
| `register` | IP | No account exists yet to key on; nothing else is available pre-registration. |
| `login` | IP, and submitted email (keyed HMAC, not plain hash — §14) | IP alone misses credential stuffing spread across many IPs at one target account; email alone misses a single IP spraying many accounts. Checking both independently catches either pattern without needing a compound key. |
| `refresh` | Session ID, and IP | The caller is already authenticated (has a session); session-scoped limiting stops a single stolen/misbehaving refresh token from being hammered, while IP still catches rapid replay from unexpected/many locations. |
| `forgot-password` | IP, and submitted email (keyed HMAC) | Same reasoning as `login` — prevents both IP-based spam and targeted harassment of one account's inbox, without the response ever confirming which dimension tripped (enumeration resistance is unaffected by rate-limit dimensioning — see ADR-independent `docs/SECURITY.md` coverage). |
| `reset-password` | IP only | The token itself is the real defense (256-bit entropy, single-use, expiring — `docs/SECURITY.md`). Dimensioning by token would require hashing a client-supplied token before it's validated, adding complexity for a scenario the entropy already makes infeasible; dimensioning by account isn't possible pre-validation without leaking whether a token maps to a real account. IP-only matches today's behavior. |

Workspace and endpoint-generic dimensions (for future expensive
operations — uploads, embeddings, LLM calls) are **explicitly out of
scope for this ADR** (see §4) — they get designed when those features are
built, using the same underlying mechanism.

### 9a. IP resolution: trusted-proxy model (required before any IP
dimension is meaningful in production)

§5 already identified that `client_ip()` trusts `request.client.host`
(the raw TCP peer) directly, with no `X-Forwarded-For` handling at all —
correct for a direct connection, but behind any reverse proxy or load
balancer (the ordinary production shape), `request.client.host` becomes
the *proxy's* address for every request, collapsing every real client
into one shared bucket. Naively "fixing" this by trusting
`X-Forwarded-For` unconditionally would be strictly worse: any client can
set that header to an arbitrary value on a direct request
(`X-Forwarded-For: 1.2.3.4`), letting an attacker choose their own
rate-limit key and evade every IP-keyed check in this design. **This ADR
does not design blind trust of that header.** The explicit model:

- **A new setting, `TRUSTED_PROXY_CIDRS`** (comma-separated CIDR ranges,
  following the existing `.env.example` convention of typed, explicit
  configuration with no hidden default behavior). **Default: empty.**
- **Default behavior (empty `TRUSTED_PROXY_CIDRS` — matches today's
  code exactly):** `X-Forwarded-For` and `Forwarded` are **ignored
  unconditionally**; the resolved client IP is always
  `request.client.host`, the real TCP peer, whatever it is. This is the
  correct behavior both for a direct client (there is no proxy to trust)
  and for an operator who has not yet configured a trusted proxy — never
  silently trusting a client-supplied header is the safe default,
  consistent with this project's existing pattern of secure-by-default
  settings that require explicit opt-in to change (`COOKIE_SECURE`,
  `COOKIE_SAMESITE`).
- **Configured behavior (`TRUSTED_PROXY_CIDRS` non-empty):** resolve the
  client IP by walking `X-Forwarded-For` **from the right** (the entry
  closest to this server), not the left (the entry a client fully
  controls): if `request.client.host` (the immediate TCP peer) falls
  inside a configured trusted CIDR, take the last entry in
  `X-Forwarded-For`; if *that* value is *also* inside a trusted CIDR
  (a chain of trusted proxies, e.g. a CDN in front of an internal load
  balancer), continue walking left. The first entry encountered that is
  **not** inside a trusted CIDR is the resolved client IP. If
  `request.client.host` itself is *not* inside a trusted CIDR — someone
  connected directly, bypassing the expected proxy, whether by
  misconfiguration or a deliberate attempt to skip it —
  `X-Forwarded-For` is ignored and `request.client.host` is used as-is,
  exactly like the empty-configuration case. Walking from the right (not
  blindly taking the header's first/leftmost entry) is what specifically
  prevents the spoofing case above: a client-supplied prefix on the
  header is irrelevant once the resolution only trusts entries that a
  *configured* trusted proxy itself appended.
- **Production requirement:** any deployment placing this backend behind
  a reverse proxy or load balancer **must** set `TRUSTED_PROXY_CIDRS` to
  that proxy's actual address range (e.g., the hosting provider's load
  balancer subnet, or `127.0.0.1/32`/`::1/128` for a same-host reverse
  proxy) — otherwise every request's IP dimension silently collapses to
  the proxy's own address, exactly as it does today. This is a
  **documented deployment requirement**, not a default the application
  can safely infer.
- **What this ADR does not decide (correctly left open, §22):** the exact
  CIDR values for any real deployment — unknowable until a hosting
  target is chosen, and not something to invent here — and whether the
  hop-walk should be bounded by a configured maximum hop count in
  addition to the CIDR check (a defensive limit against a pathologically
  long forged header chain causing excess parsing work). Neither
  decision is implementation-blocking; both should be resolved when a
  real deployment target exists.

This model applies to **every** IP-keyed dimension in this design (the
`login`/`forgot-password`/`reset-password` IP buckets, the `refresh` IP
check, and every IP-keyed abuse signal in §11) — there is exactly one IP
resolution function, used everywhere `client_ip()` is used today.

**Operation/cost model:** every check in the table above uses **cost =
1** per request. The task explicitly warns against inventing arbitrary
per-operation cost weights, and nothing in this repository provides
evidence (measured request cost, abuse incident, or load data) to justify
weighting one operation's requests as "more expensive" than another's in
token terms — today's `(limit, window)` pairs already encode the intended
relative strictness per endpoint (e.g., `refresh` at 20/min vs. `login`
at 5/min), which cost=1 preserves exactly. **Open decision:** if a future
operation has a measurably different resource cost (e.g., an LLM call
costing meaningfully more compute than a login attempt), that operation's
bucket should use a correspondingly larger `cost` per request — this ADR
establishes the mechanism (the Lua script already parameterizes `cost`)
without inventing a number for a case that doesn't exist in this
repository yet.

## 10. Atomicity / concurrency strategy

**The atomicity guarantee, stated precisely:** for any single operation
(`register`, `login`, `refresh`, `forgot-password`, `reset-password`),
the entire decision — reading and refilling every one of that
operation's dimension buckets (§9), checking all of them, and writing
back only if all of them pass — executes as **one indivisible unit
inside Redis**, whether that operation has one dimension or several. No
other command, from any client or backend instance, can observe or
mutate any of that operation's keys partway through this sequence. This
holds regardless of how many backend instances exist and regardless of
how many *other* operations' checks are happening concurrently against
*different* keys.

**This is check-before-write, not write-then-rollback — the distinction
matters and is deliberate.** §8's algorithm never writes a dimension's
bucket and then reverts it if a later dimension fails; it evaluates
*every* dimension's refilled token count first (a pure read/compute pass
against values already fetched into the script, mutating nothing in
Redis), and only after every dimension has been confirmed to pass does
it issue the writes, for every dimension, together, in the same script
invocation. There is no intermediate state a rollback would ever need to
undo, and no window in which a partial write is visible to any other
caller — Redis's single-threaded Lua execution (below) means nothing
outside the script can observe the buckets between the check phase and
the write phase because there is no externally-observable gap between
them at all. Rollback is a strategy for undoing a write that already
happened and was already visible; this design instead never performs a
write until it is already known to be correct, which is a stronger and
simpler guarantee than rollback would provide.

**Why per-key atomicity alone is not the same claim, and the race it
misses (found in adversarial review of this ADR's first draft):** the
first draft ran one independent Lua script per dimension key and reasoned
that "each key's script is atomic" was sufficient. It is not, for a
*compound* decision spanning multiple keys. Concrete case: `login` checks
an IP bucket and an account bucket independently. Two sequential requests
for the *same account* from *different* IPs (`ip1`, `ip2`), where the
account bucket has exactly one token left:

1. Request A: `EVAL` on the `ip1` bucket → passes, consumes an `ip1`
   token.
2. Request A: `EVAL` on the account bucket → passes (last token),
   consumes it.
3. Request B: `EVAL` on the `ip2` bucket → passes, consumes an `ip2`
   token.
4. Request B: `EVAL` on the account bucket → **fails** (now empty) →
   request B is rejected.

Request B's `ip2` bucket already had a token consumed *before* the
account-level check failed — a real token was spent on a request that
was never going to succeed. This is not a data race in the sense of two
writers corrupting one key (each individual key's script *is* correctly
serialized); it is a **partial-consumption problem**: a compound
allow/deny decision was split into separately-atomic pieces, so a
rejection on one dimension doesn't undo consumption already committed on
another. Concretely, this lets a "sacrificial" account (one already near
its own limit, or targeted by an attacker to become so) be used to drain
a *shared* IP's bucket — for example, many unrelated users behind one
NAT/corporate egress IP could be penalized by requests that were always
going to fail the account check, not the IP check. The same shape of
problem applies to `refresh` (session + IP) and `forgot-password` (IP +
account).

**Fix:** the multi-key Lua design in §8 — one script invocation per
operation, over all of that operation's keys — closes this exactly: step
2 of §8's algorithm checks every dimension's refilled token count
*before* step 3 writes anything, and nothing is written unless every
dimension passes. Request B in the scenario above would never have its
`ip2` bucket touched at all, because the single invocation would have
seen the account bucket was already exhausted (evaluated in the same
pass) and rejected without writing either key.

- **Mechanism:** the whole multi-key sequence runs inside one Lua script
  via `EVAL`/`EVALSHA`. Redis executes Lua scripts single-threadedly to
  completion — no other command (from any client, any backend instance)
  can interleave partway through, for *any* of the keys the script
  touches. This is the standard, well-established way to avoid both the
  naive single-key `GET → calculate → SET` race the task explicitly warns
  against, and the multi-key partial-consumption race identified above.
- **Concurrency across instances:** because all backend instances share
  one Redis and each operation's full multi-dimension check is atomic, N
  instances checking the same operation/identity concurrently is exactly
  equivalent to one instance checking it N times in some order — the
  property that was missing entirely from the in-process design (§5).
- **Redis Cluster note (not applicable today — §7 states the deployment
  boundary explicitly; this note only exists so the constraint isn't
  rediscovered as a production incident if that boundary is ever
  revisited):** a single Lua script touching multiple keys requires all
  of those keys to hash to the same cluster slot on a sharded/clustered
  Redis — a non-issue on the single-instance (or primary-replica)
  deployment this ADR targets, since every key lives on the one node the
  script runs against regardless. If Redis Cluster is ever adopted later,
  each operation's keys should share a hash tag (e.g. `rl:{login}:ip:...`
  and `rl:{login}:acct:...`, both tagged `{login}`) so Redis routes them
  to the same slot — not a decision this ADR makes now, and not a claim
  that this design has been evaluated against a cluster.
- **TTL behavior:** each bucket key gets `EXPIRE` set (inside the same
  Lua script, so it's part of the same atomic operation) to a value
  comfortably longer than the time to fully refill from empty (e.g.,
  `capacity / refill_rate × safety_factor`) — an idle key disappears on
  its own rather than persisting indefinitely, bounding Redis memory
  growth regardless of how many distinct IPs/accounts have ever been
  seen. Combined with "nothing is written on rejection" above, this also
  means a request that was always going to be rejected never creates a
  *new* key for a dimension that didn't already have one (§18's
  cardinality analysis relies on this).
- **Cleanup:** no separate cleanup job is needed — TTL expiry is Redis's
  own mechanism; there is nothing this application must sweep.
- **Clock/time handling:** the Lua script uses Redis's own `TIME` command
  (available inside scripts) rather than a timestamp passed in from the
  application, so all elapsed-time math is computed from one consistent
  clock (Redis's) regardless of clock skew between backend instances —
  this avoids a class of bugs where two instances' local clocks disagree
  about how many tokens should have refilled.
- **Failure scenarios:** covered in §13 (this section is about
  correctness when Redis *is* available; §13 covers what happens when it
  isn't).

## 11. Deterministic abuse detection model

**Explicitly a rules engine, not AI/ML** — every decision here is an
`if`-level check against counters, auditable and explainable by reading
the rule, not a trained model or statistical score.

**Why a rule table instead of a numeric risk score:** the task warns
against inventing an arbitrary scoring system. A numeric score
(e.g., "risk = 0.3×failed_logins + 0.5×distinct_ips + ...") would require
justifying relative weights this repository has no evidence for, and
would be harder to audit ("why was this blocked? the score was 0.73") than
an ordered list of named rules ("why was this blocked? Rule B: 6 failed
logins for this account in 10 minutes"). This design chooses the
rule-table approach specifically for that auditability, consistent with
`docs/SECURITY.md`'s existing emphasis on non-generic, explicit error
handling and honest observability.

**Signals available today** (verified against what the system already
records, not invented):

- `LOGIN_FAILED` audit events (already recorded, per-user via
  `auth_service.py`) — the abuse layer additionally needs a fast,
  ephemeral *counter* per dimension (Postgres is not queried on this hot
  path; see §7).
- Rate-limit exhaustion itself (a `THROTTLE`/`STRICT_THROTTLE` decision,
  §12) is itself a signal the abuse layer can count.
- `PASSWORD_RESET_REQUESTED` frequency (already an audit event).
- Reset-password validation failures (`reset_token_invalid` /
  `reset_token_expired` / `reset_token_already_used` — already
  distinguished error codes in `password_reset_service.py`), counted per
  IP.
- Distinct-IP-count per account within a window, for the specific
  "coordinated abuse" pattern named in the task (credential stuffing
  spread across many source IPs at one target account). **Corrected from
  a plain Redis `SET` to a HyperLogLog (`PFADD`/`PFCOUNT`) in this
  revision** — see the dedicated analysis below; this is a firm choice
  for this signal, not an implementation-time option.

**Distinct-IP structure: why HyperLogLog, not a `SET` (correction from
adversarial review of this ADR's first draft):** the first draft proposed
a plain `SET` of IPs "with an upgrade to HyperLogLog if cardinality
becomes large enough to matter," treating this as an open, defer-until-
needed choice. That default was backwards for this specific signal.
Every other Redis structure in this design (§18's cardinality table) is
populated by request traffic that is itself already rate-limited — an
attacker pays a real cost (an actual network request, itself throttled)
per unit of state they cause to exist. A `SET` of distinct IPs has the
same property in terms of *request cost*, but not in terms of *memory*:
an attacker who genuinely controls (or rents, e.g. via a residential
proxy network) a very large number of source IPs — which is precisely
the "coordinated abuse" scenario R3 exists to detect — can cause this
one `SET` to grow to hundreds of thousands or millions of members, each
consuming real memory, *specifically by exercising the attack this
signal is designed to catch*. That is a bad amplification property for a
structure whose only purpose is answering "is the distinct count above
threshold `M`?" — a question that does not require storing the exact
membership at all. A HyperLogLog answers exactly that question with
~12KB of fixed memory *regardless of true cardinality* (bounded by
construction, not by attacker behavior) and a small, well-characterized
approximation error (~0.81% standard error) — entirely acceptable for a
threshold comparison, unlike a case that needed the exact members or an
exact count. This closes the one place in the original design where an
attacker's own attack traffic could cheaply inflate memory beyond what a
fixed-size structure would need.

**Proposed rule table** (an explicit, ordered list — first matching rule
applies; **thresholds below are proposed defaults, not measured facts** —
see "Open decisions"):

| Rule | Condition | Dimension blocked | Resulting state |
|---|---|---|---|
| R1 | ≥ N login failures for one **IP** within window W | that IP, `login` | `STRICT_THROTTLE` |
| R2 | ≥ N login failures for one **account** (by keyed-HMAC email) within window W, regardless of source IP | that account, `login` | `STRICT_THROTTLE` |
| R3 | Distinct source IPs for one account's login failures within window W exceeds M | that account, `login` | `TEMPORARY_BLOCK` (coordinated-abuse signal) |
| R4 | ≥ N forgot-password requests for one IP within window W | that IP, `forgot-password` | `STRICT_THROTTLE` |
| R5 | ≥ N reset-password validation failures for one IP within window W | that IP, `reset-password` | `TEMPORARY_BLOCK` |

**R2's severity was downgraded from `TEMPORARY_BLOCK` to
`STRICT_THROTTLE` (correction from adversarial review of this ADR's
first draft) — this is the most important behavioral change in this
revision.** The first draft made R2 a hard block: enough login failures
against one account, from *any* source, temporarily blocks that
account's logins entirely. Adversarial analysis of §7 ("do not
over-block legitimate users," and analyzing bypass by identity dimension)
surfaces a real problem this creates: an account-scoped hard block can be
triggered by *anyone who merely knows the victim's email address* —
which is not a secret, and is the whole point of `login` needing an
email in the first place. An attacker who wants to deny a specific,
known victim access to their own account does not need to guess their
password or coordinate multiple IPs; they only need to submit enough
wrong passwords against that one known email, from one machine, to trip
R2 — turning the abuse-protection layer itself into a targeted
denial-of-service tool against a chosen victim. This is a recognized,
general trade-off with account-lockout-style defenses, not something
specific to this design, but the first draft did not account for it.
**Fix:** R2 (single-source-shape failures against one account) now only
tightens that account's own rate limit (`STRICT_THROTTLE` — the account
can still eventually log in, just more slowly, so a legitimate but
error-prone user is inconvenienced, not locked out, and an attacker
gains little by triggering it against a victim), while **R3 remains the
sole trigger for a hard account-level `TEMPORARY_BLOCK`**, because R3's
condition (many *distinct* source IPs failing against one account) is
categorically harder for a casual attacker to cheaply fabricate against
a victim they merely know the email of — it requires genuinely
distributed infrastructure, which is a much stronger signal that the
account is under real coordinated attack rather than being targeted for
denial-of-service via the abuse layer itself. R1/R4/R5 keep their
original IP-scoped severities (§7's dimension-bypass analysis found no
equivalent victim-targeting problem for IP-scoped rules, since an
attacker cannot choose to "be" another user's IP to block them).

**Extension point for a future, more advanced model:** the rule table is
evaluated behind a small interface (conceptually, `AbuseDecisionEngine`:
`record(event) -> None` and `decide(dimensions) -> DecisionState`). A
future replacement (still requiring its own ADR and evaluation evidence
before being called anything other than deterministic rules) implements
the same interface; nothing in the rate-limiter or route layer needs to
change to swap it in.

**Open decisions (explicitly not invented here):** the exact values of
`N`, `M`, `W` per rule. This repository has no incident history, load
data, or measured false-positive rate to derive them from. Reasonable
starting points would scale off the existing, already-justified base
rates (e.g., "R1's threshold is some small multiple of the base `login`
limit observed within a longer window"), but committing to specific
numbers here would be exactly the kind of unjustified invention the task
warns against — they must be set (and documented, with rationale) at
implementation time, ideally starting conservative and tightened or
loosened based on real observed traffic once Redis and audit logging for
these events are live.

## 12. Decision states

Not every endpoint needs every state — each is used only where the
corresponding condition is actually reachable for that operation:

- **ALLOW** — the request proceeds normally. The overwhelming majority of
  requests, on every endpoint.
- **THROTTLE** — the token-bucket check (§8) found insufficient tokens for
  this key. Response: `429` with a `Retry-After` reflecting the bucket's
  refill rate. This is the direct equivalent of today's only behavior,
  now computed per-dimension and coordinated across instances. Used on
  every rate-limited endpoint.
- **STRICT_THROTTLE** — an abuse rule (§11) matched at its lower
  severity (R1, R2, R4 — R2 deliberately capped at this severity rather
  than a hard block; see §11's account-lockout-as-DoS-vector analysis):
  the dimension is still allowed to eventually succeed, but is held to a
  tighter effective rate than the base bucket for a bounded escalation
  window. Implemented as a *second*, stricter token bucket (smaller
  capacity/slower refill) that the abuse layer activates for that
  dimension for the escalation window's duration — not a separate
  boolean, so it still expires cleanly via TTL. Used only on `login` and
  `forgot-password`, where a "someone is guessing/spamming but not yet
  at block-worthy volume" middle ground is meaningful; not used on
  `register`/`refresh`/`reset-password` because no rule in §11 targets
  them at this severity.
- **TEMPORARY_BLOCK** — an abuse rule matched at its higher severity (R3,
  R5 — see §11 for why R2 was deliberately excluded from this severity):
  the dimension is rejected outright for a bounded duration,
  without consulting the ordinary token bucket at all (checked first, per
  §6's flow diagram). Response: `429` (deliberately the same status code
  as ordinary throttling — see §16 on why the response must not reveal
  which internal state produced it). Auto-expires via Redis TTL (§17);
  never a permanent or indefinite block, per the task's explicit
  requirement.
- **REJECT** — reserved, and **not used by this design as specified**.
  The task lists it as a state to define; this design finds no
  operation-level condition in the current system that needs a rate-limit
  layer decision distinct from `THROTTLE`/`TEMPORARY_BLOCK` on one hand or
  ordinary input validation (`400`/`401`, already handled outside the
  rate limiter entirely) on the other. Defining `REJECT` here without a
  concrete trigger would be exactly the kind of state forced in without
  architectural need that the task warns against. **Open decision:** if a
  future signal emerges that specifically warrants an immediate, non-TTL
  rejection distinct from both of the above (e.g., a structurally
  malformed identity claim detected before any bucket check), it should
  be added then, with its own justification — not preemptively now.

## 13. Redis failure policy (mandatory, operation-aware)

No single global policy. Two failure-handling tiers, chosen per
operation's actual security sensitivity — not "fail open everywhere" or
"fail closed everywhere."

**What security guarantee is actually lost during a Redis failure,
stated honestly and up front, per adversarial review's explicit demand
— this is not a footnote:**

| Scenario | What's lost | What still holds |
|---|---|---|
| Single backend instance, Redis down | Nothing beyond what exists today — the Tier A fallback (below) *is* today's actual limiter, on the one instance that's already the whole deployment. | Full protection, unchanged from pre-Redis behavior. |
| Multiple backend instances, Redis down | **Distributed coordination — the entire reason this ADR exists.** Each instance falls back to its *own* independent in-process bucket (§13's Tier A), so the effective limit is multiplied by instance count, exactly reproducing §2.1's original gap for the outage's duration. | The *base* rate limit still applies per instance (not zero limiting), and it self-heals the moment Redis recovers — this is a temporary, monitored (see "Mechanics" below) degradation to a known, previously-accepted weakness, not a new one. |
| Either, block-check specifically unreachable | The abuse layer's escalation on top of the base limit (§11's `STRICT_THROTTLE`/`TEMPORARY_BLOCK`) — a dimension that was blocked is treated as not-blocked for the outage's duration. | The base rate limit (via whichever tier's fallback applies) still runs; an unblocked-during-outage identity is still throttled, just not additionally blocked. |
| An attacker who can trigger or time a Redis outage | In a multi-instance deployment: a temporarily multiplied (not eliminated) rate limit, and no abuse escalation, for as long as the outage lasts. | The attacker never gets *zero* rate limiting on any tier — every path in this policy still enforces the in-process fallback's numbers at minimum. |

**Tier A — security-sensitive endpoints (`login`, `refresh`,
`forgot-password`, `reset-password`):** on Redis unavailability, timeout,
or error, **fall back to the existing in-process `FixedWindowRateLimiter`**
for that check, rather than either (a) disabling rate limiting entirely
(unacceptable — a Redis outage would become a brute-force opportunity) or
(b) rejecting all requests outright (unacceptable — a Redis outage would
become a self-inflicted denial of service on every login attempt,
including legitimate ones). The in-process limiter is imperfect
under multi-instance deployment (per the table above) but is a real,
tested, already-working safety net — strictly better than either
extreme, and it is why §6 keeps it as a first-class fallback rather than
deleting it. Abuse-layer `TEMPORARY_BLOCK` checks (§12) specifically
**fail open** on Redis failure (an unreachable block-store is treated as
"not blocked," since blocking is a defense-in-depth layer *on top of*
the base rate limit, and the base limit is still enforced via the Tier A
fallback) — this is a deliberate exception within Tier A's otherwise
conservative posture. The alternative (failing *closed* on an
unreachable block-check — treating "cannot verify" as "assume blocked")
was considered and rejected: since a block-check that can't reach Redis
can't distinguish *which* identities are actually blocked from those
that never were, failing closed there would mean *every* caller looks
unverifiable and gets rejected for the outage's duration — an
indiscriminate denial of service on the entire endpoint for every user,
not a targeted continuation of protection against the specific
identities that had actually tripped a block. Failing open on this one
check is the smaller, better-understood cost.

**Tier B — `register`:** a `register`-only endpoint has lower security
sensitivity than the credential-bearing endpoints above (an attacker
gains an account, not access to an existing one), so on Redis failure it
**fails open** (falls back to no additional limiting beyond ordinary
application validation) rather than risk blocking legitimate signups
during a Redis blip. **Open decision:** whether `register` should
actually share Tier A's fallback instead is a reasonable alternative;
this ADR takes the more permissive position because unauthenticated
signup abuse is a lower-severity outcome than authentication brute force,
but this should be revisited once real abuse data exists.

**The application's own `/api/v1/health/ready` endpoint must not be made
to depend on Redis connectivity — a deliberate, explicit design
decision, not an oversight to catch later.** That endpoint currently
verifies real database connectivity (Issue #1) because the application
genuinely cannot serve correct responses without PostgreSQL. Redis is
architecturally different by design (§7): this entire failure policy
exists so the application keeps serving traffic, with degraded but
present rate limiting, when Redis is unavailable. If `/api/v1/health/ready`
were also wired to check Redis, an orchestrator (or a Docker/Compose
healthcheck, or a load balancer) would pull an otherwise-healthy instance
out of rotation, or restart it, for exactly the condition this failure
policy is designed to tolerate gracefully — turning a handled, monitored
degradation into an unnecessary outage. Readiness reflecting Redis health
would contradict the entire point of Tier A/Tier B (above). Docker
Compose's `depends_on: redis: condition: service_healthy` (§16) is a
separate, container-startup-ordering concern for local dev/CI determinism
only — it must not be conflated with, or used to justify, making the
application's own runtime readiness check depend on Redis.

**Mechanics common to both tiers:**

- Every Redis call in the rate-limit/abuse path uses a strict, short
  client-side timeout (on the order of tens of milliseconds — the exact
  value is an implementation-time tuning decision, not invented here) so
  a degraded (not fully down) Redis cannot make requests hang; a timeout
  is treated identically to a connection failure.
- Every Redis client exception in this path is caught at the boundary
  between the rate-limiter and the route dependency — never allowed to
  propagate as an uncaught exception into FastAPI's generic error
  handling, which would produce an unstructured `500` rather than the
  documented fallback behavior. This directly satisfies the task's "must
  not turn a Redis outage into uncontrolled exceptions or misleading HTTP
  behavior."
- A Redis-failure fallback event is logged (structured log, not a
  Postgres audit row — see §14) so degraded operation is visible in
  observability without spamming the durable audit trail.

## 14. Redis key design

Namespace: two top-level prefixes, `rl:` (rate-limit buckets) and
`abuse:` (abuse counters/blocks), so the two concerns are trivially
distinguishable during debugging (`redis-cli --scan --pattern 'rl:*'` vs.
`'abuse:*'`) without needing to inspect values.

```
rl:{operation}:ip:{ip_address}
rl:{operation}:acct:{hmac_sha256(key, lowercase(email))}
rl:{operation}:session:{session_id}

abuse:failcount:{signal}:ip:{ip_address}
abuse:failcount:{signal}:acct:{hmac_sha256(key, lowercase(email))}
abuse:distinct_ips:acct:{hmac_sha256(key, lowercase(email))}   # a Redis HyperLogLog, per §11's R3 — see §11
abuse:block:{operation}:ip:{ip_address}
abuse:block:{operation}:acct:{hmac_sha256(key, lowercase(email))}
```

**Email identifier: keyed HMAC, not plain `sha256(email)` (correction
from adversarial review of this ADR's first draft).** The first draft
used a plain, unkeyed `sha256(lowercase(email))`. That is not a
meaningful privacy protection for an input like an email address: unlike
a refresh-token secret or password-reset token (256 bits of random
entropy — genuinely infeasible to guess or enumerate), email addresses
are low-entropy, structured, and often already known or leaked in bulk.
Anyone holding a candidate list of emails (a purchased/leaked list, or
simply every registered user's address from another breach) can
precompute `sha256(email)` for every candidate and match it directly
against observed Redis keys — a plain hash of a low-entropy input is a
lookup table waiting to be built, not a one-way transformation in any
practical sense. **Corrected design: `HMAC-SHA256(key, lowercase(email))`**,
where `key` is a server-held secret never exposed outside the backend.
Precomputing a matching table now requires knowing that secret, which an
external holder of a leaked email list does not have — this is the
standard reason HMAC (not plain hashing) is the correct primitive for
keying data by a low-entropy identifier, exactly analogous to why
passwords are salted+hashed rather than plainly hashed, though the
threat model here is enumeration/dictionary-matching of Redis keys, not
password cracking. **Open decision (§22):** whether `key` is a new,
dedicated setting (e.g. `RATE_LIMIT_HASH_KEY`) or reuses `SECRET_KEY`
(`app/core/config.py`) — a dedicated key is preferable for key
separation (rotating one secret shouldn't require touching the other's
consumers), but reusing `SECRET_KEY` avoids introducing a new required
secret; either is cryptographically sound, so this is a hygiene
trade-off to make at implementation time, not a correctness question.

Design rationale against the task's explicit requirements:

- **No collisions:** every key is namespaced by concern (`rl:`/`abuse:`),
  operation, dimension type, and dimension value — two different
  operations or dimension types can never collide even if a dimension
  value happens to coincide.
- **TTL support:** every key above is a bucket, counter, set, or flag with
  a defined TTL (§10, §17) — nothing in this design is written without an
  expiry.
- **No sensitive/credential material:** raw email addresses, passwords,
  access tokens, refresh tokens, and password-reset tokens **never**
  appear in a key or value — email is transformed via keyed HMAC before
  use (see above; a stronger version of the pattern already established
  for refresh-token secrets and password-reset tokens in
  `app/core/security.py`, which are hashed with plain SHA-256 *because*
  they are already high-entropy random secrets, unlike email addresses),
  and session IDs are already non-secret random identifiers the API
  itself exposes (`GET /api/v1/auth/sessions`), not credentials.
  `ip_address` is stored in plaintext, matching what
  `audit_logs.ip_address` already does in PostgreSQL today — not a new
  category of sensitive data this system didn't already record.
- **No cross-workspace/user confusion:** every account-scoped key is
  keyed by the hashed account identity, never by a value an unrelated
  user or workspace could cause to collide (no shared "global" counters
  in this design, except the tier-scoped fallback which is inherently
  IP/account-scoped already).
- **Debuggable:** the prefix scheme itself communicates intent
  (`rl:login:ip:203.0.113.4` is self-explanatory) without needing to
  decode a hash to understand *what kind* of thing a key represents, even
  though the hashed portion itself isn't reversible.
- **Bounded cardinality:** TTL (§10) bounds every key above to
  *currently active* identities, not all-time — and, per §10, a key is
  only ever written when its operation's request is actually allowed, so
  a flood of requests that get rejected doesn't create new keys either.
  `abuse:distinct_ips:acct:*` (§11's R3) is the one exception worth a
  dedicated decision: **corrected from a plain `SET` to a HyperLogLog**
  (`PFADD`/`PFCOUNT`) in this revision — see §11 for why a `SET` was the
  wrong default specifically for this signal, unlike everywhere else in
  this design where TTL alone is a sufficient bound.

## 15. Observability / audit strategy

Not every rate-limit event deserves a permanent, durable
(`audit_logs`) record — the task explicitly warns against spamming
Postgres for every normal allowed request. The split:

| Event | Where it goes | Why |
|---|---|---|
| `ALLOW` | Nowhere beyond the ordinary access log (already exists — `app/observability/access_log.py`) | The overwhelming majority of traffic; a per-request audit row here would dwarf every other audit event type for no security value. |
| `THROTTLE` (ordinary `429`) | A structured log line (metrics-oriented), **not** a Postgres audit row | Expected, common, and often just a legitimate client retrying too fast — not itself security-significant enough for the durable trail, consistent with `docs/SECURITY.md`'s existing "don't spam audit logs" posture (implicit in its current curated event list). |
| `STRICT_THROTTLE` activated | **`audit_logs` row** — reuses the already-defined-but-unused `AuditEvent.RATE_LIMITED` (§5) | This is the first point where the system has formed an opinion that a specific dimension looks abusive, not just momentarily over budget — worth a durable, queryable record. |
| `TEMPORARY_BLOCK` applied | **`audit_logs` row** — a new `AuditEvent` constant (e.g. `ABUSE_TEMPORARY_BLOCK_APPLIED`) | Security-significant by definition; needed for incident review and for tuning the rule thresholds in §11 against real data. |
| Redis failure/fallback | Structured log line, not an audit row | Operational/degradation signal, not a security event about a *client* — belongs with other infrastructure-health logging. |

This closes the gap identified in §5 (`RATE_LIMITED` defined but never
emitted) using the event's already-established name, rather than
inventing a parallel constant for the same concept.

## 16. Docker / local development / CI implications (design only)

- A `redis` service would join `infra/compose/docker-compose.yml`
  following the same pattern already established for `db` and `mailpit`:
  a standard image (e.g. `redis:7-alpine` — the exact pinned version is
  an implementation-time decision), a healthcheck (`redis-cli ping`,
  matching the `pg_isready`/built-in-`readyz` pattern already used), and
  `backend` gaining `depends_on: redis: condition: service_healthy`
  alongside its existing `db`/`mailpit` dependencies — **for local dev
  and CI only.** This ordering guarantee is a determinism convenience for
  those environments (so a test run never races a not-yet-ready Redis),
  not a statement that the application requires Redis to start at all —
  that would directly contradict §13's whole point (graceful degradation
  when Redis is unavailable). A production deployment's own startup/
  readiness checks should not hard-fail on Redis being briefly
  unreachable at boot, consistent with the runtime failure policy.
- Configuration would follow the existing convention: a `REDIS_URL`
  setting in `app/core/config.py` (required once Redis-backed limiting is
  the primary path, following the same "fail loudly if missing" pattern
  already used for `SECRET_KEY`/`DATABASE_URL`), documented in
  `.env.example`, with a `local`-environment default pointing at the
  Compose service — mirroring exactly how `DATABASE_URL` and
  `SMTP_HOST` are already handled.
- **Test environment:** `backend/tests/conftest.py` currently provisions
  a real Postgres for integration tests (not a mock — ADR 0002's "no
  sqlite substitute" precedent). The same principle should extend to
  Redis: integration/security tests for the rate-limiter and abuse layer
  should run against a real Redis instance, not a mock, for the same
  reason — a mock cannot verify the atomicity/concurrency properties this
  design depends on (§10). This means CI needs a Redis service
  alongside its existing `pgvector/pgvector:pg16` service container
  (`.github/workflows/ci.yml`).
- **Failure-policy tests** (§13) need a way to *simulate* Redis being
  unavailable in a controlled test — e.g., pointing the client at an
  unreachable port/host for that specific test, or a fixture that closes
  the connection mid-test — rather than only testing the happy path.
- None of the above is implemented by this ADR — no service, dependency,
  or config file was added; this section documents what implementation
  would need to do.

## 17. Testing strategy (design only — no tests added by this ADR)

**Unit** (no real Redis needed — pure logic):
- Token-bucket refill/consume math (§8) given synthetic
  elapsed-time inputs.
- Abuse rule-table evaluation (§11) given synthetic counter states — each
  rule (R1–R5) triggers exactly under its stated condition and not
  otherwise.
- TTL calculation (§10, §17) for both rate-limit buckets and abuse
  counters/blocks.
- Decision-state selection logic (§12) — which state a given
  bucket-check + rule-evaluation combination produces.
- Fallback-selection logic (§13) — given a simulated Redis failure, the
  correct tier's fallback behavior is chosen.

**Integration** (real Redis, per §16):
- The Lua script's atomicity under concurrent invocations for the *same*
  key (many simultaneous checks should never allow more than `capacity`
  tokens to be consumed).
- **The multi-key compound decision (§10) never partially consumes one
  dimension when another dimension rejects the request** — the direct
  regression test for the atomicity flaw found in this ADR's adversarial
  review: replay §10's worked scenario (two accounts/IPs racing against
  a nearly-exhausted account bucket) and assert the rejected request's
  IP bucket was never touched.
- Multiple logical "backend instances" (multiple client connections to
  one Redis, simulating horizontal scale-out) sharing rate-limit state
  correctly — this is the direct regression test for §2.1's problem.
- Real TTL expiry (a key created now is gone after its TTL, not before).
- Redis failure/timeout scenarios per §13, using the simulated-failure
  approach from §16, asserting the documented tier-specific fallback
  behavior actually happens (not just that no exception propagates), and
  specifically that a multi-instance Redis outage degrades to (not below)
  the fallback limiter's per-instance rate, per §13's failure-mode table.

**Concurrency** (a specific integration-test focus, since this is the
task's explicit concern):
- Many concurrent requests for one key never exceed `capacity` allowed
  requests within a window that shouldn't permit more — the direct test
  that the naive `GET → calculate → SET` race the task warns against does
  not exist in the chosen Lua-script design.
- The HyperLogLog update (R3) under concurrent writers from different
  simulated IPs converges to approximately the correct count (within
  HyperLogLog's known error bound, not exact).

**Security:**
- Cross-user isolation: one account's failed logins never affect another
  account's bucket or abuse counters (key design in §14 makes this a key-
  uniqueness test).
- Cross-workspace isolation: not directly applicable to the five
  endpoints in scope (none are workspace-scoped today), but the key
  design (§14) should be re-validated against this property the moment
  a workspace-scoped operation is added under this mechanism.
- Bypass attempts: a client cannot escape its bucket by varying
  irrelevant request properties (only the documented dimensions in §9
  affect the key).
- **Spoofed `X-Forwarded-For`** (§9a): a client-supplied
  `X-Forwarded-For` header must be silently ignored when
  `TRUSTED_PROXY_CIDRS` is unset or the immediate peer isn't in a
  trusted CIDR — a direct attacker cannot choose their own rate-limit
  key by setting the header on a request that goes straight to the
  backend. A second test confirms the header *is* honored, and correctly
  walked from the right, when the immediate peer *is* a configured
  trusted proxy — including the chained-trusted-proxies case.
- Authentication-failure abuse: R1/R3 (§11) trigger under the exact
  synthetic failure patterns they're designed for (single-IP brute force,
  coordinated multi-IP brute force via HyperLogLog's threshold), and do
  *not* trigger under normal, non-abusive failure patterns (e.g., one
  user mistyping their password twice). **R2 specifically must be
  verified to produce `STRICT_THROTTLE`, not `TEMPORARY_BLOCK`** — the
  direct regression test for the account-lockout-as-DoS-vector finding:
  simulate many failed logins against one account from a single IP and
  assert the account can still eventually authenticate (just slowly),
  never a hard rejection from this rule alone.
- Reset-password abuse: R5 triggers on repeated invalid/expired/used
  token responses from one IP.
- Rate-limit exhaustion: the direct `429` behavior, now assertable
  against real Redis-backed state rather than only the in-process
  fallback.
- Temporary-block expiry: a blocked dimension (only ever reachable via
  R3 or R5 after this revision) is rejected during the block window and
  allowed again (subject to the ordinary bucket) the moment the TTL
  expires — never requiring a manual/administrative unblock for the
  bounded case.
- **Victim-targeting attempt**: an attacker who knows only a victim's
  email, sending failed logins from one IP, cannot fully lock the victim
  out (asserts the R2 downgrade's actual security property, not just its
  mechanical decision-state).

**Regression:**
- Every existing Issue #2 authentication/CSRF/password-recovery test
  (`backend/tests/test_auth.py`, `test_csrf.py`, `test_cookie_security.py`,
  `test_password_reset.py`, `test_rate_limit.py` — 119 tests total as of
  this ADR) must continue passing unmodified, since the public
  `enforce_*_rate_limit` interface does not change (§6).

## 18. Security considerations

- This design does not weaken any existing protection — CSRF, cookie
  attributes, CORS, and Argon2id hashing (ADRs 0003–0005) are unaffected;
  this ADR is additive.
- The abuse layer's `TEMPORARY_BLOCK` state must return the same `429`
  shape as ordinary throttling (§12) specifically so an attacker cannot
  distinguish "you're rate-limited" from "you've been flagged as
  abusive" — revealing that distinction would let an attacker calibrate
  their request rate to stay just under the abuse threshold while still
  being throttled, defeating the point of having two severities.
- Keying Redis entries by an HMAC of the email address (§14) — not a
  plain hash — means a Redis data dump does not let a holder of a leaked
  email list precompute matches against observed keys; see §14 for why a
  plain hash was insufficient for a low-entropy identifier. A modest but
  real privacy improvement, at the cost of losing human-readability
  during debugging (an accepted trade-off, consistent with
  `docs/SECURITY.md`'s "avoid leaking sensitive information
  unnecessarily" posture).
- The `X-Forwarded-For` gap identified in §5 is now fully designed, not
  just flagged — §9a specifies the trusted-proxy model (default: ignore
  the header entirely; only walk it, from the right, when the immediate
  peer is a configured trusted proxy). It affects the *current* IP-only
  limiter too, not just the future Redis one, and is a genuine,
  pre-existing security-relevant finding independent of this ADR's main
  subject.
- **Account-lockout as a denial-of-service vector against a known victim**
  (found during adversarial review of this ADR's first draft — see §11):
  any account-scoped abuse rule triggered by *anything an outside party
  can supply* (an email address is not secret) risks letting that party
  weaponize the protection against a victim they merely know the address
  of. §11's R2 was downgraded from a hard block to `STRICT_THROTTLE`
  specifically to close this for the common case; only R3 (requiring
  genuinely distributed source IPs, not fabricable by a casual attacker
  from one machine) still triggers a hard `TEMPORARY_BLOCK` on the
  account dimension. This is a real, general trade-off inherent to any
  account-lockout-style defense (recognized in standard security
  guidance on the topic), not a flaw unique to this design, but the
  first draft did not account for it.
- **Redis cardinality / memory threat analysis** (the task's explicit
  Critical Review #10 — every attacker-influenceable Redis structure in
  this design, analyzed for who can create it, its bound, and its TTL):

  | Structure | Who can create/grow it | Bound | TTL | Attacker-cheap to multiply? |
  |---|---|---|---|---|
  | `rl:{op}:ip:{ip}` | Anyone making a request to that operation | One key per distinct source IP active within the window | Yes (§10) | No — requires an actual distinct source IP per key, and each request against it is itself rate-limited; identical exposure to what the in-process limiter already has today, not new |
  | `rl:{op}:acct:{hmac}` | Anyone submitting an email to `login`/`forgot-password`, including a fabricated one that matches no real account | One key per distinct submitted email active within the window | Yes (§10) | Bounded, not free: per §10, a key is only *written* when its operation's request is allowed, and every request is gated by that same request's IP-dimension check in the same atomic decision — so the rate of new fabricated-email keys from one source is capped by that source's own IP-bucket rate |
  | `rl:{op}:session:{id}` | Only a caller holding a valid session (already authenticated) | One key per active session | Yes (§10) | No — requires a real, already-authenticated session; not available to an unauthenticated attacker at all |
  | `abuse:failcount:*` | Same gating as the corresponding `rl:*` key that must be checked/passed first | Same as above | Yes (§10) | Same reasoning as above |
  | `abuse:distinct_ips:acct:{hmac}` | Anyone causing `LOGIN_FAILED` events against one account from many source IPs — i.e., exactly the R3 attack | **Fixed ~12KB per key regardless of true cardinality** (HyperLogLog, §11 — this is the one structure where the original `SET`-based design was *not* adequately bounded, corrected in this revision) | Yes (§10) | Memory no longer scales with attacker IP count at all, by construction |
  | `abuse:block:*` | Only created once a rule in §11 actually fires (itself gated by the failcount keys above) | One flag per dimension that has actually tripped a rule | Yes (§10, §11) | No — strictly downstream of the already-bounded failcount signals |

  **What happens during sustained abuse, honestly stated:** an attacker
  with genuinely large, distributed infrastructure (the R3 threat model)
  can still cause a meaningful number of `rl:*ip:*` and
  `abuse:failcount:*ip:*` keys to exist simultaneously — bounded by TTL
  and by their own real request volume, not eliminated. This is
  inherent to any IP-keyed system facing a real botnet and is not unique
  to or worsened by this design; the correction in this revision
  specifically ensures the *one* structure whose size scaled with
  attacker IP count *without* a corresponding per-key fixed cost
  (`abuse:distinct_ips:*`) no longer does.

## 19. Alternatives considered

- **Sliding-window log (store every request timestamp in a Redis sorted
  set)** — more precise than token bucket at the cost of unbounded
  per-key memory proportional to request volume within the window
  (mitigated by trimming, but every check becomes an `O(log n)`
  operation over a growing structure rather than `O(1)` over a fixed-size
  hash). Rejected in favor of token bucket, which gives equivalent
  burst/rate control with `O(1)` state per key.
- **Redis `INCR` + `EXPIRE` without a Lua script (simple fixed-window
  counter)** — closer to a literal port of today's algorithm, and
  simpler to implement than a Lua script. Rejected because it reintroduces
  the boundary-doubling problem (§2.2, §8) for no simplicity benefit that
  matters at this scale, and because `INCR`+`EXPIRE` as two separate
  commands (even if both atomic individually) reintroduces a
  window between them where a process crash could leave a key
  without its TTL set, unlike a single Lua script that sets both
  atomically together.
- **A managed third-party rate-limiting service (e.g., a WAF-level rate
  limiter, or a hosted API gateway feature)** — rejected as premature
  infrastructure for the same reason ADR 0001 excludes it: no measured
  requirement points at needing a system external to this application's
  own deployment, and it would introduce a vendor dependency and network
  hop this design avoids entirely by keeping the check inside the
  request path against a datastore this project already needs to reason
  about (Redis, once introduced).
- **A numeric abuse risk score instead of the rule table (§11)** —
  rejected; see §11's rationale (auditability, no evidence to justify
  weights).
- **Redis Streams / pub-sub for real-time abuse event distribution
  across instances** — not needed: every instance queries the same
  shared Redis keys directly (§10), so there is no need to *broadcast*
  state changes between instances; each instance's next check simply
  reads the current shared state. Adding a streaming layer would be
  unjustified complexity for a problem this design doesn't have.
- **Independent per-key Lua scripts for a multi-dimension operation** —
  this ADR's own first draft, rejected during adversarial review. Each
  key's script is individually atomic, but the *compound* decision
  across keys is not, allowing partial consumption on a request that's
  ultimately rejected (worked example in §10). Superseded by a single
  Lua invocation parameterized over all of an operation's keys.
- **Plain `SHA-256(email)` for the account-dimension Redis key** — this
  ADR's own first draft, rejected during adversarial review. Sufficient
  for a high-entropy secret (which is why refresh-token secrets and
  password-reset tokens use exactly this in `app/core/security.py`), but
  not for a low-entropy, potentially-already-leaked identifier like an
  email address, which is dictionary/rainbow-table-matchable from a
  plain hash. Superseded by a keyed HMAC (§14).
- **A plain Redis `SET` for the R3 distinct-IP-per-account signal** —
  this ADR's own first draft, rejected during adversarial review.
  Correct in isolation, but sized by exactly the attacker behavior R3
  exists to detect, making it the one structure in this design an
  attacker could cheaply inflate in memory by executing the very attack
  being watched for. Superseded by a HyperLogLog (§11), which answers
  the same threshold question with fixed memory regardless of true
  cardinality.
- **A hard `TEMPORARY_BLOCK` for R2 (account-scoped login failures from
  any source)** — this ADR's own first draft, rejected during
  adversarial review. An account-level hard block triggerable by anyone
  who merely knows the victim's (non-secret) email address is itself a
  targeted denial-of-service vector against that victim. Superseded by
  capping R2 at `STRICT_THROTTLE` and reserving the hard block for R3,
  whose distributed-IP condition is materially harder to cheaply
  fabricate against a chosen victim (§11).

## 20. Trade-offs

- Token bucket via Lua script is more complex to implement and reason
  about than a plain `INCR`+`EXPIRE` counter — accepted because it
  removes a real, verified correctness gap (§2.2) that the task's
  "must not create a naive GET→calculate→SET pattern" instruction is
  directly warning against in spirit.
- The Tier A fallback (§13) means a sustained Redis outage in a
  multi-instance deployment degrades security-sensitive endpoints back
  to today's known multi-instance weakness (§2.1, and §13's failure-mode
  table) rather than to zero protection — an intentional middle ground,
  not a full fix for the outage case, because a full fix would require
  either (a) accepting a fail-closed denial of legitimate traffic, which
  this design judges worse, or (b) a second independent coordination
  mechanism just for the outage case, which is disproportionate
  complexity for a failure mode that should be rare and monitored
  (§13's logging).
- Keying accounts by HMAC for Redis keys (§14) trades debuggability (a
  human can't `redis-cli GET` their way to "which account is this") for
  the privacy benefit described in §18 — accepted. Unlike a plain hash,
  the mapping is *not* recoverable from database access alone: computing
  a matching key for a candidate email also requires the server-held
  HMAC key (§14's open decision on where that key lives), which is a
  meaningfully stronger property than the first draft's plain-hash
  version had, at the same debuggability cost.
- HyperLogLog for the R3 distinct-IP signal (§11) trades exactness for
  bounded memory — the count crossing threshold `M` is approximate
  (~0.81% standard error), so a determination right at the threshold
  could occasionally be off by a small amount in either direction.
  Accepted because the signal only needs a threshold comparison, never
  the exact membership or count, and the alternative (an exact `SET`)
  has the attacker-scalable memory problem §11 describes — precision
  that scales with attacker effort is a worse trade than a small, fixed
  approximation error.
- Capping R2 at `STRICT_THROTTLE` instead of a hard block (§11) means a
  genuine single-source brute-force attempt against one account is
  slowed but not stopped outright by R2 alone — accepted because R1 (the
  IP-scoped rule) already throttles that same single source
  independently, and R3 remains available to hard-block the account the
  moment the attack becomes distributed enough to no longer look like
  "one attacker, one IP" — the trade-off is against a narrow middle case
  (one attacker, one IP, patient enough to stay under R1's IP-level
  throttle while grinding one account), judged less severe than leaving
  every account open to being locked out by anyone who knows its email.

## 21. Future extension points

- The `AbuseDecisionEngine` interface (§11) can host a more advanced
  model later — behind its own ADR and evaluation evidence, never
  labeled "AI" without one.
- Per-operation `cost` (§9) is already parameterized in the Lua script's
  interface even though every current operation uses `cost = 1` — a
  future expensive operation (uploads, embeddings, LLM calls) can set a
  higher cost without a script change.
- Workspace-scoped dimensions (§9) can be added the same way IP/account/
  session dimensions were added here, once a workspace-scoped expensive
  operation exists to justify them.
- A combined IP+account block dimension (narrower than either R2's or
  R3's account-only scope) if real data ever shows the current rule
  table (§11) produces meaningful false positives or false negatives
  that a more specific dimension would resolve.
- A configurable maximum trusted-proxy hop count (§9a), if a real
  deployment's proxy chain depth ever needs an explicit bound beyond the
  CIDR check alone.

## 22. Open decisions (explicitly not invented in this ADR)

- Exact numeric thresholds for every abuse rule (§11: `N`, `M`, `W` per
  rule) and for the strict-throttle bucket's capacity/refill relative to
  the base bucket (§12) — blocked on the abuse layer itself, a later
  slice.
- **Trusted-proxy configuration values** (§9a): the actual
  `TRUSTED_PROXY_CIDRS` for any real deployment are unknowable until a
  hosting target is chosen — not invented here (the *mechanism* is
  implemented and wired in — slice 2 — but every real deployment must
  still set its own value; local dev/CI correctly run with it unset).
  Whether the hop-walk additionally needs a configured maximum-hop bound
  (defense against a pathologically long forged header) is also still
  left for implementation.

**Resolved during adversarial review** (recorded here, not as open items,
specifically so a reader of this ADR's history knows these were
considered and decided, not overlooked): whether distinct-IP tracking
uses a `SET` or `HyperLogLog` (§11 — HyperLogLog, not left open, because
the "start simple" default was itself the wrong call for this
specific attacker-influenced structure); whether email keys use a plain
hash or a keyed HMAC (§14 — HMAC, not left open, for a low-entropy
identifier); whether R2 produces `STRICT_THROTTLE` or `TEMPORARY_BLOCK`
(§11 — `STRICT_THROTTLE`, to avoid a victim-targeting denial-of-service
vector); and whether per-operation rate-limit checks use one Lua script
per dimension or one per operation across all its dimensions (§8, §10 —
one per operation, for compound atomicity).

**Resolved during implementation** (slices 1–2 — recorded here with
rationale, per this section's own instruction, rather than decided
silently in code):

- **Redis client timeout value** (§13): `0.05`s (both socket and connect
  timeout) — `app/core/config.py`'s `redis_socket_timeout_seconds`/
  `redis_socket_connect_timeout_seconds`, configurable, not hardcoded.
- **TTL safety factor** (§10): `2.0×` — `RedisTokenBucketLimiter`'s
  `_TTL_SAFETY_FACTOR` in `app/core/rate_limit.py`.
- **Pinned Redis image version** (§16): `redis:7.4-alpine`, in both
  `infra/compose/docker-compose.yml` and `.github/workflows/ci.yml`.
- **HMAC key location** (§14): reuses `secret_key` by default
  (`Settings.rate_limit_hash_key_resolved`), with an explicit
  `RATE_LIMIT_HASH_KEY` override available for deployments that want key
  separation — chosen to avoid requiring a new secret to be provisioned
  for every deployment when the threat model (Redis-key dictionary
  resistance) doesn't strictly need one distinct from JWT signing.
- **Whether `register` shares Tier A's fallback instead of failing
  open**: resolved with a distinction the ADR's original wording didn't
  draw — see the dedicated note in "Implementation status" and
  `SOLVING.md`'s 2026-09-14 entry on this exact question. Short version:
  `register` shares Tier A's fallback whenever Redis was never
  configured at all, and only fails open (Tier B, as originally written)
  during a genuine mid-request outage of an *already-configured* Redis.

Everything in this section's remaining bulleted list is a genuine
decision still left for a future slice or a real deployment target —
not decided speculatively here without evidence.

## 23. Consequences

- `backend/app/core/rate_limit.py` gains a Redis-backed implementation
  alongside (not instead of) `FixedWindowRateLimiter`, plus a small
  abuse-decision module, once implementation begins.
- `docs/SECURITY.md` §"Rate limiting approach" needs updating once
  implementation lands (not by this ADR — this ADR documents the design,
  not the implementation; see the accompanying documentation-reconciliation
  changes made alongside this ADR, which mark the *design* as complete
  and the *implementation* as still not started).
- `docs/API_CONTRACT.md` §"Rate limiting" does not need a design-time
  update: it already states the limiter is in-process only and that
  Redis-backed distributed rate limiting has not been implemented, which
  remains accurate. The externally-visible contract this design produces
  (still a `429` with the shared error shape on any rejection, regardless
  of which internal state — `THROTTLE`/`STRICT_THROTTLE`/
  `TEMPORARY_BLOCK` — produced it, per §12/§18) does not change, so no
  new endpoint documentation is needed until implementation adds
  something client-visible (e.g., a `Retry-After` header, §12) that
  isn't already documented.
- `infra/compose/docker-compose.yml` and `.github/workflows/ci.yml` gain
  a `redis` service when implementation begins (§16) — not yet.
- `.env.example` and `app/core/config.py` gain `REDIS_URL` (§16),
  `TRUSTED_PROXY_CIDRS` (§9a, defaulting to empty/no-trust), and
  whatever setting backs the HMAC key (§14, §22) when implementation
  begins — not yet.
- A new `docs/DECISIONS/0007-...` may be needed later if implementation
  reveals this design needs revision, or if the abuse model is ever
  replaced with something more advanced — per §21, that always gets its
  own ADR, never a silent upgrade.

## Implementation status

**Five distinct maturity states apply to everything in this ADR, and
they are not interchangeable — conflating them is exactly the kind of
overclaim this document works to avoid.** As of this ADR's original
acceptance, everything below was "Designed" only. **As of implementation
Slice 1** (commit `b1f1b00` on branch `issue-redis-rate-limiting`,
**committed, not yet pushed or merged**) **and Slice 2** (same branch,
on top of that commit, **implemented but uncommitted, working-tree-only**
— see `HANDOFF.md`), that is no longer uniformly true; the table below is
now per-component, not a single status for the whole ADR:

| State | Meaning |
|---|---|
| **Designed** | Written down, reasoned about, reviewed (including adversarially) |
| **Implemented** | Code exists that does what's designed |
| **Tested** | Automated tests (unit/integration/security/regression, §17) verify the implementation |
| **Committed** | The code is part of a real Git commit on this branch — distinct from merely existing in the working tree |
| **Production-validated** | Actually run against real production traffic and shown to behave as designed |

| Component | Designed | Implemented | Tested | Committed | Production-validated |
|---|---|---|---|---|---|
| Redis configuration (§7, `.env.example`/`app/core/config.py`) | Yes | **Yes** (slice 1) | **Yes** (config-validation tests) | **Yes** (`b1f1b00`) | No |
| Redis connection abstraction (`app/core/redis_client.py`) | Yes | **Yes** (slice 1) | **Yes** (real-Redis tests) | **Yes** (`b1f1b00`) | No |
| Redis key namespace + HMAC-SHA256 identifier (§14, `app/core/redis_keys.py`) | Yes | **Yes** (slice 1) | **Yes** | **Yes** (`b1f1b00`) | No |
| Trusted-proxy IP resolution (§9a, `app/core/ip_resolution.py`) | Yes | **Yes** (slice 1) | **Yes** | **Yes** (`b1f1b00`) | No — the function exists and is committed, but is **not called from any endpoint in the committed state**; slice 2 would wire it in (see below) |
| Multi-key atomic Lua token-bucket engine (§8/§10, `RedisTokenBucketLimiter`/`DimensionSpec` in `app/core/rate_limit.py`) | Yes | **Yes** (slice 1) | **Yes** — including the direct multi-key-atomicity and concurrency regression tests §17 names, against a real Redis instance | **Yes** (`b1f1b00`) | No |
| `redis` Docker Compose/CI service (§16) | Yes | **Yes** (slice 1) | N/A (infra, not app logic) | **Yes** (`b1f1b00`) | No |
| **Endpoint wiring** — every `enforce_*_rate_limit` dependency attempts the Redis engine above first | Yes | **Yes** (slice 2) | **Yes** — `tests/test_rate_limit_wiring.py` (real-Redis key creation via a live endpoint call, Tier A/B failure-policy HTTP tests, spoofed-header-ignored-by-default) plus every pre-existing `test_auth.py`/`test_password_reset.py` rate-limit assertion, now exercised through the live Redis path | **No** — implemented and tested only in the uncommitted Slice 2 working tree; every endpoint's committed behavior still calls only the in-process limiter | No |
| Redis failure policy in the actual request path (§13's Tier A/B fallback logic, `_check_or_fallback()`) | Yes — with one sub-decision resolved during implementation, see below | **Yes** (slice 2) | **Yes** — unit-level via dependency override, and live against the real Docker Compose stack (Redis stopped mid-session, both tiers verified, then Redis restarted and enforcement resumed without a restart) | **No** — uncommitted, working-tree-only, same as endpoint wiring above | No |
| Deterministic abuse/risk layer (§11–§12, `AbuseDecisionEngine`) | Yes | **No** | No | No | No |
| `AuditEvent.RATE_LIMITED` / abuse-escalation audit emission (§15) | Yes | **No** | No | No | No |

**§13's Tier B sub-decision, resolved during slice 2 (recorded here per
§22's instruction that open decisions get their rationale recorded
alongside the code, not decided silently):** §13 left open "whether
`register` should actually share Tier A's fallback instead" of failing
open. Implementation distinguishes "Redis was never configured for this
deployment" (`get_redis_client()` returns `None` — always falls back to
`FixedWindowRateLimiter`, every operation, including `register`) from "Redis
is configured but is currently unreachable" (`RedisUnavailableError` —
where Tier A/B's documented policies apply as written). Rationale: since
`REDIS_URL` defaults to unset, applying Tier B's literal fail-open to the
"never configured" case would leave `register` with zero rate limiting
by default in every environment that hasn't explicitly opted into Redis
— a regression of `docs/SECURITY.md` principle 8 for the *default*
state, not an actual outage. Full reasoning and verification:
`SOLVING.md`'s 2026-09-14 "ADR 0006 §13's Tier B..." entry.

**What this means in practice, stated plainly:** Slice 2's code — every
`enforce_*_rate_limit` dependency attempting the Redis engine first,
using ADR §9's exact per-operation dimensions (IP always; account via
keyed-HMAC email for `login`/`forgot-password`; session ID, parsed from
the refresh-token cookie without a database round-trip, for `refresh`),
falling back to `FixedWindowRateLimiter` per the resolved Tier A/B policy
above — **exists, is implemented, and is tested, but is not committed.**
It sits as uncommitted working-tree changes on top of the Slice 1 commit
(`b1f1b00`). **Until Slice 2 is itself reviewed and committed, it is not
a real, observable change to any authentication endpoint's rate-limiting
behavior in this repository's actual history** — every endpoint's
*committed* behavior is still exactly the pre-Redis in-process limiter,
unchanged. Slice 2's behavior has been verified both by automated tests
and live against the running Docker Compose stack (including a genuine
Redis outage and recovery), which establishes it is *correct*, not that
it is *live*. What is **not** yet true in either committed or uncommitted
form: the deterministic abuse/risk layer (§11/§12) does not exist, so no
`STRICT_THROTTLE`/`TEMPORARY_BLOCK` escalation is possible, and
`AuditEvent.RATE_LIMITED` is still never emitted (§15). Nothing in this
ADR should be read as claiming **Production-validated** for any
component: no production deployment of this project exists at all (§1).

Remaining work (tracked in `HANDOFF.md`'s "Exact next recommended
action"): push and open a PR for Slice 1; after it merges, review and
commit Slice 2; only after that, the deterministic abuse layer (§11/§12)
and its audit-emission wiring (§15) — its own reviewed unit of work, not
folded into slice 2, and not to be started before Slice 1/2 have landed.
