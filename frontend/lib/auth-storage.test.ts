import { beforeEach, describe, expect, it } from "vitest";

import { clearAuth, loadAuth, saveAuth, type StoredAuth } from "@/lib/auth-storage";

const sample: StoredAuth = {
  accessToken: "access-token",
  refreshToken: "refresh-token",
  user: { id: "user-1", email: "user@example.com", created_at: "2026-01-01T00:00:00Z" },
};

describe("auth-storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns null when nothing is stored", () => {
    expect(loadAuth()).toBeNull();
  });

  it("round-trips saved auth", () => {
    saveAuth(sample);

    expect(loadAuth()).toEqual(sample);
  });

  it("clearAuth removes stored auth", () => {
    saveAuth(sample);

    clearAuth();

    expect(loadAuth()).toBeNull();
  });

  it("returns null for corrupted JSON instead of throwing", () => {
    window.localStorage.setItem("auth", "not-json{{{");

    expect(loadAuth()).toBeNull();
  });
});
