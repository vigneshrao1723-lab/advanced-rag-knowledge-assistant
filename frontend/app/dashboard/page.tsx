"use client";

import Link from "next/link";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { useWorkspace } from "@/lib/workspace-context";

function DashboardContent() {
  const { user } = useAuth();
  const { currentWorkspace, workspaces, isLoading } = useWorkspace();

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Welcome back{user ? `, ${user.email}` : ""}</CardTitle>
          <CardDescription>
            Workspace overview. Documents, chat, and search land in later issues.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-muted-foreground text-sm">Loading workspaces…</p>
          ) : currentWorkspace ? (
            <div className="flex flex-col gap-2 text-sm">
              <p>
                Current workspace: <span className="font-medium">{currentWorkspace.name}</span>{" "}
                <span className="text-muted-foreground">({currentWorkspace.my_role})</span>
              </p>
              <p className="text-muted-foreground">
                You belong to {workspaces.length} workspace{workspaces.length === 1 ? "" : "s"}.
              </p>
              <Link href="/workspace">
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
