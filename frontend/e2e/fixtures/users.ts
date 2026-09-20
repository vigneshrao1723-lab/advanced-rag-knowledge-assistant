/** A distinct, unlikely-to-collide email per test/run — mirrors the
 * `_unique_email()` helper the backend's own pytest suite already uses
 * (`backend/tests/test_auth.py`). Never a real address; `example.com`
 * never accepts mail. */
export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

/** Meets the application's own minimum (8 characters, `lib/schemas.ts`). */
export const TEST_PASSWORD = "correct horse battery staple";
export const TEST_PASSWORD_AFTER_RESET = "a brand new stronger password";
