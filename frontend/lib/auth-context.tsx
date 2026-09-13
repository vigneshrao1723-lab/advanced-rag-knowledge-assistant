"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import * as api from "@/lib/api-client";
import { clearAuth, loadAuth, saveAuth } from "@/lib/auth-storage";
import type { TokenResponse, User } from "@/lib/schemas";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  register: (email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function applyTokens(tokens: TokenResponse): User {
  saveAuth({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    user: tokens.user,
  });
  return tokens.user;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Reading localStorage must be deferred to after mount (it isn't
    // available during SSR) — this is the standard client-only
    // initialization pattern, not a data race the lint rule is guarding
    // against.
    const stored = loadAuth();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUser(stored?.user ?? null);
    setIsLoading(false);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const tokens = await api.register(email, password);
    setUser(applyTokens(tokens));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.login(email, password);
    setUser(applyTokens(tokens));
  }, []);

  const logout = useCallback(async () => {
    const stored = loadAuth();
    if (stored) {
      await api.logout(stored.refreshToken).catch(() => {
        // Logging out is best-effort client-side regardless of network
        // outcome — the local session always ends immediately.
      });
    }
    clearAuth();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, isAuthenticated: user !== null, register, login, logout }),
    [user, isLoading, register, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
