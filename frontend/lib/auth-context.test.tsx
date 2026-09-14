import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/lib/auth-context";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SAMPLE_USER = { id: "u1", email: "user@example.com", created_at: "2026-01-01T00:00:00Z" };

describe("AuthProvider — cookie-only auth state (no storage)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("determines auth state on mount via a real request, not by reading storage", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SAMPLE_USER));

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user?.email).toBe(SAMPLE_USER.email);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/users/me");
    expect((init as RequestInit).credentials).toBe("include");
  });

  it("treats a 401 on mount as logged out and does not attempt a refresh first", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "http_error", message: "not authenticated" } }, 401)
    );

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    // Exactly the one mount-time check — no extra refresh attempt for an
    // anonymous visitor who was never logged in.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("a full login → logout cycle never writes to localStorage or sessionStorage", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "http_error", message: "not authenticated" } }, 401)
    );
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    fetchMock.mockResolvedValue(jsonResponse({ user: SAMPLE_USER }));
    await act(async () => {
      await result.current.login("user@example.com", "password");
    });
    expect(result.current.user?.email).toBe(SAMPLE_USER.email);
    expect(result.current.isAuthenticated).toBe(true);

    await act(async () => {
      await result.current.logout();
    });
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);

    expect(setItemSpy).not.toHaveBeenCalled();
    setItemSpy.mockRestore();
  });
});
