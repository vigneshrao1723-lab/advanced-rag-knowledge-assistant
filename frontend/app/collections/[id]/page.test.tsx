import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useParams: () => ({ id: "c1" }),
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
    getCollection: vi.fn(),
    updateCollection: vi.fn(),
    deleteCollection: vi.fn(),
    listDocuments: vi.fn(),
    addDocumentToCollection: vi.fn(),
    removeDocumentFromCollection: vi.fn(),
  };
});

import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import CollectionDetailPage from "@/app/collections/[id]/page";

const OWNER_USER = { id: "owner-1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" };
const WORKSPACE = { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" as const };

const DOCUMENT = {
  id: "d1",
  filename: "report.pdf",
  mime_type: "application/pdf",
  size_bytes: 2048,
  checksum_sha256: "abc",
  status: "READY" as const,
  page_count: 3,
  failure_reason: null,
  created_at: "",
  updated_at: "",
};

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

describe("CollectionDetailPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the collection's name and documents", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.getCollection).mockResolvedValue({
      id: "c1",
      name: "Research",
      description: "Papers",
      created_at: "",
      updated_at: "",
      document_count: 1,
      documents: [DOCUMENT],
    });
    vi.mocked(api.listDocuments).mockResolvedValue([DOCUMENT]);

    render(<CollectionDetailPage />);

    expect(await screen.findByText("Research")).toBeInTheDocument();
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
  });

  it("shows a not-found message for a 404", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.getCollection).mockRejectedValue(new ApiError(404, "Collection not found."));

    render(<CollectionDetailPage />);

    expect(await screen.findByText(/collection not found/i)).toBeInTheDocument();
  });

  it("adds a document via the add-document form", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.getCollection).mockResolvedValue({
      id: "c1",
      name: "Research",
      description: null,
      created_at: "",
      updated_at: "",
      document_count: 0,
      documents: [],
    });
    vi.mocked(api.listDocuments).mockResolvedValue([DOCUMENT]);
    vi.mocked(api.addDocumentToCollection).mockResolvedValue(DOCUMENT);
    const user = userEvent.setup();

    render(<CollectionDetailPage />);
    await screen.findByText(/no documents in this collection yet/i);
    await screen.findByRole("option", { name: "report.pdf" });
    await user.selectOptions(screen.getByLabelText(/add a document/i), "d1");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    expect(api.addDocumentToCollection).toHaveBeenCalledWith("w1", "c1", "d1");
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
  });

  it("removes a document from the collection", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.getCollection).mockResolvedValue({
      id: "c1",
      name: "Research",
      description: null,
      created_at: "",
      updated_at: "",
      document_count: 1,
      documents: [DOCUMENT],
    });
    vi.mocked(api.listDocuments).mockResolvedValue([DOCUMENT]);
    vi.mocked(api.removeDocumentFromCollection).mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<CollectionDetailPage />);
    await screen.findByText("report.pdf");
    await user.click(screen.getByRole("button", { name: /remove report.pdf from this collection/i }));

    expect(api.removeDocumentFromCollection).toHaveBeenCalledWith("w1", "c1", "d1");
  });
});
