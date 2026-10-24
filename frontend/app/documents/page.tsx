"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Pencil,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import { IN_PROGRESS_DOCUMENT_STATUSES } from "@/lib/schemas";
import type { Document, DocumentStatus, WorkspaceRole } from "@/lib/schemas";
import { useWorkspace } from "@/lib/workspace-context";

const POLL_INTERVAL_MS = 3000;
// Matches backend/app/core/config.py's max_upload_size_bytes default and
// the five formats backend/app/services/document_service.py validates
// against (docs/API_CONTRACT.md) -- informational copy only, not an
// independent client-side limit the backend doesn't already enforce.
const SUPPORTED_FORMATS_LABEL = "PDF, DOCX, TXT, Markdown or CSV";
const MAX_UPLOAD_SIZE_LABEL = "up to 50 MB";

function canUpload(role: WorkspaceRole | undefined): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "MEMBER";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusBadge(status: Document["status"]): { classes: string; icon: typeof CheckCircle2 } {
  if (status === "READY") {
    return { classes: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20", icon: CheckCircle2 };
  }
  if (status === "FAILED") {
    return { classes: "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20", icon: AlertCircle };
  }
  return { classes: "bg-indigo-50 text-indigo-700 ring-1 ring-inset ring-indigo-600/20", icon: Loader2 };
}

function UploadForm({ workspaceId, onUploaded }: { workspaceId: string; onUploaded: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
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
    },
    [workspaceId, onUploaded]
  );

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) await handleFile(file);
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (!isUploading) setIsDragOver(true);
  }

  function handleDragLeave() {
    setIsDragOver(false);
  }

  async function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragOver(false);
    const file = event.dataTransfer.files?.[0];
    if (file && !isUploading) await handleFile(file);
  }

  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor="document-upload"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
          isDragOver
            ? "border-indigo-400 bg-indigo-50"
            : "border-slate-200 bg-slate-50/60 hover:border-indigo-300 hover:bg-indigo-50/40"
        } ${isUploading ? "pointer-events-none opacity-70" : ""}`}
      >
        {isUploading ? (
          <Loader2 className="size-7 animate-spin text-indigo-600" aria-hidden="true" />
        ) : (
          <UploadCloud className="size-7 text-indigo-600" aria-hidden="true" />
        )}
        <span className="text-sm font-medium text-slate-900">
          {isUploading ? "Uploading and processing…" : "Upload a document"}
        </span>
        {!isUploading && (
          <span className="text-xs text-slate-500">
            Drag and drop, or click to browse · {SUPPORTED_FORMATS_LABEL} · {MAX_UPLOAD_SIZE_LABEL}
          </span>
        )}
        <input
          id="document-upload"
          ref={inputRef}
          type="file"
          onChange={handleChange}
          disabled={isUploading}
          className="sr-only"
        />
      </label>
      {error && (
        <p className="text-destructive flex items-center gap-1.5 text-sm">
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  );
}

function DocumentRow({
  document,
  workspaceId,
  canManage,
  onChanged,
  onDeleted,
}: {
  document: Document;
  workspaceId: string;
  canManage: boolean;
  onChanged: () => void;
  onDeleted: (id: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [filenameDraft, setFilenameDraft] = useState(document.filename);

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

  async function handleRenameSubmit(event: FormEvent) {
    event.preventDefault();
    if (!filenameDraft.trim()) return;
    setIsBusy(true);
    setError(null);
    try {
      await api.renameDocument(workspaceId, document.id, filenameDraft.trim());
      onChanged();
      setIsRenaming(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not rename the document.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete "${document.filename}"? This cannot be undone.`)) return;
    setIsBusy(true);
    setError(null);
    try {
      await api.deleteDocument(workspaceId, document.id);
      onDeleted(document.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the document.");
      setIsBusy(false);
    }
  }

  const { classes, icon: StatusIcon } = statusBadge(document.status);
  const isInProgress = IN_PROGRESS_DOCUMENT_STATUSES.includes(document.status);

  if (isRenaming) {
    return (
      <li className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
        <form onSubmit={handleRenameSubmit} className="flex flex-col gap-2">
          <label htmlFor={`rename-${document.id}`} className="sr-only">
            Document name
          </label>
          <input
            id={`rename-${document.id}`}
            autoFocus
            value={filenameDraft}
            onChange={(event) => setFilenameDraft(event.target.value)}
            className="border-input bg-background rounded-md border px-2 py-1.5 text-sm"
          />
          <div className="flex gap-1.5">
            <Button type="submit" size="sm" disabled={isBusy}>
              Save
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={isBusy}
              onClick={() => {
                setFilenameDraft(document.filename);
                setIsRenaming(false);
              }}
            >
              Cancel
            </Button>
          </div>
          {error && <p className="text-destructive text-xs">{error}</p>}
        </form>
      </li>
    );
  }

  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300">
      <div className="flex items-start justify-between gap-4">
        <Link
          href={`/documents/${document.id}`}
          className="flex min-w-0 items-start gap-3 focus-visible:outline-none"
        >
          <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
            <FileText className="size-4" aria-hidden="true" />
          </div>
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium text-slate-900 hover:underline">
              {document.filename}
            </p>
            <p className="text-muted-foreground text-xs">
              {formatSize(document.size_bytes)}
              {document.page_count !== null ? ` · ${document.page_count} pages` : ""}
            </p>
            {document.status === "FAILED" && document.failure_reason && (
              <p className="text-destructive mt-1 text-xs">{document.failure_reason}</p>
            )}
          </div>
        </Link>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${classes}`}
          >
            <StatusIcon className={`size-3.5 ${isInProgress ? "animate-spin" : ""}`} aria-hidden="true" />
            {document.status}
          </span>
          {canManage && document.status === "FAILED" && (
            <Button variant="outline" size="sm" disabled={isRetrying} onClick={handleRetry}>
              {isRetrying ? "Retrying…" : "Retry"}
            </Button>
          )}
          <a
            href={api.getDocumentDownloadUrl(workspaceId, document.id)}
            download={document.filename}
            title="Download original file"
            aria-label={`Download ${document.filename}`}
            className="text-muted-foreground hover:bg-slate-100 hover:text-foreground rounded-md p-1.5 transition"
          >
            <Download className="size-3.5" aria-hidden="true" />
          </a>
          {canManage && (
            <>
              <button
                type="button"
                title="Rename document"
                aria-label={`Rename ${document.filename}`}
                disabled={isBusy}
                onClick={() => setIsRenaming(true)}
                className="text-muted-foreground hover:bg-slate-100 hover:text-foreground rounded-md p-1.5 transition"
              >
                <Pencil className="size-3.5" aria-hidden="true" />
              </button>
              <button
                type="button"
                title="Delete document"
                aria-label={`Delete ${document.filename}`}
                disabled={isBusy}
                onClick={handleDelete}
                className="text-muted-foreground hover:text-destructive rounded-md p-1.5 transition hover:bg-red-50"
              >
                <Trash2 className="size-3.5" aria-hidden="true" />
              </button>
            </>
          )}
        </div>
      </div>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </li>
  );
}

const STATUS_FILTER_OPTIONS: DocumentStatus[] = [
  "UPLOADED",
  "PROCESSING",
  "PARSED",
  "CLEANED",
  "CHUNKED",
  "EMBEDDED",
  "INDEXED",
  "READY",
  "FAILED",
];

function DocumentsContent() {
  const { currentWorkspace, isLoading: isWorkspaceLoading } = useWorkspace();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "">("");

  const workspaceId = currentWorkspace?.id ?? null;

  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    if (!workspaceId) {
      setDocuments([]);
      setIsLoading(false);
      return;
    }
    try {
      setDocuments(
        await api.listDocuments(workspaceId, {
          status: statusFilter || undefined,
          q: searchQuery.trim() || undefined,
        })
      );
      setError(null);
    } catch {
      setError("Could not load documents.");
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, statusFilter, searchQuery]);

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
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex min-w-[180px] flex-1 flex-col gap-1.5">
            <label htmlFor="document-search" className="text-sm font-medium">
              Search by filename
            </label>
            <div className="relative">
              <Search
                className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-slate-400"
                aria-hidden="true"
              />
              <input
                id="document-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="border-input bg-background w-full rounded-md border py-2 pl-8 pr-3 text-sm"
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="document-status-filter" className="text-sm font-medium">
              Status
            </label>
            <select
              id="document-status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as DocumentStatus | "")}
              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
            >
              <option value="">All</option>
              {STATUS_FILTER_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        </div>
        {isLoading ? (
          <p className="text-muted-foreground text-sm">Loading documents…</p>
        ) : error ? (
          <p className="text-destructive flex items-center gap-1.5 text-sm">
            <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-10 text-center">
            <FileText className="size-6 text-slate-400" aria-hidden="true" />
            <p className="text-muted-foreground text-sm">
              {searchQuery || statusFilter
                ? "No documents match this filter."
                : "No documents uploaded yet."}
            </p>
            {canManage && !searchQuery && !statusFilter && (
              <p className="text-muted-foreground text-xs">
                Upload a file above to start building this workspace&apos;s knowledge base.
              </p>
            )}
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                workspaceId={currentWorkspace.id}
                canManage={canManage}
                onChanged={loadDocuments}
                onDeleted={(id) => setDocuments((prev) => prev.filter((d) => d.id !== id))}
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
