# SOLVING.md — Hard Problem Log

This file is a chronological log of genuinely hard problems encountered in
this repository: root causes, what was tried and failed, what actually
worked, how the fix was verified, and how to prevent recurrence. It is
**not** a general changelog (see `CHANGELOG.md`) and not a place to record
routine, expected work.

Only add an entry when a problem took real investigation to solve — a
misleading error message, a non-obvious interaction between components, a
subtle bug whose fix wasn't the first thing tried. Do not fabricate entries
to make this log look more populated than the project's actual history.

## Entry template

```
## YYYY-MM-DD — <short problem title>

**Symptom:** What was observed (error text, wrong behavior, etc).

**Root cause:** What was actually wrong, once found.

**Failed attempts:** What was tried first that did NOT fix it, and why it
didn't (this is often the most valuable part — saves the next person from
repeating it).

**Fix:** What actually resolved it.

**Verification:** How it was confirmed fixed (test added, manual repro
steps, etc).

**Prevention:** What changed (a test, a lint rule, a doc note, a process
step) so this doesn't recur.
```

---

## 2026-09-13 — Postgres native enum created twice by Alembic

**Symptom:** `alembic upgrade head` for migration `0002` failed with
`psycopg.errors.DuplicateObject: type "workspace_role" already exists`,
even though the migration only appeared to create the type once.

**Root cause:** The migration explicitly called
`_WORKSPACE_ROLE_ENUM.create(op.get_bind(), checkfirst=True)` before
`op.create_table("workspace_members", ...)` — but SQLAlchemy's
`sa.Enum` column type *also* emits its own `CREATE TYPE` via a
`before_create` DDL event whenever the table containing it is created, with
no awareness of the type having been separately created a moment earlier in
the same migration. Two `CREATE TYPE` statements for the same name in one
transaction is a hard conflict.

**Failed attempts:** None — this was caught on the first `alembic upgrade
head` run against the real database, before it was ever an unnoticed
partial-migration risk.

**Fix:** Removed the separate explicit `.create()` call in `upgrade()`;
let `create_table`'s own before-create hook create the enum type exactly
once. The explicit `.drop()` call in `downgrade()` is still required and
correct — `drop_table` does *not* automatically drop a Postgres enum type,
only `create_table` auto-creates one.

**Verification:** `alembic upgrade head` succeeded cleanly; confirmed the
`workspace_role` type and `workspace_members` table both exist
(`psql \d workspace_members`, `\dT+ workspace_role`); then verified full
reversibility with `alembic downgrade 0001` followed by `alembic upgrade
head` again, both clean.

**Prevention:** For any future Postgres-native-enum column, only call
`.create()`/`.drop()` explicitly in `downgrade()` (where `drop_table` needs
help) — never in `upgrade()`, where `create_table` already handles it.

## 2026-09-13 — Component tests failing with "multiple elements found" once more than one test rendered

**Symptom:** New Testing-Library component tests (`Nav`, register/login
pages) failed with `getMultipleElementsFoundError` on queries expecting a
single match, even though each individual test only rendered one component
instance and made straightforward assertions.

**Root cause:** `@testing-library/react`'s automatic per-test DOM cleanup
registers itself via a *global* `afterEach` — but this project's
`vitest.config.mts` never sets `test.globals: true`, so no global
`afterEach` exists for it to hook into, and cleanup silently never ran.
Every `render()` call across every test in a file kept accumulating DOM in
`document.body`, so a query written to expect one match increasingly found
several once more than one test in a `describe` block had run.

**Failed attempts:** Rewriting individual test queries to be more specific
(e.g. `getByRole` with a narrower name) briefly looked like a fix for the
*first* failure encountered, but the same class of failure kept recurring
test-by-test — the real cause was file-wide DOM accumulation, not any one
query being ambiguous.

**Fix:** Added an explicit `afterEach(() => cleanup())` (from
`@testing-library/react`) to `vitest.setup.ts`, which every test file
already loads via `test.setupFiles` — this registers cleanup once, for
every test file, regardless of the `globals` setting.

**Verification:** Full frontend suite (7 test files, 22 tests) passes
without the file-order-dependent flakiness; confirmed by running the suite
repeatedly and inspecting that only one component's DOM is ever present in
a given test's assertions.

**Prevention:** Documented directly in `vitest.setup.ts` with a comment
explaining why the explicit `afterEach(cleanup)` is required given this
project's `globals: false` config, so it isn't mistaken for dead code and
removed later.

## 2026-09-14 — Password-reset tests silently got no email, but only from the fifth test onward

**Symptom:** Two password-reset tests (`test_password_reset_invalidates_existing_sessions`,
`test_reset_token_is_single_use`) failed with "no reset link found in
captured output: ''" — the `forgot-password` call apparently sent no email
at all — while an earlier, structurally identical test
(`test_full_password_reset_flow`) passed.

**Root cause:** `app/core/rate_limit.py`'s in-process limiters are
module-level singletons, shared across the whole test session. The
`tests/conftest.py` autouse fixture that resets them before every test
(`_reset_rate_limiters`) was written for Issue #2's original three
limiters (login/register/refresh) and never updated when
`forgot_password_rate_limiter`/`reset_password_rate_limiter` were added
for the password-recovery feature in the same session. Every prior test
in the file that called `forgot-password` (four of them, several making
multiple calls) added up against the *never-reset* limiter (limit 5)
without the developer noticing, because a 429 there fails silently from
the test's point of view — `capsys` just captures nothing, which looks
identical to "the code path was never reached" rather than "it was
reached and then rejected."

**Failed attempts:** None — the empty-output symptom made the actual cause
(a 429 being returned instead of a real send) non-obvious at first glance;
the fix was found by tracing which fixture is responsible for isolating
rate-limiter state between tests and noticing the two new limiters weren't
in it.

**Fix:** Added `forgot_password_rate_limiter.reset()` and
`reset_password_rate_limiter.reset()` to `_reset_rate_limiters` in
`tests/conftest.py`.

**Verification:** All 10 `tests/test_password_reset.py` tests pass, and
the two dedicated rate-limit tests
(`test_forgot_password_is_rate_limited`, `test_reset_password_is_rate_limited`)
still correctly trip a real 429 within their own test.

**Prevention:** Any new rate limiter added to `app/core/rate_limit.py`
must be added to `tests/conftest.py`'s `_reset_rate_limiters` in the same
change — there is no automatic discovery of new limiter instances, so this
is a manual checklist item, not something a future limiter gets "for
free."

## 2026-09-14 — `frontend/lib/api-client.test.ts` failed with "Body is unusable: Body has already been read"

**Symptom:** Several `api-client.test.ts` tests failed — one with a
`ZodError` (parsing `undefined` fields), three with
`TypeError: Body is unusable: Body has already been read` — as soon as a
test called more than one `api-client` function (e.g. `register` then
`login`, or `register`/`login`/`getCurrentUser`/`logout` in sequence).

**Root cause:** `vi.fn().mockResolvedValue(jsonResponse(...))` resolves
every call to the **same** `Response` object instance. A `Response` body
is a stream that can only be consumed once — the first `await
response.json()` in the test setup (or the first api-client call) reads
it; every subsequent call to `.json()` on that same object throws. The
`ZodError` failures were a second-order symptom of the same root cause:
a test that reused the shared response across a `login` and a
`getCurrentUser` call got the *wrong* body shape for `getCurrentUser`
(the mock was configured for `{user: ...}`, but `getCurrentUser` expects
a flat user object), because one `mockResolvedValue(...)` call was being
asked to serve two endpoints with different response shapes.

**Failed attempts:** None — the fix was applied directly once the "body
already read" message made the single-shared-object cause clear.

**Fix:** Use `mockImplementation(() => Promise.resolve(jsonResponse(...)))`
instead of `mockResolvedValue(jsonResponse(...))` wherever a test calls
more than one `api-client` function — `mockImplementation` re-invokes the
factory function on every call, producing a fresh `Response` each time.
Where different endpoints in the same test need different response
shapes, branch on the request URL inside the implementation
(`fetchMock.mockImplementation((url) => url.includes("/users/me") ? ... : ...)`).

**Verification:** All previously-failing tests in
`frontend/lib/api-client.test.ts` pass; the full suite (30 tests at the
time) passes with no regressions.

**Prevention:** Default to `mockImplementation` (not `mockResolvedValue`)
for any fetch mock in this codebase that a test might call more than
once per test body — `mockResolvedValue` is only safe for a genuinely
single-call test. This is now the pattern used throughout
`api-client.test.ts`; follow it for new tests in the same file rather
than reintroducing `mockResolvedValue` for a multi-call test.

## 2026-09-14 — Per-key Redis atomicity was insufficient for a multi-dimensional rate-limit decision (design-time, ADR 0006)

**Symptom (found during adversarial architecture review, before any code
was written):** the first draft of
[ADR 0006](docs/DECISIONS/0006-redis-distributed-rate-limiting-abuse-protection.md)
designed `login`/`refresh`/`forgot-password`'s rate limiting as one
independent, atomic Redis Lua script *per dimension key* (e.g., one
script invocation for the IP bucket, a separate one for the account
bucket), reasoning that "each key's own script is atomic" was sufficient
for the combined allow/deny decision.

**Root cause:** each individual bucket's Lua script *was* correctly
atomic in isolation — but the *compound* decision spanning multiple
buckets was not. A worked scenario exposed it: two requests for the same
account from different IPs, with the account bucket down to its last
token. Request A consumes an IP token, then the account's last token.
Request B consumes a *different* IP's token, then finds the account
bucket empty and gets rejected — but its IP token was already spent on a
request that was never going to succeed. Each bucket was atomic
individually, but the compound decision wasn't atomic, so a rejection on
one dimension didn't prevent (or undo) consumption already committed on
another.

**Failed attempts:** None in the sense of a discarded code fix (this was
caught at the design stage, before implementation) — but the design
itself had shipped in ADR 0006's first draft and been reviewed once
already without this being caught, until a dedicated adversarial review
pass specifically asked "is one atomic operation per key sufficient to
guarantee a combined hierarchical limit?" and required working through a
concrete concurrent scenario rather than accepting "each piece is atomic"
as proof of the whole.

**Resolution:** redesigned as one multi-key Lua transaction *per
operation* (Redis's `EVAL script numkeys key1 key2 ... arg...` natively
supports multiple keys in one atomic invocation): read and refill every
dimension's bucket first, check all of them, and only write to *any* of
them if *all* of them pass. A rejected request writes to nothing —
check-before-write, never write-then-rollback.

**Verification:** worked through explicitly via the concurrent scenario
above (re-run against the corrected design to confirm the flaw no longer
exists) and captured as a named future regression test in ADR 0006 §17
("the multi-key compound decision never partially consumes one dimension
when another dimension rejects the request"). No automated test exists
yet — Redis has not been implemented (design-only ADR) — so this is
verified by design reasoning now and must be verified by that specific
test once implementation begins.

**Prevention/lesson:** **atomic components do not necessarily produce an
atomic workflow.** Whenever a single logical decision depends on more
than one independently-atomic piece of state, the atomicity of each
piece says nothing about the atomicity of the decision that spans them —
that requires its own explicit design (here, one transaction covering
every piece the decision depends on), not an inference from "the parts
are safe." Applies beyond Redis/Lua: the same question is worth asking
any time a change introduces multiple independently-locked or
independently-transactional resources that one business decision reads
or writes together.

## 2026-09-14 — Redis Lua scripts silently truncate fractional numbers to integers on return (Redis rate-limiting implementation, slice 1)

**Symptom (caught during implementation, before it could become a test
failure):** the ADR 0006 §8 token-bucket Lua script needs to return a
"how long until this dimension has enough tokens" value alongside the
allow/deny flag, computed in Lua as `(cost - current_tokens) /
refill_rate` — a fractional number of seconds for any sub-one-second
wait, which is the common case for this project's actual rate limits
(e.g. `login` at 5/60s means a typical retry wait is a few seconds at
most, frequently under 1).

**Root cause:** Redis's Lua-to-RESP2 reply conversion for a table
returned from `EVAL`/`EVALSHA` converts each Lua number to a Redis
*integer* reply — not a float, no rounding, just truncation toward zero
(this is documented Redis/Lua-scripting behavior, not a bug in this
project's script). A script that computed and `return`ed `{allowed,
wait_seconds}` with `wait_seconds` as a fractional value like `0.4` would
have silently come back to Python as `0` on every call where the true
wait was under one second — which, given this project's actual
configured limits, would have been *most* rejections. Nothing about this
fails loudly: the script runs, returns a result, and the bug is a wrong
number, not an exception — exactly the kind of defect a design-only
review can't catch and only shows up once real inputs are pushed through
the real script.

**Fix:** the script (`app/core/rate_limit.py`'s `_TOKEN_BUCKET_LUA`)
computes and returns `retry_after_ms` as `math.ceil(wait_seconds * 1000)`
— an integer number of *milliseconds* — instead of a fractional number of
seconds. The Python wrapper (`RedisTokenBucketLimiter.check_all()`)
divides back down to `retry_after_seconds` on the Python side, where
float division is exact. Milliseconds give enough headroom that the
Lua-side integer truncation only loses sub-millisecond precision, which
this design has no use for anyway.

**Verification:** `tests/test_redis_rate_limiter.py::test_request_beyond_capacity_is_rejected`
asserts `result.retry_after_seconds > 0` for a rejection with a
sub-one-second true wait time (`refill_rate=0.001` tokens/sec against a
capacity already at zero) — this test would have failed (or worse,
silently asserted `0 > 0` → correctly failed rather than silently passed,
but only because the assertion happens to be a strict `>`) had the script
returned raw fractional seconds instead of integer milliseconds. Also
directly inspected via `redis-cli` against a real Redis instance while
implementing, to confirm the raw integer reply, before writing the
Python-side conversion.

**Prevention/lesson:** **a value born as a Lua `number` inside a script
does not stay a JSON-like general number once it crosses the Lua→RESP
boundary in a `return`.** Any Redis Lua script that needs to hand back a
fractional value must pre-scale it into an integer unit (milliseconds,
basis points, fixed-point cents — whatever the domain supports) *inside
the script*, and unscale on the client side; there is no Lua-script
return path that preserves a float as a float to a RESP2 client. Worth
checking any time a new Lua script in this codebase returns a computed
number, not just a stored one.

## 2026-09-14 — Wiring the Redis rate limiter into endpoints made 52 previously-passing tests fail (Redis rate-limiting implementation, slice 2)

**Symptom:** immediately after wiring `RedisTokenBucketLimiter` into
`enforce_*_rate_limit` (so `login`/`register`/etc. now try the real Redis
path first), the full backend test suite went from 170/170 passing to
52 failing — almost every test that touches `register` or `login`,
including ones that don't look like they're about rate limiting at all
(`test_workspaces.py`'s setup helper registers a user first).

**Root cause:** `backend/tests/conftest.py`'s `_reset_rate_limiters`
fixture (autouse) only ever called `.reset()` on the in-process
`FixedWindowRateLimiter` instances. Once `enforce_register_rate_limit`
etc. started attempting the Redis path first, each test's `register`/
`login` calls began writing real, TTL-bound `rl:register:ip:testclient`/
`rl:login:ip:testclient` keys to the one real Redis every test in the
session shares — and nothing ever cleared them between tests. Every
`TestClient` presents the same fake host (`"testclient"`), so by the
~6th test that called `register`, that Redis-backed bucket was already
exhausted and every subsequent test's very first `register` call got a
`429` instead of the `201` it expected.

**Fix:** extended `_reset_rate_limiters` to also, after resetting the
in-process limiters, `SCAN`+`DELETE` every `rl:*` key from
`get_redis_client()` (wrapped in `try/except redis.RedisError`, since if
Redis is unreachable during a test run every `enforce_*_rate_limit` call
already falls back to the just-reset in-process limiter, so there is
nothing to clean up in that case).

**Verification:** full suite back to green (175/175 after also adding
slice 2's own new tests), re-run 3 times with no flakiness.

**Prevention/lesson:** **wiring a new backing store into existing code
paths can silently invalidate test-isolation assumptions the existing
tests never had to state explicitly.** The original `_reset_rate_limiters`
fixture's docstring already explained *why* it exists ("the TestClient
always presents the same fake client host") — that reasoning didn't
change, but the set of *state* it needed to reset silently grew the
moment a second backing store (Redis) started being written to by the
same code path. Any time a new persistent/shared backend is wired into
a function that previously only touched in-memory state, re-check every
existing "reset between tests" fixture for whether it now needs to reset
the new backend too — the old fixture passing its own tests is not
evidence it still resets *everything* the code under test now touches.

## 2026-09-14 — ADR 0006 §13's Tier B ("register fails open") would have made register unprotected by default on every deployment (Redis rate-limiting implementation, slice 2)

**Symptom (caught during design of the wiring, before writing the fail-open
branch):** ADR 0006 §13 states Tier B's policy plainly: "on Redis failure
[`register`] fails open (falls back to no additional limiting beyond
ordinary application validation)." Implementing that literally — treating
`get_redis_client() is None` (Redis never configured) the same as a
`RedisUnavailableError` raised mid-request (Redis configured but down) —
means `register` has **zero** rate limiting the instant this code ships,
in every environment that hasn't explicitly set `REDIS_URL`. That is
every environment today: local dev, CI, and any hypothetical production
deployment, since `redis_url` defaults to `None`.

**Root cause:** the ADR's Tier B language was written with a specific
scenario in mind — "a Redis blip" in a deployment that has *already*
chosen Redis-backed limiting as primary — but the same code path
(`RedisUnavailableError`, or in this case just "no client at all") is
reached by two different real-world situations that the ADR's wording
doesn't distinguish: a deployment that opted into Redis and is having a
transient outage, versus a deployment (i.e. every one so far) that
simply hasn't turned Redis on yet. ADR §13 itself flagged this exact
sub-decision as unresolved: "whether `register` should actually share
Tier A's fallback instead is a reasonable alternative... this should be
revisited once real abuse data exists" — but implementing the literal
default without revisiting it would have shipped the permissive option
as this project's actual, immediate behavior.

**Fix:** `_check_or_fallback()` (`app/core/rate_limit.py`) distinguishes
the two cases explicitly: `redis_client is None` always falls back to
`FixedWindowRateLimiter` (for every operation, `register` included,
matching this module's exact pre-slice-2 behavior when Redis isn't
configured); only a `RedisUnavailableError` raised from an actually-
configured client selects the tier-specific policy (Tier A fallback vs.
Tier B fail-open). This resolves ADR §13's explicitly-open sub-decision
in favor of safety-by-default, documented with rationale in the module
docstring, `HANDOFF.md`, and ADR 0006's "Implementation status" section
— not silently deviated from.

**Verification:**
`test_redis_configured_but_none_still_uses_fallback_for_register` and
`test_redis_unavailable_fails_open_for_register`
(`tests/test_rate_limit_wiring.py`) assert the two cases produce
different behavior; also verified live against the real Docker Compose
stack — `register` stayed rate-limited with `REDIS_URL` unset, and
specifically failed open (7/7 succeeded past the base limit of 5) only
once Redis was actually started and then stopped mid-session.

**Prevention/lesson:** **an ADR's stated default for a genuine outage
scenario is not automatically the right default for "this capability has
never been turned on yet."** When a failure-handling branch is reached by
both "an enabled dependency broke" and "this dependency was never
enabled," check whether the *safe* default (do what happens today) and
the *documented* default (what the design says for an outage) actually
agree before wiring the literal design into code — here they didn't, and
the ADR had already flagged it as an open decision precisely because it
hadn't been resolved yet.

## 2026-09-24 — A new "zero extractable content" safety check broke two existing PDF test fixtures, correctly

**Symptom:** After adding Slice 3.7's embedding stage, three tests that
had passed unchanged through Slices 3.4/3.5/3.6 started failing:
`test_pdf_processes_to_ready_with_correct_page_count`,
`test_pdf_reaches_ready_with_persisted_chunks`, and
`test_processing_an_already_ready_document_is_rejected_with_409` all
asserted `status == "READY"` but got `status == "FAILED"`.

**Root cause:** Both `tests/test_document_processing.py` and
`tests/test_document_lifecycle.py` share a PDF fixture built via
`pypdf.PdfWriter().add_blank_page(width=200, height=200)` — a real,
valid, single/multi-page PDF, but with **no text content on any page**
(`add_blank_page` creates an empty page; it doesn't write anything into
it). Every test through Slice 3.6 only ever asserted `page_count` and
lifecycle `status`, never chunk *content*, so this was invisible: a
blank-page PDF extracts to sections with empty text, and
`chunking.py`'s own `_chunk_section()` correctly returns `[]` for an
empty section — so this fixture had *always* chunked to zero rows, it
just never mattered until Slice 3.7 added a real safety check
(`process_document()`: a document with zero persisted chunks has
nothing to embed and can never be retrieved, so it's now reported as an
honest `FAILED` rather than silently reaching `READY`). The new check is
correct; the fixture's long-standing "blank" content was the actual gap,
newly exposed rather than newly introduced.

**Failed attempts:** Considered weakening or removing the zero-chunk
check to make the existing fixtures pass unmodified — rejected: a
document that silently reaches `READY` with zero retrievable chunks is
a worse, more confusing production outcome (looks successful, is
functionally useless) than an honest, generic `FAILED`. The check itself
was correct; only the fixture's fitness for the tests using it was in
question. Considered adding `reportlab` (or another PDF-generation
library) as a new test dependency to draw real text easily — rejected as
unnecessary: this project's own "don't introduce a dependency unless
necessary" convention, and a byte-correct minimal PDF is small and
well-understood enough to hand-build.

**Fix:** Replaced `_blank_pdf()` in both test files with
`_pdf_with_text()` — a hand-built PDF (catalog/pages/page/content-
stream/font objects, `xref` table, `trailer`) whose content stream
contains a real `Tj` text-showing operator, so `pypdf` extracts genuine
text from it. Byte offsets for the `xref` table are computed in Python
as each object is appended, not hand-copied/hardcoded, specifically to
avoid introducing a second, worse class of hard-to-debug bug (an
off-by-one in a hand-maintained offset table) while fixing the first.
Verified independently via a standalone `pypdf.PdfReader` round-trip
(`extract_text() == "Hello World"`) before wiring it into either test
file. `PdfWriter`/`io` imports were removed from both files once nothing
else used them.

**Verification:** All three previously-failing tests pass again,
asserting `READY` correctly. Every other test using the same shared
`_PDF_BYTES` constant (rate-limiting, crash-safety, authorization,
audit-event tests — none of which cared about final chunk content) was
re-run and remained unaffected. Full backend suite: 527/527 passing, 3
consecutive runs.

**Prevention/lesson:** **a "successful" test fixture that was never
inspected past a coarse-grained assertion (status/page_count only) can
be hiding a degenerate input** (here: real-but-empty content) that a
later, more thorough downstream check will correctly reject. When a new
safety/correctness check starts failing a previously-green test, verify
which side is actually wrong — the new check, or the old fixture's
fitness for what it's now being asked to prove — before weakening the
check. Also: when constructing a binary file format by hand for a test
fixture, compute any offset/length table programmatically rather than
hardcoding it, so the fixture-construction code itself can't introduce
the exact class of subtle bug the check under test is meant to catch.
