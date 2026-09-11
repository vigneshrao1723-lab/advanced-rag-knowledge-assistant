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

*No entries yet. This repository is in its documentation/initialization
phase (see `PROJECT_STATE.md`) — no implementation work has occurred that
would produce a hard-problem entry. The first entry will be added when one
is genuinely warranted.*
