/**
 * Token persistence for the browser tab.
 *
 * Tokens are delivered in the JSON response body, not cookies (see
 * docs/DECISIONS/0003-authentication-session-architecture.md's "what
 * remains to be finalized" resolved here: response-body delivery keeps the
 * API client-agnostic and avoids SameSite/Secure cookie complexity for
 * local HTTP dev). `localStorage` is a pragmatic choice for this issue's
 * scope — no XSS-hardening (CSP, etc.) is in place yet, so this is a known
 * limitation, not a claim that this is maximally secure (see HANDOFF.md).
 */

export interface StoredUser {
  id: string;
  email: string;
  created_at: string;
}

export interface StoredAuth {
  accessToken: string;
  refreshToken: string;
  user: StoredUser;
}

const STORAGE_KEY = "auth";

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function loadAuth(): StoredAuth | null {
  if (!isBrowser()) return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredAuth;
  } catch {
    return null;
  }
}

export function saveAuth(auth: StoredAuth): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
  } catch {
    // Best-effort only (e.g. private browsing storage limits).
  }
}

export function clearAuth(): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Best-effort only.
  }
}
