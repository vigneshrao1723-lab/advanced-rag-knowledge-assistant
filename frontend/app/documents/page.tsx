"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import { IN_PROGRESS_DOCUMENT_STATUSES } from "@/lib/schemas";
import type { Document, WorkspaceRole } from "@/lib/schemas";
import { useWorkspace } from "@/lib/workspace-context";

const POLL_INTERVAL_MS = 3000;

function canUpload(role: WorkspaceRole | undefined): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "MEMBER";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusClasses(status: Document["status"]): string {
  if (status === "READY") return "bg-emerald-100 text-emerald-800";
  if (status === "FAILED") return "bg-destructive/10 text-destructive";
  return "bg-accent text-accent-foreground";
}

function UploadForm({ workspaceId, onUploaded }: { workspaceId: string; onUploaded: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      const document = await api.uploadDocument(workspaceId, file);
      await api.processDocument(workspaceId, document.id);
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload document.");
    } finally {
      setIsUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="document-upload" className="text-sm font-medium">
        Upload a document
      </label>
      <input
        id="document-upload"
        ref={inputRef}
        type="file"
        onChange={handleChange}
        disabled={isUploading}
        className="border-input bg-background rounded-md border px-3 py-2 text-sm"
      />
      {isUploading && <p className="text-muted-foreground text-sm">Uploading and processing…</p>}
      {error && <p className="text-destructive text-sm">{error}</p>}
    </div>
  );
}

function DocumentRow({
  document,
  workspaceId,
  canManage,
  onChanged,
}: {
  document: Document;
  workspaceId: string;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);

  async function handleRetry() {
    setIsRetrying(true);
    setError(null);
    try {
      await api.processDocument(workspaceId, document.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not process document.");
    } finally {
      setIsRetrying(false);
    }
  }

  return (
    <li className="flex flex-col gap-1 border-b pb-3 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-4">
        <div className="text-sm">
          <p className="font-medium">{document.filename}</p>
          <p className="text-muted-foreground text-xs">
            {formatSize(document.size_bytes)}
            {document.page_count !== null ? ` · ${document.page_count} pages` : ""}
          </p>
          {document.status === "FAILED" && document.failure_reason && (
            <p className="text-destructive text-xs">{document.failure_reason}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClasses(document.status)}`}
          >
            {document.status}
          </span>
          {canManage && document.status === "FAILED" && (
            <Button variant="outline" size="sm" disabled={isRetrying} onClick={handleRetry}>
              {isRetrying ? "Retrying…" : "Retry"}
            </Button>
          )}
        </div>
      </div>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </li>
  );
}

function DocumentsContent() {
  const { currentWorkspace, isLoading: isWorkspaceLoading } = useWorkspace();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = currentWorkspace?.id ?? null;

  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    if (!workspaceId) {
      setDocuments([]);
      setIsLoading(false);
      return;
    }
    try {
      setDocuments(await api.listDocuments(workspaceId));
      setError(null);
    } catch {
      setError("Could not load documents.");
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDocuments();
  }, [loadDocuments]);

  // Polls while any document is still mid-pipeline, so the status column
  // (and the retry action once a document reaches FAILED) reflects real
  // backend state without a manual refresh.
  useEffect(() => {
    const hasInProgress = documents.some((d) =>
      IN_PROGRESS_DOCUMENT_STATUSES.includes(d.status)
    );
    if (!hasInProgress) return;
    const interval = setInterval(() => {
      void loadDocuments();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [documents, loadDocuments]);

  if (isWorkspaceLoading) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }
  if (!currentWorkspace) {
    return <p className="text-muted-foreground text-sm">Select or create a workspace first.</p>;
  }

  const canManage = canUpload(currentWorkspace.my_role);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
        <CardDescription>
          Upload documents to {currentWorkspace.name}. Once processed, they become searchable in
          chat.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {canManage && (
          <UploadForm workspaceId={currentWorkspace.id} onUploaded={loadDocuments} />
        )}
        {isLoading ? (
          <p className="text-muted-foreground text-sm">Loading documents…</p>
        ) : error ? (
          <p className="text-destructive text-sm">{error}</p>
        ) : documents.length === 0 ? (
          <p className="text-muted-foreground text-sm">No documents uploaded yet.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                workspaceId={currentWorkspace.id}
                canManage={canManage}
                onChanged={loadDocuments}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function DocumentsPage() {
  return (
    <ProtectedRoute>
      <DocumentsContent />
    </ProtectedRoute>
  );
}
