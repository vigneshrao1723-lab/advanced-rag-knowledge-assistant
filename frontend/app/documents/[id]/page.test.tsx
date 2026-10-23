import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockSearchParamsGet = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useParams: () => ({ id: "d1" }),
  useSearchParams: () => ({ get: mockSearchParamsGet }),
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
    getDocument: vi.fn(),
    listDocumentChunks: vi.fn(),
  };
});

import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import DocumentDetailPage from "@/app/documents/[id]/page";

const OWNER_USER = { id: "owner-1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" };
const WORKSPACE = { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" as const };

const DOCUMENT = {
  id: "d1",
  filename: "report.pdf",
  mime_type: "application/pdf",
  size_bytes: 2048,
  checksum_sha256: "abc",
  status: "READY" as const,
  page_count: 2,
  failure_reason: null,
  created_at: "",
  updated_at: "",
};

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

describe("DocumentDetailPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
    mockSearchParamsGet.mockReturnValue(null);
  });

  it("renders the document's chunks in order", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.getDocument).mockResolvedValue(DOCUMENT);
    vi.mocked(api.listDocumentChunks).mockResolvedValue([
      { id: "c1", document_id: "d1", chunk_index: 0, page: 1, section: "Intro", content: "First chunk text." },
      { id: "c2", document_id: "d1", chunk_index: 1, page: 1, section: "Body", content: "Second chunk text." },
    ]);

    render(<DocumentDetailPage />);

    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByText("First chunk text.")).toBeInTheDocument();
    expect(screen.getByText("Second chunk text.")).toBeInTheDocument();
  });

  it("shows a processing message when the document has no chunks yet", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOCUMENT, status: "PROCESSING" });
    vi.mocked(api.listDocumentChunks).mockResolvedValue([]);

    render(<DocumentDetailPage />);

    expect(await screen.findByText(/still processing/i)).toBeInTheDocument();
  });

  it("shows a not-found message for a 404", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.getDocument).mockRejectedValue(new ApiError(404, "Document not found."));
    vi.mocked(api.listDocumentChunks).mockResolvedValue([]);

    render(<DocumentDetailPage />);

    expect(await screen.findByText(/document not found/i)).toBeInTheDocument();
  });

  it("highlights the chunk named by the ?chunk= query param", async () => {
    mockAuthenticated();
    mockWorkspace();
    mockSearchParamsGet.mockReturnValue("c2");
    vi.mocked(api.getDocument).mockResolvedValue(DOCUMENT);
    vi.mocked(api.listDocumentChunks).mockResolvedValue([
      { id: "c1", document_id: "d1", chunk_index: 0, page: 1, section: null, content: "First chunk text." },
      { id: "c2", document_id: "d1", chunk_index: 1, page: 1, section: null, content: "Second chunk text." },
    ]);

    render(<DocumentDetailPage />);
    await screen.findByText("Second chunk text.");

    const highlighted = screen.getByText("Second chunk text.").closest("div");
    expect(highlighted).toHaveClass("border-indigo-400");
  });
});
