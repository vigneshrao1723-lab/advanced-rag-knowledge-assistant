"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/documents", label: "Documents" },
  { href: "/chat", label: "Chat" },
  { href: "/collections", label: "Collections" },
  { href: "/search", label: "Search" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const { user, isAuthenticated, logout } = useAuth();
  const { workspaces, currentWorkspace, setCurrentWorkspaceId } = useWorkspace();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <header className="border-border bg-background sticky top-0 z-10 border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4">
        <Link href="/" className="text-sm font-semibold whitespace-nowrap">
          Advanced RAG Knowledge Assistant
        </Link>
        {isAuthenticated ? (
          <>
            <nav className="flex items-center gap-1">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-md px-3 py-1.5 text-sm transition-colors"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
            <div className="flex items-center gap-3">
              {workspaces.length > 0 && (
                <label className="sr-only" htmlFor="workspace-selector">
                  Current workspace
                </label>
              )}
              {workspaces.length > 0 && (
                <select
                  id="workspace-selector"
                  className="border-input bg-background rounded-md border px-2 py-1 text-sm"
                  value={currentWorkspace?.id ?? ""}
                  onChange={(e) => setCurrentWorkspaceId(e.target.value)}
                >
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              )}
              <span className="text-muted-foreground hidden text-sm sm:inline">{user?.email}</span>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                Log out
              </Button>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="text-muted-foreground hover:text-foreground rounded-md px-3 py-1.5 text-sm transition-colors"
            >
              Log in
            </Link>
            <Link href="/register">
              <Button size="sm">Register</Button>
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}
