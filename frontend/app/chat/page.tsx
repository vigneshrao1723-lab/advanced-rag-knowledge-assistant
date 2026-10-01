"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { Citation, Conversation, Document, Message } from "@/lib/schemas";
import { startVoiceRecording, type VoiceRecorder } from "@/lib/voice-recorder";
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
        <form onSubmit={handleRenameSubmit} className="flex flex-col gap-1 px-1 py-1">
          <label htmlFor={`rename-${conversation.id}`} className="sr-only">
            Conversation title
          </label>
          <input
            id={`rename-${conversation.id}`}
            autoFocus
            value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
            className="border-input bg-background rounded-md border px-2 py-1 text-sm"
          />
          <div className="flex gap-1">
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
    <li className="group flex items-center gap-1">
      <button
        type="button"
        onClick={() => onSelect(conversation.id)}
        className={`min-w-0 flex-1 truncate rounded-md px-3 py-2 text-left text-sm transition-colors ${
          isSelected ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
        }`}
      >
        {conversation.title ?? `Conversation ${conversation.id.slice(0, 8)}`}
      </button>
      <button
        type="button"
        aria-label="Rename conversation"
        disabled={isBusy}
        onClick={() => {
          setTitleDraft(conversation.title ?? "");
          setIsRenaming(true);
        }}
        className="text-muted-foreground hover:text-foreground shrink-0 px-1 text-xs opacity-0 group-hover:opacity-100"
      >
        Rename
      </button>
      <button
        type="button"
        aria-label="Delete conversation"
        disabled={isBusy}
        onClick={handleDelete}
        className="text-muted-foreground hover:text-destructive shrink-0 px-1 text-xs opacity-0 group-hover:opacity-100"
      >
        Delete
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
    <div className="flex w-64 shrink-0 flex-col gap-3">
      <Button size="sm" disabled={isCreating} onClick={handleCreate}>
        {isCreating ? "Starting…" : "New conversation"}
      </Button>
      {conversations.length > 0 && (
        <div>
          <label htmlFor="conversation-search" className="sr-only">
            Search conversations
          </label>
          <input
            id="conversation-search"
            type="search"
            placeholder="Search conversations…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="border-input bg-background w-full rounded-md border px-2 py-1 text-sm"
          />
        </div>
      )}
      {error && <p className="text-destructive text-sm">{error}</p>}
      {conversations.length === 0 ? (
        <p className="text-muted-foreground text-sm">No conversations yet.</p>
      ) : filtered.length === 0 ? (
        <p className="text-muted-foreground text-sm">No conversations match &quot;{query}&quot;.</p>
      ) : (
        <ul className="flex flex-col gap-1">
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
        className="text-left underline decoration-dotted underline-offset-2 hover:text-foreground"
      >
        [{citation.rank}] {label} {isLoading ? "(loading…)" : isOpen ? "▲" : "▼"}
      </button>
      {error && <p className="text-destructive">{error}</p>}
      {isOpen && content !== null && (
        <blockquote className="border-border text-foreground mt-1 max-w-prose border-l-2 py-1 pl-2 whitespace-pre-wrap">
          {content}
        </blockquote>
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
        aria-label="Good response"
        aria-pressed={message.feedback === "UP"}
        onClick={() => handleRate("UP")}
        className={`rounded px-1 text-xs ${message.feedback === "UP" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
      >
        👍
      </button>
      <button
        type="button"
        aria-label="Bad response"
        aria-pressed={message.feedback === "DOWN"}
        onClick={() => handleRate("DOWN")}
        className={`rounded px-1 text-xs ${message.feedback === "DOWN" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
      >
        👎
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
  onFeedbackChanged,
}: {
  workspaceId: string;
  conversationId: string;
  message: Message;
  documentsById: Map<string, Document>;
  onFeedbackChanged: (message: Message) => void;
}) {
  const isUser = message.role === "USER";
  return (
    <div className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
          isUser ? "bg-primary text-primary-foreground" : "bg-accent text-accent-foreground"
        }`}
      >
        {message.content}
      </div>
      {!isUser && !message.id.startsWith("pending-") && (
        <div className="flex items-center gap-2">
          <AudioPlaybackButton
            workspaceId={workspaceId}
            conversationId={conversationId}
            messageId={message.id}
          />
          <FeedbackButtons
            workspaceId={workspaceId}
            conversationId={conversationId}
            message={message}
            onChanged={onFeedbackChanged}
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
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<VoiceRecorder | null>(null);

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
      // The optimistic user bubble is left in place rather than removed
      // -- it reflects what the user actually asked, and reopening this
      // conversation later shows the real persisted state regardless.
    } finally {
      setIsSending(false);
    }
  }

  async function handleRecordToggle() {
    setSendError(null);
    if (isRecording) {
      // Interrupt/stop: clicking again while recording stops it and
      // transcribes whatever was captured so far, rather than requiring
      // a fixed recording duration.
      setIsRecording(false);
      setIsTranscribing(true);
      try {
        const audioBlob = await recorderRef.current?.stop();
        recorderRef.current = null;
        if (!audioBlob) return;
        const { transcript, message: assistantMessage } = await api.postVoiceMessage(
          workspaceId,
          conversationId,
          audioBlob
        );
        setMessages((prev) => [
          ...prev,
          {
            id: `pending-${prev.length}`,
            role: "USER",
            content: transcript,
            created_at: new Date().toISOString(),
            citations: [],
            feedback: null,
          },
          assistantMessage,
        ]);
      } catch (err) {
        setSendError(err instanceof ApiError ? err.message : "Could not process that recording.");
      } finally {
        setIsTranscribing(false);
      }
      return;
    }

    try {
      recorderRef.current = await startVoiceRecording();
      setIsRecording(true);
    } catch {
      setSendError("Could not access the microphone.");
    }
  }

  return (
    <Card className="flex flex-1 flex-col">
      <CardHeader>
        <CardTitle>Chat</CardTitle>
        <CardDescription>Ask a question about your workspace&apos;s documents.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="flex min-h-64 flex-1 flex-col gap-3 overflow-y-auto">
          {isLoading ? (
            <p className="text-muted-foreground text-sm">Loading…</p>
          ) : loadError ? (
            <p className="text-destructive text-sm">{loadError}</p>
          ) : messages.length === 0 ? (
            <p className="text-muted-foreground text-sm">Ask a question to get started.</p>
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                workspaceId={workspaceId}
                conversationId={conversationId}
                message={message}
                documentsById={documentsById}
                onFeedbackChanged={(updated) =>
                  setMessages((prev) => prev.map((m) => (m.id === updated.id ? updated : m)))
                }
              />
            ))
          )}
          <div ref={bottomRef} />
        </div>
        <form className="flex items-end gap-2" onSubmit={handleSubmit}>
          <div className="flex flex-1 flex-col gap-1.5">
            <label htmlFor="chat-question" className="sr-only">
              Ask a question
            </label>
            <input
              id="chat-question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question…"
              disabled={isSending}
              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
            />
          </div>
          <Button type="submit" disabled={isSending || !question.trim()}>
            {isSending ? "Asking…" : "Ask"}
          </Button>
          <Button
            type="button"
            variant={isRecording ? "destructive" : "outline"}
            disabled={isTranscribing}
            onClick={handleRecordToggle}
          >
            {isRecording ? "Stop recording" : isTranscribing ? "Transcribing…" : "Ask by voice"}
          </Button>
        </form>
        {sendError && <p className="text-destructive text-sm">{sendError}</p>}
      </CardContent>
    </Card>
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
    <div className="flex flex-col gap-4 sm:flex-row">
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
          <CardContent>
            <p className="text-muted-foreground text-sm">
              Start a new conversation to ask a question.
            </p>
          </CardContent>
        </Card>
      )}
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
