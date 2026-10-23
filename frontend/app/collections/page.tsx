"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { AlertCircle, FolderOpen, Trash2 } from "lucide-react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { Collection, WorkspaceRole } from "@/lib/schemas";
import { useWorkspace } from "@/lib/workspace-context";

function canManageCollections(role: WorkspaceRole | undefined): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "MEMBER";
}

function CreateCollectionForm({
  workspaceId,
  onCreated,
}: {
  workspaceId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await api.createCollection(workspaceId, name.trim(), description.trim() || null);
      setName("");
      setDescription("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create collection.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={handleSubmit}>
      <div className="flex flex-1 flex-col gap-1.5">
        <label htmlFor="new-collection-name" className="text-sm font-medium">
          New collection name
        </label>
        <input
          id="new-collection-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-1 flex-col gap-1.5">
        <label htmlFor="new-collection-description" className="text-sm font-medium">
          Description (optional)
        </label>
        <input
          id="new-collection-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
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

function CollectionRow({
  workspaceId,
  collection,
  canManage,
  onDeleted,
}: {
  workspaceId: string;
  collection: Collection;
  canManage: boolean;
  onDeleted: (id: string) => void;
}) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    if (!window.confirm(`Delete "${collection.name}"? This cannot be undone.`)) return;
    setIsDeleting(true);
    setError(null);
    try {
      await api.deleteCollection(workspaceId, collection.id);
      onDeleted(collection.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete collection.");
      setIsDeleting(false);
    }
  }

  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300">
      <div className="flex items-start justify-between gap-4">
        <Link
          href={`/collections/${collection.id}`}
          className="flex min-w-0 items-start gap-3 focus-visible:outline-none"
        >
          <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
            <FolderOpen className="size-4" aria-hidden="true" />
          </div>
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium text-slate-900 group-hover:underline">
              {collection.name}
            </p>
            {collection.description && (
              <p className="text-muted-foreground truncate text-xs">{collection.description}</p>
            )}
            <p className="text-muted-foreground text-xs">
              {collection.document_count} document{collection.document_count === 1 ? "" : "s"}
            </p>
          </div>
        </Link>
        {canManage && (
          <button
            type="button"
            title="Delete collection"
            aria-label={`Delete ${collection.name}`}
            disabled={isDeleting}
            onClick={handleDelete}
            className="text-muted-foreground hover:text-destructive shrink-0 rounded-md p-1.5 transition hover:bg-red-50"
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </button>
        )}
      </div>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </li>
  );
}

function CollectionsContent() {
  const { currentWorkspace, isLoading: isWorkspaceLoading } = useWorkspace();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = currentWorkspace?.id ?? null;

  const loadCollections = useCallback(async () => {
    setIsLoading(true);
    if (!workspaceId) {
      setCollections([]);
      setIsLoading(false);
      return;
    }
    try {
      setCollections(await api.listCollections(workspaceId));
      setError(null);
    } catch {
      setError("Could not load collections.");
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadCollections();
  }, [loadCollections]);

  if (isWorkspaceLoading) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }
  if (!currentWorkspace) {
    return <p className="text-muted-foreground text-sm">Select or create a workspace first.</p>;
  }

  const canManage = canManageCollections(currentWorkspace.my_role);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Collections</CardTitle>
        <CardDescription>
          Group {currentWorkspace.name}&apos;s documents into logical collections.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {canManage && (
          <CreateCollectionForm workspaceId={currentWorkspace.id} onCreated={loadCollections} />
        )}
        {isLoading ? (
          <p className="text-muted-foreground text-sm">Loading collections…</p>
        ) : error ? (
          <p className="text-destructive flex items-center gap-1.5 text-sm">
            <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        ) : collections.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-10 text-center">
            <FolderOpen className="size-6 text-slate-400" aria-hidden="true" />
            <p className="text-muted-foreground text-sm">No collections yet.</p>
            {canManage && (
              <p className="text-muted-foreground text-xs">
                Create one above to start grouping related documents.
              </p>
            )}
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {collections.map((collection) => (
              <CollectionRow
                key={collection.id}
                workspaceId={currentWorkspace.id}
                collection={collection}
                canManage={canManage}
                onDeleted={() => setCollections((prev) => prev.filter((c) => c.id !== collection.id))}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function CollectionsPage() {
  return (
    <ProtectedRoute>
      <CollectionsContent />
    </ProtectedRoute>
  );
}
