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

function ConversationList({
  workspaceId,
  conversations,
  selectedId,
  onSelect,
  onCreated,
}: {
  workspaceId: string;
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreated: (conversation: Conversation) => void;
}) {
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="flex w-64 shrink-0 flex-col gap-3">
      <Button size="sm" disabled={isCreating} onClick={handleCreate}>
        {isCreating ? "Starting…" : "New conversation"}
      </Button>
      {error && <p className="text-destructive text-sm">{error}</p>}
      {conversations.length === 0 ? (
        <p className="text-muted-foreground text-sm">No conversations yet.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {conversations.map((conversation) => (
            <li key={conversation.id}>
              <button
                type="button"
                onClick={() => onSelect(conversation.id)}
                className={`w-full truncate rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  selectedId === conversation.id
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent/50"
                }`}
              >
                {conversation.title ?? `Conversation ${conversation.id.slice(0, 8)}`}
              </button>
            </li>
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

function MessageBubble({
  workspaceId,
  conversationId,
  message,
  documentsById,
}: {
  workspaceId: string;
  conversationId: string;
  message: Message;
  documentsById: Map<string, Document>;
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
        <AudioPlaybackButton
          workspaceId={workspaceId}
          conversationId={conversationId}
          messageId={message.id}
        />
      )}
      {message.citations.length > 0 && (
        <ul className="text-muted-foreground flex flex-col gap-0.5 text-xs">
          {message.citations.map((citation) => (
            <li key={`${message.id}-${citation.rank}`}>
              [{citation.rank}] {citationLabel(citation, documentsById)}
            </li>
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
