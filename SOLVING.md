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
