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
  };
});

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
});
