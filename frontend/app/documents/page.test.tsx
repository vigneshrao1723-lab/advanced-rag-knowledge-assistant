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
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    processDocument: vi.fn(),
  };
});

import * as api from "@/lib/api-client";
import DocumentsPage from "@/app/documents/page";

const OWNER_USER = { id: "owner-1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" };
const WORKSPACE = { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" as const };

function mockAuthenticated() {
  useAuthMock.mockReturnValue({ user: OWNER_USER, isAuthenticated: true, isLoading: false });
}

function mockWorkspace(role: "OWNER" | "MEMBER" | "VIEWER" = "OWNER") {
  useWorkspaceMock.mockReturnValue({
    workspaces: [{ ...WORKSPACE, my_role: role }],
    currentWorkspace: { ...WORKSPACE, my_role: role },
    isLoading: false,
  });
}

describe("DocumentsPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists uploaded documents with their status", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listDocuments).mockResolvedValue([
      {
        id: "d1",
        filename: "report.pdf",
        mime_type: "application/pdf",
        size_bytes: 2048,
        checksum_sha256: "abc",
        status: "READY",
        page_count: 3,
        failure_reason: null,
        created_at: "",
        updated_at: "",
      },
    ]);

    render(<DocumentsPage />);

    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
  });

  it("shows an empty state when no documents exist", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listDocuments).mockResolvedValue([]);

    render(<DocumentsPage />);

    expect(await screen.findByText(/no documents uploaded yet/i)).toBeInTheDocument();
  });

  it("uploads a file and triggers processing", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listDocuments).mockResolvedValue([]);
    vi.mocked(api.uploadDocument).mockResolvedValue({
      id: "d1",
      filename: "notes.txt",
      mime_type: "text/plain",
      size_bytes: 10,
      checksum_sha256: "abc",
      status: "UPLOADED",
      page_count: null,
      failure_reason: null,
      created_at: "",
      updated_at: "",
    });
    vi.mocked(api.processDocument).mockResolvedValue({
      id: "d1",
      filename: "notes.txt",
      mime_type: "text/plain",
      size_bytes: 10,
      checksum_sha256: "abc",
      status: "PROCESSING",
      page_count: null,
      failure_reason: null,
      created_at: "",
      updated_at: "",
    });
    const user = userEvent.setup();
    const file = new File(["hello world"], "notes.txt", { type: "text/plain" });

    render(<DocumentsPage />);
    await screen.findByLabelText(/upload a document/i);
    await user.upload(screen.getByLabelText(/upload a document/i), file);

    await waitFor(() => expect(api.uploadDocument).toHaveBeenCalledWith("w1", file));
    await waitFor(() => expect(api.processDocument).toHaveBeenCalledWith("w1", "d1"));
  });

  it("hides the upload control for a VIEWER", async () => {
    mockAuthenticated();
    mockWorkspace("VIEWER");
    vi.mocked(api.listDocuments).mockResolvedValue([]);

    render(<DocumentsPage />);

    await screen.findByText(/no documents uploaded yet/i);
    expect(screen.queryByLabelText(/upload a document/i)).not.toBeInTheDocument();
  });

  it("prompts to select a workspace when none is current", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({ workspaces: [], currentWorkspace: null, isLoading: false });

    render(<DocumentsPage />);

    expect(await screen.findByText(/select or create a workspace/i)).toBeInTheDocument();
  });
});
