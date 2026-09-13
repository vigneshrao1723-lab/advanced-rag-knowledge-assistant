"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

import * as api from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { Workspace } from "@/lib/schemas";

const CURRENT_WORKSPACE_STORAGE_KEY = "current_workspace_id";

interface WorkspaceContextValue {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  isLoading: boolean;
  setCurrentWorkspaceId: (id: string) => void;
  refresh: () => Promise<void>;
  createWorkspace: (name: string) => Promise<Workspace>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspaceId, setCurrentWorkspaceIdState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setWorkspaces([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const list = await api.listWorkspaces();
      setWorkspaces(list);
      setCurrentWorkspaceIdState((current) => {
        if (current && list.some((w) => w.id === current)) return current;
        const stored = window.localStorage.getItem(CURRENT_WORKSPACE_STORAGE_KEY);
        if (stored && list.some((w) => w.id === stored)) return stored;
        return list[0]?.id ?? null;
      });
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    // Standard fetch-on-mount/on-dependency-change pattern (no
    // React-Query/SWR dependency is warranted for this issue's scope) —
    // `refresh` itself guards against setting state after the component's
    // inputs have changed via its own `isAuthenticated` check.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const setCurrentWorkspaceId = useCallback((id: string) => {
    setCurrentWorkspaceIdState(id);
    try {
      window.localStorage.setItem(CURRENT_WORKSPACE_STORAGE_KEY, id);
    } catch {
      // Best-effort only.
    }
  }, []);

  const createWorkspace = useCallback(
    async (name: string) => {
      const workspace = await api.createWorkspace(name);
      setWorkspaces((prev) => [...prev, workspace]);
      setCurrentWorkspaceId(workspace.id);
      return workspace;
    },
    [setCurrentWorkspaceId]
  );

  const currentWorkspace = useMemo(
    () => workspaces.find((w) => w.id === currentWorkspaceId) ?? null,
    [workspaces, currentWorkspaceId]
  );

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      workspaces,
      currentWorkspace,
      isLoading,
      setCurrentWorkspaceId,
      refresh,
      createWorkspace,
    }),
    [workspaces, currentWorkspace, isLoading, setCurrentWorkspaceId, refresh, createWorkspace]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within a WorkspaceProvider");
  return ctx;
}
