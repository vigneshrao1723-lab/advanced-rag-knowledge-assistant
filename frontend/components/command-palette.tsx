"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import {
  Command,
  FileText,
  FolderOpen,
  LayoutDashboard,
  MessageSquareText,
  Search,
  Settings,
  Users,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";

interface PaletteAction {
  id: string;
  label: string;
  icon: typeof Search;
  run: () => void;
}

/** Global `Ctrl+K`/`Cmd+K` command palette (GitHub Issue #41). Mounted
 * once in `AppShell` so it's available from any authenticated page.
 * Deliberately no new dependency (`cmdk` etc.) -- a small, self-
 * contained filter list covers this feature's actual scope, matching
 * this codebase's existing preference for plain components over
 * pulling in a library for a modest feature. */
export function CommandPalette() {
  const { isAuthenticated } = useAuth();
  const { workspaces, currentWorkspace, setCurrentWorkspaceId } = useWorkspace();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const close = useCallback(() => {
    setIsOpen(false);
    setQuery("");
    setSelectedIndex(0);
  }, []);

  const open = useCallback(() => {
    setIsOpen(true);
    setSelectedIndex(0);
  }, []);

  const runAction = useCallback(
    (action: PaletteAction) => {
      action.run();
      close();
    },
    [close]
  );

  useEffect(() => {
    if (!isAuthenticated) return;

    function handleKeyDown(event: KeyboardEvent) {
      // A modifier-chord shortcut never collides with normal typing, so
      // it's safe to open even while a text input/textarea already has
      // focus (every real command palette -- GitHub, Linear, Notion --
      // behaves this way; there is no existing Escape/Ctrl/Cmd handler
      // anywhere else in this app for this to conflict with).
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setIsOpen((wasOpen) => {
          const willOpen = !wasOpen;
          if (willOpen) setSelectedIndex(0);
          return willOpen;
        });
        return;
      }
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isAuthenticated]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  const actions = useMemo<PaletteAction[]>(() => {
    const navigationActions: PaletteAction[] = [
      {
        id: "dashboard",
        label: "Go to Dashboard",
        icon: LayoutDashboard,
        run: () => router.push("/dashboard"),
      },
      {
        id: "documents",
        label: "Go to Documents",
        icon: FileText,
        run: () => router.push("/documents"),
      },
      {
        id: "collections",
        label: "Go to Collections",
        icon: FolderOpen,
        run: () => router.push("/collections"),
      },
      { id: "search", label: "Go to Search", icon: Search, run: () => router.push("/search") },
      {
        id: "chat",
        label: "Go to Chat (new chat)",
        icon: MessageSquareText,
        run: () => router.push("/chat"),
      },
      {
        id: "settings",
        label: "Go to Settings",
        icon: Settings,
        run: () => router.push("/settings"),
      },
      {
        id: "workspace",
        label: "Go to Workspace settings",
        icon: Users,
        run: () => router.push("/workspace"),
      },
    ];
    const switchWorkspaceActions: PaletteAction[] = workspaces
      .filter((workspace) => workspace.id !== currentWorkspace?.id)
      .map((workspace) => ({
        id: `switch-workspace-${workspace.id}`,
        label: `Switch workspace to "${workspace.name}"`,
        icon: Users,
        run: () => setCurrentWorkspaceId(workspace.id),
      }));
    return [...navigationActions, ...switchWorkspaceActions];
  }, [router, workspaces, currentWorkspace, setCurrentWorkspaceId]);

  const filteredActions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return actions;
    return actions.filter((action) => action.label.toLowerCase().includes(normalizedQuery));
  }, [actions, query]);

  function handleQueryChange(value: string) {
    setQuery(value);
    setSelectedIndex(0);
  }

  function handleInputKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((index) => Math.min(index + 1, filteredActions.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const action = filteredActions[selectedIndex];
      if (action) runAction(action);
    }
  }

  if (!isAuthenticated) return null;

  return (
    <>
      <button
        type="button"
        onClick={open}
        aria-label="Open command palette"
        title="Open command palette (Ctrl+K)"
        className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-medium text-slate-600 shadow-lg transition hover:border-indigo-300 hover:text-indigo-700"
      >
        <Command className="size-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">Quick actions</span>
        <kbd className="hidden rounded border border-slate-200 bg-slate-50 px-1 text-[10px] sm:inline">
          Ctrl K
        </kbd>
      </button>

      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/40 px-4 pt-[15vh]"
          onClick={close}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            className="w-full max-w-lg overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
              <Search className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
              <label htmlFor="command-palette-input" className="sr-only">
                Search actions
              </label>
              <input
                id="command-palette-input"
                ref={inputRef}
                value={query}
                onChange={(event) => handleQueryChange(event.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="Type a command or search…"
                className="w-full border-none text-sm outline-none"
              />
            </div>
            <ul role="listbox" aria-label="Actions" className="max-h-80 overflow-y-auto p-2">
              {filteredActions.length === 0 ? (
                <li className="px-3 py-6 text-center text-sm text-slate-400">
                  No matching actions.
                </li>
              ) : (
                filteredActions.map((action, index) => {
                  const Icon = action.icon;
                  return (
                    <li key={action.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={index === selectedIndex}
                        onMouseEnter={() => setSelectedIndex(index)}
                        onClick={() => runAction(action)}
                        className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                          index === selectedIndex
                            ? "bg-indigo-50 text-indigo-800"
                            : "text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        <Icon className="size-4 shrink-0" aria-hidden="true" />
                        {action.label}
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
