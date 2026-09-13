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
