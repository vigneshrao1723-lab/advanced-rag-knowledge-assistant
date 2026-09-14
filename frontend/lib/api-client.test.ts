import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api-client";

function setCsrfCookie(value: string): void {
  document.cookie = `csrf_token=${value}; path=/`;
}

function clearCookies(): void {
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SAMPLE_USER = { id: "u1", email: "user@example.com", created_at: "2026-01-01T00:00:00Z" };

describe("api-client — cookie/CSRF request plumbing", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setCsrfCookie("test-csrf-value");
    // `mockImplementation` (not `mockResolvedValue`) so each call gets a
    // fresh `Response` — a `Response` body can only be read once, and
    // several tests below call multiple api-client functions per test.
    fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ user: SAMPLE_USER }, 201)));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearCookies();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  function lastRequestInit(): RequestInit {
    const call = fetchMock.mock.calls.at(-1);
    return call?.[1] as RequestInit;
  }

  it("always sends credentials: include, even though frontend and backend are different origins", async () => {
    await api.login("user@example.com", "password");

    expect(lastRequestInit().credentials).toBe("include");
  });

  it("attaches the CSRF header (sourced from the cookie) on state-changing requests", async () => {
    await api.login("user@example.com", "password");

    const headers = lastRequestInit().headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("test-csrf-value");
  });

  it("does not attach a CSRF header on safe GET requests", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(SAMPLE_USER)));
    await api.getCurrentUser();

    const headers = lastRequestInit().headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("never sets an Authorization header on any request — auth is cookie-only", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/users/me")) return Promise.resolve(jsonResponse(SAMPLE_USER));
      if (url.includes("/workspaces")) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(jsonResponse({ user: SAMPLE_USER }, 201));
    });
    await api.register("user@example.com", "password");
    await api.login("user@example.com", "password");
    await api.getCurrentUser();
    await api.listWorkspaces();

    for (const call of fetchMock.mock.calls) {
      const headers = call[1].headers as Record<string, string>;
      expect(headers.Authorization).toBeUndefined();
      expect(headers.authorization).toBeUndefined();
    }
  });

  it("register/login responses contain only the user — no tokens in the body", async () => {
    const registerResult = await api.register("user@example.com", "password");
    const loginResult = await api.login("user@example.com", "password");

    for (const result of [registerResult, loginResult]) {
      expect(result).toEqual({ user: SAMPLE_USER });
      expect(Object.keys(result)).toEqual(["user"]);
    }
  });

  it("refresh and logout send no request body — the refresh token lives only in its cookie", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ user: SAMPLE_USER }));
    await api.logout();

    expect(lastRequestInit().body).toBeUndefined();
  });

  it("never writes to localStorage or sessionStorage during register/login/getCurrentUser/logout", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/users/me")) return Promise.resolve(jsonResponse(SAMPLE_USER));
      return Promise.resolve(jsonResponse({ user: SAMPLE_USER }, 201));
    });
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    await api.register("user@example.com", "password");
    await api.login("user@example.com", "password");
    await api.getCurrentUser();
    await api.logout();

    expect(setItemSpy).not.toHaveBeenCalled();
    setItemSpy.mockRestore();
  });

  it("retries once after a successful refresh on a 401 from an ordinary endpoint", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ error: { code: "http_error", message: "no" } }, 401))
      .mockResolvedValueOnce(jsonResponse({ user: SAMPLE_USER })) // refresh
      .mockResolvedValueOnce(jsonResponse([]));

    await api.listWorkspaces();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/auth/refresh");
  });

  it("does not attempt a refresh when getCurrentUser itself gets a 401 (initial auth check)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ error: { code: "http_error", message: "no" } }, 401)
    );

    await expect(api.getCurrentUser()).rejects.toThrow();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("forgotPassword sends credentials, a CSRF header, and never a token", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ message: "generic message" }))
    );

    const result = await api.forgotPassword("user@example.com");

    expect(result).toEqual({ message: "generic message" });
    expect(lastRequestInit().credentials).toBe("include");
    const headers = lastRequestInit().headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("test-csrf-value");
    expect(headers.Authorization).toBeUndefined();
    expect(JSON.parse(lastRequestInit().body as string)).toEqual({ email: "user@example.com" });
  });

  it("forgotPassword does not attempt a refresh-and-retry on a 401", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ error: { code: "http_error", message: "no" } }, 401)
    );

    await expect(api.forgotPassword("user@example.com")).rejects.toThrow();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("resetPassword sends the token and new password, with credentials and a CSRF header, and never a token in the response", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));

    await api.resetPassword("raw-reset-token", "a brand new password");

    expect(lastRequestInit().credentials).toBe("include");
    const headers = lastRequestInit().headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("test-csrf-value");
    expect(headers.Authorization).toBeUndefined();
    expect(JSON.parse(lastRequestInit().body as string)).toEqual({
      token: "raw-reset-token",
      new_password: "a brand new password",
    });
  });

  it("resetPassword does not attempt a refresh-and-retry on a 401", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ error: { code: "http_error", message: "no" } }, 401)
    );

    await expect(api.resetPassword("raw-reset-token", "a brand new password")).rejects.toThrow();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("never writes to localStorage or sessionStorage during forgotPassword/resetPassword", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("reset-password")) return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(jsonResponse({ message: "generic message" }));
    });
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    await api.forgotPassword("user@example.com");
    await api.resetPassword("raw-reset-token", "a brand new password");

    expect(setItemSpy).not.toHaveBeenCalled();
    setItemSpy.mockRestore();
  });
});
