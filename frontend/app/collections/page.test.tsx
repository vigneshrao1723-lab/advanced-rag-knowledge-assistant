import { render, screen } from "@testing-library/react";
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
    listCollections: vi.fn(),
    createCollection: vi.fn(),
    deleteCollection: vi.fn(),
  };
});

import * as api from "@/lib/api-client";
import CollectionsPage from "@/app/collections/page";

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

describe("CollectionsPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists collections with their document count", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listCollections).mockResolvedValue([
      {
        id: "c1",
        name: "Research",
        description: "Papers",
        created_at: "",
        updated_at: "",
        document_count: 3,
      },
    ]);

    render(<CollectionsPage />);

    expect(await screen.findByText("Research")).toBeInTheDocument();
    expect(screen.getByText("3 documents")).toBeInTheDocument();
  });

  it("shows an empty state when no collections exist", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listCollections).mockResolvedValue([]);

    render(<CollectionsPage />);

    expect(await screen.findByText(/no collections yet/i)).toBeInTheDocument();
  });

  it("creates a collection from the inline form", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listCollections).mockResolvedValue([]);
    vi.mocked(api.createCollection).mockResolvedValue({
      id: "c1",
      name: "New collection",
      description: null,
      created_at: "",
      updated_at: "",
      document_count: 0,
    });
    const user = userEvent.setup();

    render(<CollectionsPage />);
    await screen.findByText(/no collections yet/i);
    await user.type(screen.getByLabelText(/new collection name/i), "New collection");
    await user.click(screen.getByRole("button", { name: /create/i }));

    expect(api.createCollection).toHaveBeenCalledWith("w1", "New collection", null);
  });

  it("hides the create form for a VIEWER", async () => {
    mockAuthenticated();
    mockWorkspace("VIEWER");
    vi.mocked(api.listCollections).mockResolvedValue([]);

    render(<CollectionsPage />);

    await screen.findByText(/no collections yet/i);
    expect(screen.queryByLabelText(/new collection name/i)).not.toBeInTheDocument();
  });

  it("prompts to select a workspace when none is current", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({ workspaces: [], currentWorkspace: null, isLoading: false });

    render(<CollectionsPage />);

    expect(await screen.findByText(/select or create a workspace/i)).toBeInTheDocument();
  });
});
