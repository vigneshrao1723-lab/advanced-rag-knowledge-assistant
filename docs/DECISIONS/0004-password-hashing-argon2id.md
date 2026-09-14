# 0004. Password hashing: Argon2id via `argon2-cffi`

**Status:** Accepted
**Date:** 2026-09-12

## Context

[ADR 0003](0003-authentication-session-architecture.md) and
`docs/SECURITY.md` ("Authentication & authorization") require "a modern,
salted algorithm" for password hashing but explicitly deferred the exact
choice to implementation time (Issue #2). A choice was needed before
registration/login could be implemented.

## Decision

Passwords are hashed with **Argon2id**, via the `argon2-cffi` library
(`app/core/security.py`), using the library's own default cost parameters
(time cost, memory cost, parallelism) rather than hand-tuned values.

## Alternatives considered

- **bcrypt** — a long-standing, still-reasonable choice, but Argon2id is
  the current OWASP-recommended default and has no 72-byte input
  truncation footgun that bcrypt has.
- **PBKDF2** — rejected: weaker against GPU/ASIC-accelerated attacks than
  Argon2id at equivalent settings; only still recommended by OWASP when
  FIPS-140 compliance is required, which this project does not need.
- **scrypt** — a reasonable alternative to Argon2id; not chosen because
  Argon2id is the more widely adopted current default and `argon2-cffi` is
  a small, actively maintained, purpose-built binding (no need to reach for
  a lower-level KDF API).
- **Hand-tuning Argon2 cost parameters** — deferred. The library's defaults
  are reasonable for this project's current scale; revisit with measured
  hashing latency / infrastructure constraints if this ever becomes a real
  operational bottleneck, rather than guessing at "better" numbers now.

## Consequences

- `argon2-cffi` is a new backend dependency (`app/core/security.py`:
  `hash_password` / `verify_password`).
- Password hashes are opaque Argon2id strings (algorithm, cost parameters,
  salt, and hash all self-encoded in one string) — no separate salt column
  is needed on `users`.
- If Argon2's default cost parameters are later found inadequate (measured,
  not assumed), that is a new ADR, not a silent change — and would need a
  migration strategy for already-hashed passwords (rehash-on-next-login is
  the standard approach, not a bulk rehash).
