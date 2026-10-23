"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { AlertCircle, ArrowLeft, FileText, Loader2 } from "lucide-react";

import { ProtectedRoute } from "@/components/protected-route";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import { IN_PROGRESS_DOCUMENT_STATUSES } from "@/lib/schemas";
import type { Document, DocumentChunk } from "@/lib/schemas";
import { useWorkspace } from "@/lib/workspace-context";

function DocumentChunkBlock({
  chunk,
  isHighlighted,
  registerRef,
}: {
  chunk: DocumentChunk;
  isHighlighted: boolean;
  registerRef: (element: HTMLDivElement | null) => void;
}) {
  return (
    <div
      ref={registerRef}
      className={`rounded-xl border p-4 transition ${
        isHighlighted
          ? "border-indigo-400 bg-indigo-50/60 ring-2 ring-indigo-200"
          : "border-slate-200 bg-white"
      }`}
    >
      <p className="text-muted-foreground mb-2 text-xs">
        {chunk.page !== null ? `Page ${chunk.page}` : null}
        {chunk.page !== null && chunk.section ? " · " : null}
        {chunk.section ?? null}
      </p>
      <p className="text-sm whitespace-pre-wrap text-slate-800">{chunk.content}</p>
    </div>
  );
}

function DocumentViewerContent() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const documentId = params.id;
  const highlightedChunkId = searchParams.get("chunk");

  const { currentWorkspace, isLoading: isWorkspaceLoading } = useWorkspace();
  const [doc, setDoc] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chunkRefs = useRef(new Map<string, HTMLDivElement>());

  const workspaceId = currentWorkspace?.id ?? null;

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setIsLoading(true);
    setNotFound(false);
    setError(null);
    try {
      const [documentResult, chunksResult] = await Promise.all([
        api.getDocument(workspaceId, documentId),
        api.listDocumentChunks(workspaceId, documentId),
      ]);
      setDoc(documentResult);
      setChunks(chunksResult);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not load this document.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, documentId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  useEffect(() => {
    if (!highlightedChunkId) return;
    const target = chunkRefs.current.get(highlightedChunkId);
    target?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [highlightedChunkId, chunks]);

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
          <CardTitle>Document not found</CardTitle>
          <CardDescription>
            It may have been deleted, or it belongs to a different workspace.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/documents" className="text-sm font-medium text-indigo-700 hover:underline">
            <ArrowLeft className="mr-1 inline size-3.5" aria-hidden="true" />
            Back to documents
          </Link>
        </CardContent>
      </Card>
    );
  }
  if (error && !doc) {
    return (
      <p className="text-destructive flex items-center gap-1.5 text-sm">
        <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
        {error}
      </p>
    );
  }
  if (!doc) return null;

  const isInProgress = IN_PROGRESS_DOCUMENT_STATUSES.includes(doc.status);

  return (
    <Card>
      <CardHeader>
        <Link
          href="/documents"
          className="text-muted-foreground mb-2 inline-flex items-center gap-1 text-xs font-medium hover:text-slate-900"
        >
          <ArrowLeft className="size-3.5" aria-hidden="true" />
          Back to documents
        </Link>
        <CardTitle>{doc.filename}</CardTitle>
        <CardDescription>
          {chunks.length} chunk{chunks.length === 1 ? "" : "s"} · {doc.status}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error && (
          <p className="text-destructive flex items-center gap-1.5 text-sm">
            <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}
        {chunks.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-10 text-center">
            {isInProgress ? (
              <Loader2 className="size-6 animate-spin text-slate-400" aria-hidden="true" />
            ) : (
              <FileText className="size-6 text-slate-400" aria-hidden="true" />
            )}
            <p className="text-muted-foreground text-sm">
              {isInProgress
                ? "Still processing — chunks will appear here once ingestion finishes."
                : doc.status === "FAILED"
                  ? "This document failed to process, so it has no extracted content to view."
                  : "No extracted content available."}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {chunks.map((chunk) => (
              <DocumentChunkBlock
                key={chunk.id}
                chunk={chunk}
                isHighlighted={chunk.id === highlightedChunkId}
                registerRef={(element) => {
                  if (element) chunkRefs.current.set(chunk.id, element);
                  else chunkRefs.current.delete(chunk.id);
                }}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DocumentDetailPage() {
  return (
    <ProtectedRoute>
      <DocumentViewerContent />
    </ProtectedRoute>
  );
}
