"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { AlertCircle, FileText, Search as SearchIcon } from "lucide-react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { SearchResponse, SearchResult } from "@/lib/schemas";
import { useWorkspace } from "@/lib/workspace-context";

function SearchResultRow({ result }: { result: SearchResult }) {
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
            <FileText className="size-4" aria-hidden="true" />
          </div>
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium text-slate-900">{result.document_filename}</p>
            <p className="text-muted-foreground text-xs">
              {result.page !== null ? `Page ${result.page}` : null}
              {result.page !== null && result.section ? " · " : null}
              {result.section ?? null}
            </p>
          </div>
        </div>
        <span className="text-muted-foreground shrink-0 text-xs">
          score {result.score.toFixed(2)}
        </span>
      </div>
      <p className="text-sm text-slate-700">{result.content}</p>
    </li>
  );
}

function SearchContent() {
  const { currentWorkspace, isLoading: isWorkspaceLoading } = useWorkspace();
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentWorkspace || !query.trim()) return;
    setIsSearching(true);
    setError(null);
    try {
      setResponse(await api.search(currentWorkspace.id, query.trim()));
      setHasSearched(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not search.");
    } finally {
      setIsSearching(false);
    }
  }

  if (isWorkspaceLoading) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }
  if (!currentWorkspace) {
    return <p className="text-muted-foreground text-sm">Select or create a workspace first.</p>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Search</CardTitle>
        <CardDescription>
          Evidence-first search of {currentWorkspace.name}&apos;s documents — ranked snippets,
          scores, and source, without generating an answer.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <form className="flex items-end gap-2" onSubmit={handleSubmit}>
          <div className="flex flex-1 flex-col gap-1.5">
            <label htmlFor="search-query" className="text-sm font-medium">
              Search query
            </label>
            <input
              id="search-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
            />
          </div>
          <Button type="submit" disabled={isSearching || !query.trim()}>
            <SearchIcon className="size-4" aria-hidden="true" />
            {isSearching ? "Searching…" : "Search"}
          </Button>
        </form>

        {error && (
          <p className="text-destructive flex items-center gap-1.5 text-sm">
            <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        {!error && hasSearched && response && (
          response.results.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-200 py-10 text-center">
              <SearchIcon className="size-6 text-slate-400" aria-hidden="true" />
              <p className="text-muted-foreground text-sm">
                No results for &quot;{response.query}&quot;.
              </p>
            </div>
          ) : (
            <ul className="flex flex-col gap-3">
              {response.results.map((result) => (
                <SearchResultRow key={result.chunk_id} result={result} />
              ))}
            </ul>
          )
        )}
      </CardContent>
    </Card>
  );
}

export default function SearchPage() {
  return (
    <ProtectedRoute>
      <SearchContent />
    </ProtectedRoute>
  );
}
