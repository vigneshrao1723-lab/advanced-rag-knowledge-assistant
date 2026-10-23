import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";

/** Shared centered frame for the auth screens (login/register/forgot/reset
 * password) — purely layout, no form logic, so each page keeps its own
 * Card/content untouched. Centers vertically within the viewport below the
 * nav instead of leaving the card pinned to the top with dead space below. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col items-center justify-center px-4 py-10">
      <Link
        href="/"
        aria-label="Advanced RAG Knowledge Assistant"
        className="group mb-8 flex items-center gap-3"
      >
        <span className="flex size-9 items-center justify-center rounded-xl bg-slate-950 text-white shadow-sm transition group-hover:bg-indigo-700">
          <ArrowRight className="size-5 -rotate-45" aria-hidden="true" />
        </span>
        <span className="text-sm font-semibold tracking-tight text-slate-950">RAG Workspace</span>
      </Link>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
