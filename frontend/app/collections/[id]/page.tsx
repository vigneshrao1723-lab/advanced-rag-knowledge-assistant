"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, FileText, Pencil, Plus, Trash2 } from "lucide-react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { CollectionWithDocuments, Document, WorkspaceRole } from "@/lib/schemas";
import { useWorkspace } from "@/lib/workspace-context";

function canManageCollections(role: WorkspaceRole | undefined): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "MEMBER";
}

function RenameForm({
  collection,
  workspaceId,
  onRenamed,
  onCancel,
}: {
  collection: CollectionWithDocuments;
  workspaceId: string;
  onRenamed: (updated: CollectionWithDocuments) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(collection.name);
  const [description, setDescription] = useState(collection.description ?? "");
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setIsBusy(true);
    setError(null);
    try {
      const updated = await api.updateCollection(
        workspaceId,
        collection.id,
        name.trim(),
        description.trim() || null
      );
      onRenamed({ ...collection, ...updated });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update collection.");
      setIsBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 rounded-lg border border-indigo-200 bg-indigo-50/50 p-3">
      <label htmlFor="collection-name" className="sr-only">
        Collection name
      </label>
      <input
        id="collection-name"
        autoFocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        className="border-input bg-background rounded-md border px-2 py-1.5 text-sm font-medium"
      />
      <label htmlFor="collection-description" className="sr-only">
        Description
      </label>
      <input
        id="collection-description"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="Description (optional)"
        className="border-input bg-background rounded-md border px-2 py-1.5 text-sm"
      />
      <div className="flex gap-1.5">
        <Button type="submit" size="sm" disabled={isBusy}>
          Save
        </Button>
        <Button type="button" size="sm" variant="outline" disabled={isBusy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {error && <p className="text-destructive text-xs">{error}</p>}
    </form>
  );
}

function DocumentRow({
  workspaceId,
  collectionId,
  document,
  canManage,
  onRemoved,
}: {
  workspaceId: string;
  collectionId: string;
  document: Document;
  canManage: boolean;
  onRemoved: (documentId: string) => void;
}) {
  const [isRemoving, setIsRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRemove() {
    setIsRemoving(true);
    setError(null);
    try {
      await api.removeDocumentFromCollection(workspaceId, collectionId, document.id);
      onRemoved(document.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove document.");
      setIsRemoving(false);
    }
  }

  return (
    <li className="flex items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex min-w-0 items-start gap-3">
        <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
          <FileText className="size-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 text-sm">
          <p className="truncate font-medium text-slate-900">{document.filename}</p>
          <p className="text-muted-foreground text-xs">{document.status}</p>
        </div>
      </div>
      {canManage && (
        <button
          type="button"
          title="Remove from collection"
          aria-label={`Remove ${document.filename} from this collection`}
          disabled={isRemoving}
          onClick={handleRemove}
          className="text-muted-foreground hover:text-destructive shrink-0 rounded-md p-1.5 transition hover:bg-red-50"
        >
          <Trash2 className="size-4" aria-hidden="true" />
        </button>
      )}
      {error && <p className="text-destructive text-xs">{error}</p>}
    </li>
  );
}

function AddDocumentForm({
  workspaceId,
  collectionId,
  excludeDocumentIds,
  onAdded,
}: {
  workspaceId: string;
  collectionId: string;
  excludeDocumentIds: Set<string>;
  onAdded: (document: Document) => void;
}) {
  const [allDocuments, setAllDocuments] = useState<Document[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.listDocuments(workspaceId).then(setAllDocuments).catch(() => setAllDocuments([]));
  }, [workspaceId]);

  const available = allDocuments.filter((d) => !excludeDocumentIds.has(d.id));

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId) return;
    setIsBusy(true);
    setError(null);
    try {
      const document = await api.addDocumentToCollection(workspaceId, collectionId, selectedId);
      onAdded(document);
      setSelectedId("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add document.");
    } finally {
      setIsBusy(false);
    }
  }

  if (available.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        {allDocuments.length === 0
          ? "No documents in this workspace yet."
          : "Every document in this workspace is already in this collection."}
      </p>
    );
  }

  return (
    <form className="flex items-end gap-2" onSubmit={handleSubmit}>
      <div className="flex flex-1 flex-col gap-1.5">
        <label htmlFor="add-document-select" className="text-sm font-medium">
          Add a document
        </label>
        <select
          id="add-document-select"
          value={selectedId}
          onChange={(event) => setSelectedId(event.target.value)}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
        >
          <option value="">Select a document…</option>
          {available.map((document) => (
            <option key={document.id} value={document.id}>
              {document.filename}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" size="sm" disabled={isBusy || !selectedId}>
        <Plus className="size-4" aria-hidden="true" />
        Add
      </Button>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </form>
  );
}

function CollectionDetailContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const collectionId = params.id;
  const { currentWorkspace, isLoading: isWorkspaceLoading } = useWorkspace();
  const [collection, setCollection] = useState<CollectionWithDocuments | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);

  const workspaceId = currentWorkspace?.id ?? null;

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setIsLoading(true);
    setNotFound(false);
    setError(null);
    try {
      setCollection(await api.getCollection(workspaceId, collectionId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not load this collection.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, collectionId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function handleDeleteCollection() {
    if (!workspaceId || !collection) return;
    if (!window.confirm(`Delete "${collection.name}"? This cannot be undone.`)) return;
    try {
      await api.deleteCollection(workspaceId, collection.id);
      router.push("/collections");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete collection.");
    }
  }

  if (isWorkspaceLoading || isLoading) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }
  if (!currentWorkspace) {
    return <p className="text-muted-foreground text-sm">Select or create a workspace first.</p>;
  }
  if (notFound) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Collection not found</CardTitle>
          <CardDescription>
            It may have been deleted, or it belongs to a different workspace.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/collections" className="text-sm font-medium text-indigo-700 hover:underline">
            <ArrowLeft className="mr-1 inline size-3.5" aria-hidden="true" />
            Back to collections
          </Link>
        </CardContent>
      </Card>
    );
  }
  if (error && !collection) {
    return (
      <p className="text-destructive flex items-center gap-1.5 text-sm">
        <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
        {error}
      </p>
    );
  }
  if (!collection) return null;

  const canManage = canManageCollections(currentWorkspace.my_role);

  return (
    <Card>
      <CardHeader>
        <Link
          href="/collections"
          className="text-muted-foreground mb-2 inline-flex items-center gap-1 text-xs font-medium hover:text-slate-900"
        >
          <ArrowLeft className="size-3.5" aria-hidden="true" />
          Back to collections
        </Link>
        {isRenaming ? (
          <RenameForm
            collection={collection}
            workspaceId={currentWorkspace.id}
            onRenamed={(updated) => {
              setCollection(updated);
              setIsRenaming(false);
            }}
            onCancel={() => setIsRenaming(false)}
          />
        ) : (
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle>{collection.name}</CardTitle>
              <CardDescription>
                {collection.description || "No description."} · {collection.document_count}{" "}
                document{collection.document_count === 1 ? "" : "s"}
              </CardDescription>
            </div>
            {canManage && (
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  title="Rename collection"
                  aria-label="Rename collection"
                  onClick={() => setIsRenaming(true)}
                  className="text-muted-foreground hover:bg-slate-100 hover:text-foreground rounded-md p-1.5 transition"
                >
                  <Pencil className="size-4" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  title="Delete collection"
                  aria-label="Delete collection"
                  onClick={handleDeleteCollection}
                  className="text-muted-foreground hover:text-destructive rounded-md p-1.5 transition hover:bg-red-50"
                >
                  <Trash2 className="size-4" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {canManage && (
          <AddDocumentForm
            workspaceId={currentWorkspace.id}
            collectionId={collection.id}
            excludeDocumentIds={new Set(collection.documents.map((d) => d.id))}
            onAdded={(document) =>
              setCollection((prev) =>
                prev
                  ? {
                      ...prev,
                      documents: [document, ...prev.documents],
                      document_count: prev.document_count + 1,
                    }
                  : prev
              )
            }
          />
        )}
        {collection.documents.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-10 text-center">
            <FileText className="size-6 text-slate-400" aria-hidden="true" />
            <p className="text-muted-foreground text-sm">No documents in this collection yet.</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {collection.documents.map((document) => (
              <DocumentRow
                key={document.id}
                workspaceId={currentWorkspace.id}
                collectionId={collection.id}
                document={document}
                canManage={canManage}
                onRemoved={(documentId) =>
                  setCollection((prev) =>
                    prev
                      ? {
                          ...prev,
                          documents: prev.documents.filter((d) => d.id !== documentId),
                          document_count: prev.document_count - 1,
                        }
                      : prev
                  )
                }
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function CollectionDetailPage() {
  return (
    <ProtectedRoute>
      <CollectionDetailContent />
    </ProtectedRoute>
  );
}
