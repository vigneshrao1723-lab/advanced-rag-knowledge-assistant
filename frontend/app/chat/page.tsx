"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquareText,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Search,
  Send,
  Square,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";

import { Markdown } from "@/components/markdown";
import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { VoiceInputButton, VoiceInputPanel } from "@/components/voice-input";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { Capabilities, Citation, Conversation, Document, Message } from "@/lib/schemas";
import { useVoiceInput } from "@/lib/use-voice-input";
import { useWorkspace } from "@/lib/workspace-context";

function ConversationRow({
  workspaceId,
  conversation,
  isSelected,
  onSelect,
  onRenamed,
  onDeleted,
}: {
  workspaceId: string;
  conversation: Conversation;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onRenamed: (conversation: Conversation) => void;
  onDeleted: (id: string) => void;
}) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [titleDraft, setTitleDraft] = useState(conversation.title ?? "");
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRenameSubmit(event: FormEvent) {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    try {
      const updated = await api.renameConversation(
        workspaceId,
        conversation.id,
        titleDraft.trim() || null
      );
      onRenamed(updated);
      setIsRenaming(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not rename the conversation.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this conversation? This cannot be undone.")) return;
    setIsBusy(true);
    setError(null);
    try {
      await api.deleteConversation(workspaceId, conversation.id);
      onDeleted(conversation.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the conversation.");
      setIsBusy(false);
    }
  }

  if (isRenaming) {
    return (
      <li>
        <form
          onSubmit={handleRenameSubmit}
          className="flex flex-col gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50/50 p-2"
        >
          <label htmlFor={`rename-${conversation.id}`} className="sr-only">
            Conversation title
          </label>
          <input
            id={`rename-${conversation.id}`}
            autoFocus
            value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
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
              onClick={() => setIsRenaming(false)}
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
    <li className="group flex items-center gap-0.5">
      <button
        type="button"
        onClick={() => onSelect(conversation.id)}
        className={`min-w-0 flex-1 truncate rounded-lg px-3 py-2 text-left text-sm transition-colors ${
          isSelected
            ? "bg-indigo-50 font-medium text-indigo-800"
            : "text-slate-700 hover:bg-slate-100"
        }`}
      >
        {conversation.title ?? `Conversation ${conversation.id.slice(0, 8)}`}
      </button>
      <button
        type="button"
        title="Rename conversation"
        aria-label="Rename conversation"
        disabled={isBusy}
        onClick={() => {
          setTitleDraft(conversation.title ?? "");
          setIsRenaming(true);
        }}
        className="text-muted-foreground hover:bg-slate-100 hover:text-foreground shrink-0 rounded-md p-1.5 opacity-0 transition focus-visible:opacity-100 group-hover:opacity-100"
      >
        <Pencil className="size-3.5" aria-hidden="true" />
      </button>
      <button
        type="button"
        title="Delete conversation"
        aria-label="Delete conversation"
        disabled={isBusy}
        onClick={handleDelete}
        className="text-muted-foreground hover:text-destructive shrink-0 rounded-md p-1.5 opacity-0 transition hover:bg-red-50 focus-visible:opacity-100 group-hover:opacity-100"
      >
        <Trash2 className="size-3.5" aria-hidden="true" />
      </button>
      {error && <p className="text-destructive text-xs">{error}</p>}
    </li>
  );
}

function ConversationList({
  workspaceId,
  conversations,
  selectedId,
  onSelect,
  onCreated,
  onRenamed,
  onDeleted,
}: {
  workspaceId: string;
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreated: (conversation: Conversation) => void;
  onRenamed: (conversation: Conversation) => void;
  onDeleted: (id: string) => void;
}) {
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  async function handleCreate() {
    setIsCreating(true);
    setError(null);
    try {
      const conversation = await api.createConversation(workspaceId);
      onCreated(conversation);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start a conversation.");
    } finally {
      setIsCreating(false);
    }
  }

  const filtered = query.trim()
    ? conversations.filter((c) => (c.title ?? "").toLowerCase().includes(query.trim().toLowerCase()))
    : conversations;

  return (
    <div className="flex w-full shrink-0 flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-3 sm:w-72">
      <Button disabled={isCreating} onClick={handleCreate}>
        <Plus className="size-4" aria-hidden="true" />
        {isCreating ? "Starting…" : "New conversation"}
      </Button>
      {conversations.length > 0 && (
        <div className="relative">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
            aria-hidden="true"
          />
          <label htmlFor="conversation-search" className="sr-only">
            Search conversations
          </label>
          <input
            id="conversation-search"
            type="search"
            placeholder="Search conversations…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="border-input bg-background w-full rounded-lg border py-1.5 pr-2 pl-8 text-sm"
          />
        </div>
      )}
      {error && <p className="text-destructive text-sm">{error}</p>}
      {conversations.length === 0 ? (
        <p className="text-muted-foreground px-1 text-sm">No conversations yet.</p>
      ) : filtered.length === 0 ? (
        <p className="text-muted-foreground px-1 text-sm">
          No conversations match &quot;{query}&quot;.
        </p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {filtered.map((conversation) => (
            <ConversationRow
              key={conversation.id}
              workspaceId={workspaceId}
              conversation={conversation}
              isSelected={selectedId === conversation.id}
              onSelect={onSelect}
              onRenamed={onRenamed}
              onDeleted={onDeleted}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function citationLabel(citation: Citation, documentsById: Map<string, Document>): string {
  const filename = documentsById.get(citation.document_id)?.filename ?? "source document";
  const parts = [filename];
  if (citation.page !== null) parts.push(`page ${citation.page}`);
  if (citation.section) parts.push(citation.section);
  return parts.join(" · ");
}

function CitationSource({
  workspaceId,
  citation,
  label,
}: {
  workspaceId: string;
  citation: Citation;
  label: string;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleToggle() {
    if (isOpen) {
      setIsOpen(false);
      return;
    }
    if (content !== null) {
      setIsOpen(true);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const chunk = await api.getDocumentChunk(
        workspaceId,
        citation.document_id,
        citation.chunk_id
      );
      setContent(chunk.content);
      setIsOpen(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the cited source.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <li>
      <button
        type="button"
        onClick={handleToggle}
        className="hover:bg-accent hover:text-accent-foreground inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-left transition"
      >
        <FileText className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="font-medium">[{citation.rank}]</span> {label}
        {isLoading ? (
          <Loader2 className="size-3 shrink-0 animate-spin" aria-hidden="true" />
        ) : isOpen ? (
          <ChevronUp className="size-3 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronDown className="size-3 shrink-0" aria-hidden="true" />
        )}
      </button>
      {error && <p className="text-destructive px-1.5">{error}</p>}
      {isOpen && content !== null && (
        <>
          <blockquote className="border-indigo-200 bg-indigo-50/40 text-foreground mt-1 max-w-prose rounded-r-md border-l-2 py-2 pr-2 pl-3 text-sm whitespace-pre-wrap">
            {content}
          </blockquote>
          <Link
            href={`/documents/${citation.document_id}?chunk=${citation.chunk_id}`}
            className="mt-1 inline-flex items-center gap-1 px-1.5 text-xs font-medium text-indigo-700 hover:underline"
          >
            <ExternalLink className="size-3" aria-hidden="true" />
            View in document
          </Link>
        </>
      )}
    </li>
  );
}

function AudioPlaybackButton({
  workspaceId,
  conversationId,
  messageId,
}: {
  workspaceId: string;
  conversationId: string;
  messageId: string;
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  function ensureAudioElement(): HTMLAudioElement {
    if (!audioRef.current) {
      const audio = new Audio(api.getMessageAudioUrl(workspaceId, conversationId, messageId));
      audio.addEventListener("ended", () => setIsPlaying(false));
      audioRef.current = audio;
    }
    return audioRef.current;
  }

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  async function handleToggle() {
    setError(null);
    const audio = ensureAudioElement();
    if (isPlaying) {
      // Interrupt/stop: pausing and resetting position, not just muting
      // -- a re-click starts the answer over, matching "stop," not
      // "pause and silently resume where it left off."
      audio.pause();
      audio.currentTime = 0;
      setIsPlaying(false);
      return;
    }
    try {
      await audio.play();
      setIsPlaying(true);
    } catch {
      setError("Could not play audio.");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Button type="button" variant="outline" size="sm" onClick={handleToggle}>
        {isPlaying ? (
          <Square className="size-3.5" aria-hidden="true" />
        ) : (
          <Play className="size-3.5" aria-hidden="true" />
        )}
        {isPlaying ? "Stop" : "Play answer"}
      </Button>
      {error && <span className="text-destructive text-xs">{error}</span>}
    </div>
  );
}

function FeedbackButtons({
  workspaceId,
  conversationId,
  message,
  onChanged,
}: {
  workspaceId: string;
  conversationId: string;
  message: Message;
  onChanged: (message: Message) => void;
}) {
  const [error, setError] = useState<string | null>(null);

  async function handleRate(rating: "UP" | "DOWN") {
    setError(null);
    try {
      const next = await api.setMessageFeedback(
        workspaceId,
        conversationId,
        message.id,
        message.feedback === rating ? null : rating
      );
      onChanged(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record feedback.");
    }
  }

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        title="Good response"
        aria-label="Good response"
        aria-pressed={message.feedback === "UP"}
        onClick={() => handleRate("UP")}
        className={`rounded-md p-1.5 transition ${
          message.feedback === "UP"
            ? "bg-emerald-50 text-emerald-700"
            : "text-muted-foreground hover:bg-slate-100 hover:text-foreground"
        }`}
      >
        <ThumbsUp className="size-3.5" aria-hidden="true" />
      </button>
      <button
        type="button"
        title="Bad response"
        aria-label="Bad response"
        aria-pressed={message.feedback === "DOWN"}
        onClick={() => handleRate("DOWN")}
        className={`rounded-md p-1.5 transition ${
          message.feedback === "DOWN"
            ? "bg-red-50 text-red-700"
            : "text-muted-foreground hover:bg-slate-100 hover:text-foreground"
        }`}
      >
        <ThumbsDown className="size-3.5" aria-hidden="true" />
      </button>
      {error && <span className="text-destructive text-xs">{error}</span>}
    </div>
  );
}

function RegenerateButton({
  workspaceId,
  conversationId,
  messageId,
  onRegenerated,
}: {
  workspaceId: string;
  conversationId: string;
  messageId: string;
  onRegenerated: (message: Message) => void;
}) {
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRegenerate() {
    setIsRegenerating(true);
    setError(null);
    try {
      const updated = await api.regenerateMessage(workspaceId, conversationId, messageId);
      onRegenerated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not regenerate this answer.");
    } finally {
      setIsRegenerating(false);
    }
  }

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        title="Regenerate response"
        aria-label="Regenerate response"
        disabled={isRegenerating}
        onClick={handleRegenerate}
        className="text-muted-foreground hover:bg-slate-100 hover:text-foreground rounded-md p-1.5 transition disabled:opacity-50"
      >
        <RotateCcw className={`size-3.5 ${isRegenerating ? "animate-spin" : ""}`} aria-hidden="true" />
      </button>
      {error && <span className="text-destructive text-xs">{error}</span>}
    </div>
  );
}

function MessageBubble({
  workspaceId,
  conversationId,
  message,
  documentsById,
  onMessageUpdated,
}: {
  workspaceId: string;
  conversationId: string;
  message: Message;
  documentsById: Map<string, Document>;
  onMessageUpdated: (message: Message) => void;
}) {
  const isUser = message.role === "USER";
  return (
    <div className={`flex flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={`rounded-2xl px-4 py-2.5 text-sm leading-6 ${
          isUser
            ? "max-w-[80%] rounded-br-md bg-indigo-700 whitespace-pre-wrap text-white"
            : "max-w-full rounded-bl-md border border-slate-200 bg-slate-50 text-slate-900 sm:max-w-[90%]"
        }`}
      >
        {isUser ? message.content : <Markdown content={message.content} />}
      </div>
      {!isUser && !message.id.startsWith("pending-") && (
        <div className="flex items-center gap-2">
          <AudioPlaybackButton
            workspaceId={workspaceId}
            conversationId={conversationId}
            messageId={message.id}
          />
          <div className="h-4 w-px bg-slate-200" aria-hidden="true" />
          <FeedbackButtons
            workspaceId={workspaceId}
            conversationId={conversationId}
            message={message}
            onChanged={onMessageUpdated}
          />
          <div className="h-4 w-px bg-slate-200" aria-hidden="true" />
          <RegenerateButton
            workspaceId={workspaceId}
            conversationId={conversationId}
            messageId={message.id}
            onRegenerated={onMessageUpdated}
          />
        </div>
      )}
      {message.citations.length > 0 && (
        <ul className="text-muted-foreground flex flex-col gap-0.5 text-xs">
          {message.citations.map((citation) => (
            <CitationSource
              key={`${message.id}-${citation.rank}`}
              workspaceId={workspaceId}
              citation={citation}
              label={citationLabel(citation, documentsById)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ConversationThread({
  workspaceId,
  conversationId,
  documentsById,
}: {
  workspaceId: string;
  conversationId: string;
  documentsById: Map<string, Document>;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [transcriptHint, setTranscriptHint] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const voice = useVoiceInput({
    workspaceId,
    onTranscript: (text) => {
      // The transcript goes into the editable box - it is NOT sent. The user
      // reviews/corrects it and presses Ask.
      setQuestion(text);
      setTranscriptHint(true);
      setSendError(null);
      inputRef.current?.focus();
    },
  });
  const isVoiceBusy = voice.phase !== "idle";

  const loadMessages = useCallback(async () => {
    setIsLoading(true);
    try {
      setMessages(await api.listMessages(workspaceId, conversationId));
      setLoadError(null);
    } catch {
      setLoadError("Could not load this conversation.");
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, conversationId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMessages();
  }, [loadMessages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = question.trim();
    if (!content) return;
    setIsSending(true);
    setSendError(null);
    setTranscriptHint(false);
    setQuestion("");
    setMessages((prev) => [
      ...prev,
      {
        id: `pending-${prev.length}`,
        role: "USER",
        content,
        created_at: new Date().toISOString(),
        citations: [],
        feedback: null,
      },
    ]);
    try {
      const assistantMessage = await api.postMessage(workspaceId, conversationId, content);
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setSendError(err instanceof ApiError ? err.message : "Could not send that question.");
      if (err instanceof ApiError && err.status === 503) {
        // The AI model is unavailable: the server withdrew the question
        // (nothing was answered or saved), so drop the optimistic bubble and
        // give the user their text back to retry once the model is up.
        setMessages((prev) => prev.filter((m) => !m.id.startsWith("pending-")));
        setQuestion(content);
      }
      // For other failures the optimistic bubble stays: it reflects what the
      // user asked, and reopening the conversation shows the persisted state.
    } finally {
      setIsSending(false);
    }
  }

  return (
    <Card className="flex flex-1 flex-col gap-0 py-0">
      <CardHeader className="border-b border-slate-100 py-4">
        <CardTitle>Chat</CardTitle>
        <CardDescription>Ask a question about your workspace&apos;s documents.</CardDescription>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-4 py-4">
        <div className="flex min-h-64 flex-1 flex-col gap-4 overflow-y-auto">
          {isLoading ? (
            <p className="text-muted-foreground text-sm">Loading…</p>
          ) : loadError ? (
            <p className="text-destructive text-sm">{loadError}</p>
          ) : messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
              <MessageSquareText className="size-6 text-slate-300" aria-hidden="true" />
              <p className="text-muted-foreground text-sm">Ask a question to get started.</p>
            </div>
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                workspaceId={workspaceId}
                conversationId={conversationId}
                message={message}
                documentsById={documentsById}
                onMessageUpdated={(updated) =>
                  setMessages((prev) => prev.map((m) => (m.id === updated.id ? updated : m)))
                }
              />
            ))
          )}
          <div ref={bottomRef} />
        </div>
        <form
          className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-4"
          onSubmit={handleSubmit}
        >
          <div className="flex min-w-[160px] flex-1 flex-col gap-1.5">
            <label htmlFor="chat-question" className="sr-only">
              Ask a question
            </label>
            <input
              id="chat-question"
              ref={inputRef}
              value={question}
              onChange={(e) => {
                setQuestion(e.target.value);
                setTranscriptHint(false);
              }}
              placeholder="Ask a question…"
              disabled={isSending}
              className="border-input bg-background w-full rounded-lg border px-3.5 py-2.5 text-sm"
            />
          </div>
          <div className="flex shrink-0 gap-2">
          <Button type="submit" disabled={isSending || isVoiceBusy || !question.trim()}>
            {isSending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="size-4" aria-hidden="true" />
            )}
            {isSending ? "Asking…" : "Ask"}
          </Button>
          <VoiceInputButton voice={voice} disabled={isSending} />
          </div>
        </form>
        <VoiceInputPanel voice={voice} transcriptHint={transcriptHint} />
        {sendError && (
          <p className="text-destructive text-sm">{sendError}</p>
        )}
      </CardContent>
    </Card>
  );
}

/** Tells the user up front when answers can't be real explanations (model
 * not running / not configured) instead of letting the first question fail. */
function ModelStatusBanner() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getCapabilities()
      .then((result) => {
        if (!cancelled) setCapabilities(result);
      })
      .catch(() => {
        // The banner is advisory; if the check itself fails, say nothing.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!capabilities || capabilities.llm.status === "ready") return null;
  const isExtractive = capabilities.llm.status === "extractive";
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div>
        <p className="font-medium">
          {isExtractive ? "No AI model is set up" : "The AI model is not available"}
        </p>
        <p>{capabilities.llm.message}</p>
        <p className="text-amber-800">Setup guide: docs/AI_SETUP.md</p>
      </div>
    </div>
  );
}

function ChatContent() {
  const { currentWorkspace, isLoading: isWorkspaceLoading } = useWorkspace();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const workspaceId = currentWorkspace?.id ?? null;

  const loadSidebar = useCallback(async () => {
    setIsLoading(true);
    if (!workspaceId) {
      setConversations([]);
      setDocuments([]);
      setSelectedId(null);
      setIsLoading(false);
      return;
    }
    try {
      const [conversationList, documentList] = await Promise.all([
        api.listConversations(workspaceId),
        api.listDocuments(workspaceId),
      ]);
      setConversations(conversationList);
      setDocuments(documentList);
      setSelectedId((current) =>
        current && conversationList.some((c) => c.id === current)
          ? current
          : (conversationList[0]?.id ?? null)
      );
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSidebar();
  }, [loadSidebar]);

  if (isWorkspaceLoading) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }
  if (!currentWorkspace) {
    return <p className="text-muted-foreground text-sm">Select or create a workspace first.</p>;
  }
  if (isLoading) {
    return <p className="text-muted-foreground text-sm">Loading conversations…</p>;
  }

  const documentsById = new Map(documents.map((document) => [document.id, document]));

  return (
    <div className="flex flex-col gap-3">
      <ModelStatusBanner />
      <div className="flex min-h-[calc(100vh-14rem)] flex-col gap-4 sm:flex-row">
      <ConversationList
        workspaceId={currentWorkspace.id}
        conversations={conversations}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onCreated={(conversation) => {
          setConversations((prev) => [conversation, ...prev]);
          setSelectedId(conversation.id);
        }}
        onRenamed={(updated) => {
          setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
        }}
        onDeleted={(id) => {
          setConversations((prev) => prev.filter((c) => c.id !== id));
          setSelectedId((current) => (current === id ? null : current));
        }}
      />
      {selectedId ? (
        <ConversationThread
          key={selectedId}
          workspaceId={currentWorkspace.id}
          conversationId={selectedId}
          documentsById={documentsById}
        />
      ) : (
        <Card className="flex flex-1 items-center justify-center">
          <CardContent className="flex flex-col items-center gap-2 text-center">
            <MessageSquareText className="size-6 text-slate-300" aria-hidden="true" />
            <p className="text-muted-foreground text-sm">
              Start a new conversation to ask a question.
            </p>
          </CardContent>
        </Card>
      )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <ProtectedRoute>
      <ChatContent />
    </ProtectedRoute>
  );
}
