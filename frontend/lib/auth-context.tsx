"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import * as api from "@/lib/api-client";
import type { User } from "@/lib/schemas";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  register: (email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Auth state lives entirely in HttpOnly cookies (ADR 0005) — there is
    // nothing for JavaScript to read on mount, by design. Instead, ask the
    // backend who (if anyone) the current cookies authenticate as. This
    // call also bootstraps the CSRF cookie as a side effect (the backend
    // sets one on any response that doesn't already have one), so it runs
    // before any page — including /login and /register — could need one.
    (async () => {
      try {
        const currentUser = await api.getCurrentUser();
        setUser(currentUser);
      } catch {
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const { user: registeredUser } = await api.register(email, password);
    setUser(registeredUser);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { user: loggedInUser } = await api.login(email, password);
    setUser(loggedInUser);
  }, []);

  const logout = useCallback(async () => {
    await api.logout().catch(() => {
      // Logging out is best-effort regardless of network outcome — the
      // client-side session always ends immediately either way.
    });
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
