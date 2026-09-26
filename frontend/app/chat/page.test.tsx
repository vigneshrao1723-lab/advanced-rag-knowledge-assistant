import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

const useAuthMock = vi.fn();
const useWorkspaceMock = vi.fn();

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock("@/lib/workspace-context", () => ({
  useWorkspace: () => useWorkspaceMock(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    listDocuments: vi.fn(),
    listMessages: vi.fn(),
    postMessage: vi.fn(),
    postVoiceMessage: vi.fn(),
  };
});

const mockStartVoiceRecording = vi.fn();
vi.mock("@/lib/voice-recorder", () => ({
  startVoiceRecording: () => mockStartVoiceRecording(),
}));

import * as api from "@/lib/api-client";
import ChatPage from "@/app/chat/page";

const OWNER_USER = { id: "owner-1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" };
const WORKSPACE = { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" as const };

function mockAuthenticated() {
  useAuthMock.mockReturnValue({ user: OWNER_USER, isAuthenticated: true, isLoading: false });
}

function mockWorkspace() {
  useWorkspaceMock.mockReturnValue({
    workspaces: [WORKSPACE],
    currentWorkspace: WORKSPACE,
    isLoading: false,
  });
}

describe("ChatPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows a prompt to start a conversation when there are none yet", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listConversations).mockResolvedValue([]);
    vi.mocked(api.listDocuments).mockResolvedValue([]);

    render(<ChatPage />);

    expect(await screen.findByText(/start a new conversation/i)).toBeInTheDocument();
  });

  it("creates a conversation and selects it", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listConversations).mockResolvedValue([]);
    vi.mocked(api.listDocuments).mockResolvedValue([]);
    vi.mocked(api.createConversation).mockResolvedValue({
      id: "c1",
      title: null,
      created_at: "",
      updated_at: "",
    });
    vi.mocked(api.listMessages).mockResolvedValue([]);
    const user = userEvent.setup();

    render(<ChatPage />);
    await screen.findByText(/start a new conversation/i);
    await user.click(screen.getByRole("button", { name: /new conversation/i }));

    await waitFor(() => expect(api.createConversation).toHaveBeenCalledWith("w1"));
    expect(await screen.findByText(/ask a question to get started/i)).toBeInTheDocument();
  });

  it("loads an existing conversation's messages with citations", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listConversations).mockResolvedValue([
      { id: "c1", title: "First question", created_at: "", updated_at: "" },
    ]);
    vi.mocked(api.listDocuments).mockResolvedValue([
      {
        id: "doc-1",
        filename: "refund_policy.txt",
        mime_type: "text/plain",
        size_bytes: 100,
        checksum_sha256: "abc",
        status: "READY",
        page_count: null,
        failure_reason: null,
        created_at: "",
        updated_at: "",
      },
    ]);
    vi.mocked(api.listMessages).mockResolvedValue([
      { id: "m1", role: "USER", content: "What is the refund policy?", created_at: "", citations: [] },
      {
        id: "m2",
        role: "ASSISTANT",
        content: "Based on the available documents:\n\n[1] Refunds within 30 days.",
        created_at: "",
        citations: [{ document_id: "doc-1", page: 1, section: null, rank: 1 }],
      },
    ]);

    render(<ChatPage />);

    expect(await screen.findByText(/what is the refund policy/i)).toBeInTheDocument();
    expect(screen.getByText(/refund_policy\.txt/)).toBeInTheDocument();
  });

  it("sends a question and appends the assistant's answer", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listConversations).mockResolvedValue([
      { id: "c1", title: null, created_at: "", updated_at: "" },
    ]);
    vi.mocked(api.listDocuments).mockResolvedValue([]);
    vi.mocked(api.listMessages).mockResolvedValue([]);
    vi.mocked(api.postMessage).mockResolvedValue({
      id: "m2",
      role: "ASSISTANT",
      content: "Based on the available documents:\n\n[1] Refunds within 30 days.",
      created_at: "",
      citations: [],
    });
    const user = userEvent.setup();

    render(<ChatPage />);
    await screen.findByText(/ask a question to get started/i);
    await user.type(screen.getByLabelText(/ask a question/i), "What is the refund policy?");
    await user.click(screen.getByRole("button", { name: /^ask$/i }));

    await waitFor(() =>
      expect(api.postMessage).toHaveBeenCalledWith("w1", "c1", "What is the refund policy?")
    );
    expect(await screen.findByText(/refunds within 30 days/i)).toBeInTheDocument();
  });

  it("prompts to select a workspace when none is current", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({ workspaces: [], currentWorkspace: null, isLoading: false });

    render(<ChatPage />);

    expect(await screen.findByText(/select or create a workspace/i)).toBeInTheDocument();
  });

  it("records, stops, and posts a voice message, appending the transcript and answer", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listConversations).mockResolvedValue([
      { id: "c1", title: null, created_at: "", updated_at: "" },
    ]);
    vi.mocked(api.listDocuments).mockResolvedValue([]);
    vi.mocked(api.listMessages).mockResolvedValue([]);
    const recorderStop = vi.fn().mockResolvedValue(new Blob(["audio"], { type: "audio/wav" }));
    mockStartVoiceRecording.mockResolvedValue({ stop: recorderStop, cancel: vi.fn() });
    vi.mocked(api.postVoiceMessage).mockResolvedValue({
      transcript: "what is the refund policy",
      message: {
        id: "m2",
        role: "ASSISTANT",
        content: "Refunds within 30 days.",
        created_at: "",
        citations: [],
      },
    });
    const user = userEvent.setup();

    render(<ChatPage />);
    await screen.findByText(/ask a question to get started/i);
    await user.click(screen.getByRole("button", { name: /ask by voice/i }));

    await waitFor(() => expect(mockStartVoiceRecording).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: /stop recording/i }));

    await waitFor(() => expect(recorderStop).toHaveBeenCalled());
    await waitFor(() => expect(api.postVoiceMessage).toHaveBeenCalledWith("w1", "c1", expect.any(Blob)));
    expect(await screen.findByText(/what is the refund policy/i)).toBeInTheDocument();
    expect(await screen.findByText(/refunds within 30 days/i)).toBeInTheDocument();
  });

  it("shows an error when microphone access is denied", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listConversations).mockResolvedValue([
      { id: "c1", title: null, created_at: "", updated_at: "" },
    ]);
    vi.mocked(api.listDocuments).mockResolvedValue([]);
    vi.mocked(api.listMessages).mockResolvedValue([]);
    mockStartVoiceRecording.mockRejectedValue(new Error("denied"));
    const user = userEvent.setup();

    render(<ChatPage />);
    await screen.findByText(/ask a question to get started/i);
    await user.click(screen.getByRole("button", { name: /ask by voice/i }));

    expect(await screen.findByText(/could not access the microphone/i)).toBeInTheDocument();
  });

  it("plays and stops an assistant message's synthesized audio", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listConversations).mockResolvedValue([
      { id: "c1", title: null, created_at: "", updated_at: "" },
    ]);
    vi.mocked(api.listDocuments).mockResolvedValue([]);
    vi.mocked(api.listMessages).mockResolvedValue([
      {
        id: "m1",
        role: "ASSISTANT",
        content: "Refunds within 30 days.",
        created_at: "",
        citations: [],
      },
    ]);
    const play = vi.fn().mockResolvedValue(undefined);
    const pause = vi.fn();
    vi.spyOn(window.HTMLMediaElement.prototype, "play").mockImplementation(play);
    vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(pause);
    const user = userEvent.setup();

    render(<ChatPage />);
    const playButton = await screen.findByRole("button", { name: /play answer/i });
    await user.click(playButton);

    expect(play).toHaveBeenCalled();
    const stopButton = await screen.findByRole("button", { name: /^stop$/i });
    await user.click(stopButton);

    expect(pause).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /play answer/i })).toBeInTheDocument();
  });
});
