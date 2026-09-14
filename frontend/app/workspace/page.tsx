"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { Member, WorkspaceRole } from "@/lib/schemas";
import { useWorkspace } from "@/lib/workspace-context";

const ASSIGNABLE_ROLES: WorkspaceRole[] = ["OWNER", "ADMIN", "MEMBER", "VIEWER"];

function canManageMembers(role: WorkspaceRole | undefined): boolean {
  return role === "OWNER" || role === "ADMIN";
}

function CreateWorkspaceForm() {
  const { createWorkspace } = useWorkspace();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await createWorkspace(name.trim());
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create workspace.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="flex items-end gap-2" onSubmit={handleSubmit}>
      <div className="flex flex-1 flex-col gap-1.5">
        <label htmlFor="new-workspace-name" className="text-sm font-medium">
          New workspace name
        </label>
        <input
          id="new-workspace-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
        />
      </div>
      <Button type="submit" disabled={isSubmitting || !name.trim()}>
        {isSubmitting ? "Creating…" : "Create"}
      </Button>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </form>
  );
}

function WorkspaceList() {
  const { workspaces, currentWorkspace, setCurrentWorkspaceId } = useWorkspace();

  if (workspaces.length === 0) {
    return <p className="text-muted-foreground text-sm">You don&apos;t belong to a workspace yet.</p>;
  }

  return (
    <ul className="flex flex-col gap-1">
      {workspaces.map((workspace) => (
        <li key={workspace.id}>
          <button
            type="button"
            onClick={() => setCurrentWorkspaceId(workspace.id)}
            className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
              currentWorkspace?.id === workspace.id
                ? "bg-accent text-accent-foreground"
                : "hover:bg-accent/50"
            }`}
          >
            {workspace.name} <span className="text-muted-foreground">({workspace.my_role})</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function RenameWorkspaceForm({ workspaceId, currentName }: { workspaceId: string; currentName: string }) {
  const { refresh } = useWorkspace();
  const [name, setName] = useState(currentName);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || name === currentName) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await api.updateWorkspace(workspaceId, name.trim());
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not rename workspace.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="flex items-end gap-2" onSubmit={handleSubmit}>
      <div className="flex flex-1 flex-col gap-1.5">
        <label htmlFor="workspace-name" className="text-sm font-medium">
          Workspace name
        </label>
        <input
          id="workspace-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
        />
      </div>
      <Button type="submit" size="sm" variant="outline" disabled={isSubmitting}>
        Save
      </Button>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </form>
  );
}

function DeleteWorkspaceButton({ workspaceId }: { workspaceId: string }) {
  const { refresh } = useWorkspace();
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete() {
    if (!window.confirm("Delete this workspace? This cannot be undone.")) return;
    setIsDeleting(true);
    setError(null);
    try {
      await api.deleteWorkspace(workspaceId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete workspace.");
      setIsDeleting(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="destructive" size="sm" disabled={isDeleting} onClick={handleDelete}>
        {isDeleting ? "Deleting…" : "Delete workspace"}
      </Button>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </div>
  );
}

function AddMemberForm({ workspaceId, myRole, onAdded }: {
  workspaceId: string;
  myRole: WorkspaceRole;
  onAdded: () => void;
}) {
  const assignableRoles =
    myRole === "OWNER" ? ASSIGNABLE_ROLES : ASSIGNABLE_ROLES.filter((r) => r !== "OWNER" && r !== "ADMIN");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<WorkspaceRole>(assignableRoles[0] ?? "MEMBER");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await api.addMember(workspaceId, email.trim(), role);
      setEmail("");
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add member.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={handleSubmit}>
      <div className="flex flex-1 flex-col gap-1.5">
        <label htmlFor="member-email" className="text-sm font-medium">
          Add member by email
        </label>
        <input
          id="member-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
        />
      </div>
      <select
        aria-label="Role"
        value={role}
        onChange={(e) => setRole(e.target.value as WorkspaceRole)}
        className="border-input bg-background rounded-md border px-2 py-2 text-sm"
      >
        {assignableRoles.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <Button type="submit" disabled={isSubmitting || !email.trim()}>
        {isSubmitting ? "Adding…" : "Add"}
      </Button>
      {error && <p className="text-destructive w-full text-sm">{error}</p>}
    </form>
  );
}

function MemberRow({
  member,
  workspaceId,
  myRole,
  myUserId,
  onChanged,
}: {
  member: Member;
  workspaceId: string;
  myRole: WorkspaceRole;
  myUserId: string;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const isSelf = member.user_id === myUserId;
  const canEditRole =
    myRole === "OWNER" || (myRole === "ADMIN" && member.role !== "OWNER" && member.role !== "ADMIN");
  const canRemove = isSelf || canEditRole;
  const roleOptions =
    myRole === "OWNER" ? ASSIGNABLE_ROLES : ASSIGNABLE_ROLES.filter((r) => r !== "OWNER" && r !== "ADMIN");

  async function handleRoleChange(newRole: WorkspaceRole) {
    setError(null);
    try {
      await api.updateMemberRole(workspaceId, member.user_id, newRole);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change role.");
    }
  }

  async function handleRemove() {
    const confirmMessage = isSelf ? "Leave this workspace?" : "Remove this member?";
    if (!window.confirm(confirmMessage)) return;
    setError(null);
    try {
      await api.removeMember(workspaceId, member.user_id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove member.");
    }
  }

  return (
    <li className="flex flex-col gap-1 border-b pb-3 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-4">
        <div className="text-sm">
          <p className="font-medium">
            {member.email}
            {isSelf && <span className="text-muted-foreground ml-2 text-xs">(you)</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {canEditRole ? (
            <select
              aria-label={`Role for ${member.email}`}
              value={member.role}
              onChange={(e) => handleRoleChange(e.target.value as WorkspaceRole)}
              className="border-input bg-background rounded-md border px-2 py-1 text-sm"
            >
              {roleOptions.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          ) : (
            <span className="text-muted-foreground text-sm">{member.role}</span>
          )}
          {canRemove && (
            <Button variant="outline" size="sm" onClick={handleRemove}>
              {isSelf ? "Leave" : "Remove"}
            </Button>
          )}
        </div>
      </div>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </li>
  );
}

function MembersSection({ workspaceId, myRole }: { workspaceId: string; myRole: WorkspaceRole }) {
  const { user } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMembers = useCallback(async () => {
    setIsLoading(true);
    try {
      setMembers(await api.listMembers(workspaceId));
      setError(null);
    } catch {
      setError("Could not load members.");
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    // Standard fetch-on-mount/on-workspace-change pattern — no
    // data-fetching library is warranted for this issue's scope.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMembers();
  }, [loadMembers]);

  if (!user) return null;

  return (
    <div className="flex flex-col gap-4">
      {canManageMembers(myRole) && (
        <AddMemberForm workspaceId={workspaceId} myRole={myRole} onAdded={loadMembers} />
      )}
      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading members…</p>
      ) : error ? (
        <p className="text-destructive text-sm">{error}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {members.map((member) => (
            <MemberRow
              key={member.user_id}
              member={member}
              workspaceId={workspaceId}
              myRole={myRole}
              myUserId={user.id}
              onChanged={loadMembers}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function WorkspaceContent() {
  const { currentWorkspace, isLoading } = useWorkspace();

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Your workspaces</CardTitle>
          <CardDescription>Create a workspace or switch between the ones you belong to.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <WorkspaceList />
          <CreateWorkspaceForm />
        </CardContent>
      </Card>

      {isLoading ? null : currentWorkspace ? (
        <Card>
          <CardHeader>
            <CardTitle>{currentWorkspace.name}</CardTitle>
            <CardDescription>Your role: {currentWorkspace.my_role}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            {currentWorkspace.my_role === "OWNER" || currentWorkspace.my_role === "ADMIN" ? (
              <RenameWorkspaceForm
                workspaceId={currentWorkspace.id}
                currentName={currentWorkspace.name}
              />
            ) : null}

            <MembersSection workspaceId={currentWorkspace.id} myRole={currentWorkspace.my_role} />

            {currentWorkspace.my_role === "OWNER" && (
              <DeleteWorkspaceButton workspaceId={currentWorkspace.id} />
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function WorkspacePage() {
  return (
    <ProtectedRoute>
      <WorkspaceContent />
    </ProtectedRoute>
  );
}
