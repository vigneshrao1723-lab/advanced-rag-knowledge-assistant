/**
 * Reads the CSRF double-submit cookie (ADR 0005). Unlike the access/refresh
 * cookies, this one is deliberately *not* HttpOnly — the whole point of the
 * double-submit pattern is that JavaScript reads it and echoes it back as
 * a request header, which a cross-site attacker (who can trigger the
 * request but not read this origin's cookies) cannot do.
 */
const CSRF_COOKIE_NAME = "csrf_token";

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;

  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${CSRF_COOKIE_NAME}=`));
  if (!match) return null;

  return decodeURIComponent(match.slice(CSRF_COOKIE_NAME.length + 1));
}
