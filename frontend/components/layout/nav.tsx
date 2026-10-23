"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Menu, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/documents", label: "Documents" },
  { href: "/collections", label: "Collections" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Chat" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const { user, isAuthenticated, logout } = useAuth();
  const { workspaces, currentWorkspace, setCurrentWorkspaceId } = useWorkspace();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  async function handleLogout() {
    await logout();
    setMobileOpen(false);
    router.push("/login");
  }

  const navLinkClass =
    "rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500";

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
      <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" aria-label="Advanced RAG Knowledge Assistant" className="group flex shrink-0 items-center gap-3" onClick={() => setMobileOpen(false)}>
          <span className="flex size-9 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm transition group-hover:bg-indigo-700">
            <ArrowRight className="size-5 -rotate-45" aria-hidden="true" />
          </span>
          <span className="flex flex-col">
            <span className="text-sm font-semibold tracking-tight text-slate-950">RAG Workspace</span>
            <span className="hidden text-[10px] font-medium tracking-[0.13em] text-slate-500 sm:block">KNOWLEDGE, WITH EVIDENCE</span>
          </span>
        </Link>

        {isAuthenticated ? (
          <>
            <nav aria-label="Main navigation" className="hidden items-center gap-1 lg:flex">
              {NAV_LINKS.map((link) => (
                <Link key={link.href} href={link.href} className={navLinkClass}>{link.label}</Link>
              ))}
            </nav>
            <div className="hidden items-center gap-3 lg:flex">
              {workspaces.length > 0 && (
                <label className="sr-only" htmlFor="workspace-selector">Current workspace</label>
              )}
              {workspaces.length > 0 && (
                <select
                  id="workspace-selector"
                  className="max-w-44 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                  value={currentWorkspace?.id ?? ""}
                  onChange={(e) => setCurrentWorkspaceId(e.target.value)}
                >
                  {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
              )}
              <span className="hidden max-w-48 truncate text-xs text-slate-500 xl:inline">{user?.email}</span>
              <Button variant="outline" size="sm" onClick={handleLogout}>Log out</Button>
            </div>
          </>
        ) : (
          <div className="hidden items-center gap-3 sm:flex">
            <Link href="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition hover:text-slate-950">Log in</Link>
            <Link href="/register" className="inline-flex items-center rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2">Register</Link>
          </div>
        )}

        <button
          type="button"
          className="inline-flex size-10 items-center justify-center rounded-xl border border-slate-200 text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 sm:hidden"
          aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? <X className="size-5" aria-hidden="true" /> : <Menu className="size-5" aria-hidden="true" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-slate-200 bg-white px-4 py-4 sm:hidden">
          {isAuthenticated ? (
            <div className="flex flex-col gap-1">
              {workspaces.length > 0 && (
                <select
                  aria-label="Current workspace"
                  className="mb-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                  value={currentWorkspace?.id ?? ""}
                  onChange={(e) => setCurrentWorkspaceId(e.target.value)}
                >
                  {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
              )}
              {NAV_LINKS.map((link) => (
                <Link key={link.href} href={link.href} className={navLinkClass} onClick={() => setMobileOpen(false)}>{link.label}</Link>
              ))}
              <div className="mt-2 border-t border-slate-100 pt-3">
                <p className="truncate px-3 pb-2 text-xs text-slate-500">{user?.email}</p>
                <Button variant="outline" size="sm" className="w-full" onClick={handleLogout}>Log out</Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <Link href="/login" className={navLinkClass} onClick={() => setMobileOpen(false)}>Log in</Link>
              <Link href="/register" className="rounded-xl bg-slate-950 px-3 py-2.5 text-sm font-semibold text-white" onClick={() => setMobileOpen(false)}>Register</Link>
            </div>
          )}
        </div>
      )}
    </header>
  );
}
