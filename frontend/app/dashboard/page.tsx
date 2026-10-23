"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  FileText,
  MessageSquareText,
  Settings as SettingsIcon,
  Users,
} from "lucide-react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";

const QUICK_ACTIONS = [
  {
    href: "/documents",
    icon: FileText,
    title: "Documents",
    description: "Upload files and track processing status.",
  },
  {
    href: "/chat",
    icon: MessageSquareText,
    title: "Chat",
    description: "Ask grounded questions with citations.",
  },
  {
    href: "/workspace",
    icon: Users,
    title: "Workspace",
    description: "Manage members, roles and workspaces.",
  },
  {
    href: "/settings",
    icon: SettingsIcon,
    title: "Settings",
    description: "Review your account and active sessions.",
  },
];

/** Real counts pulled from the already-implemented list endpoints --
 * never a fabricated metric. Loads best-effort; a failure here just
 * hides the stat row rather than blocking the rest of the dashboard. */
function WorkspaceStats({ workspaceId }: { workspaceId: string }) {
  const [counts, setCounts] = useState<{ documents: number; conversations: number } | null>(null);

  const load = useCallback(async () => {
    try {
      const [documents, conversations] = await Promise.all([
        api.listDocuments(workspaceId),
        api.listConversations(workspaceId),
      ]);
      setCounts({ documents: documents.length, conversations: conversations.length });
    } catch {
      setCounts(null);
    }
  }, [workspaceId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  if (!counts) return null;

  return (
    <div className="flex flex-wrap gap-6 border-t border-slate-100 pt-4">
      <div>
        <p className="text-2xl font-semibold tracking-tight text-slate-950">{counts.documents}</p>
        <p className="text-muted-foreground text-xs">
          document{counts.documents === 1 ? "" : "s"}
        </p>
      </div>
      <div>
        <p className="text-2xl font-semibold tracking-tight text-slate-950">
          {counts.conversations}
        </p>
        <p className="text-muted-foreground text-xs">
          conversation{counts.conversations === 1 ? "" : "s"}
        </p>
      </div>
    </div>
  );
}

function DashboardContent() {
  const { user } = useAuth();
  const { currentWorkspace, workspaces, isLoading } = useWorkspace();

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Welcome back{user ? `, ${user.email}` : ""}</CardTitle>
          <CardDescription>
            Workspace overview. Upload documents and ask questions from the Documents and Chat
            pages.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {isLoading ? (
            <p className="text-muted-foreground text-sm">Loading workspaces…</p>
          ) : currentWorkspace ? (
            <div className="flex flex-col gap-4 text-sm">
              <div className="flex flex-col gap-1">
                <p>
                  Current workspace: <span className="font-medium">{currentWorkspace.name}</span>{" "}
                  <span className="text-muted-foreground">({currentWorkspace.my_role})</span>
                </p>
                <p className="text-muted-foreground">
                  You belong to {workspaces.length} workspace{workspaces.length === 1 ? "" : "s"}.
                </p>
              </div>
              <WorkspaceStats workspaceId={currentWorkspace.id} />
              <Link href="/workspace" className="w-fit">
                <Button size="sm" variant="outline">
                  Manage workspaces
                </Button>
              </Link>
            </div>
          ) : (
            <div className="flex flex-col gap-2 text-sm">
              <p className="text-muted-foreground">You don&apos;t belong to a workspace yet.</p>
              <Link href="/workspace">
                <Button size="sm">Create a workspace</Button>
              </Link>
            </div>
          )}
        </CardContent>
      </Card>

      {currentWorkspace && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-slate-700">Quick actions</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {QUICK_ACTIONS.map(({ href, icon: Icon, title, description }) => (
              <Link
                key={href}
                href={href}
                className="group flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-md"
              >
                <div className="flex size-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700 transition group-hover:bg-indigo-600 group-hover:text-white">
                  <Icon className="size-4" aria-hidden="true" />
                </div>
                <div>
                  <p className="flex items-center gap-1 text-sm font-semibold text-slate-950">
                    {title}
                    <ArrowRight
                      className="size-3.5 -translate-x-1 opacity-0 transition group-hover:translate-x-0 group-hover:opacity-100"
                      aria-hidden="true"
                    />
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs leading-5">{description}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}
