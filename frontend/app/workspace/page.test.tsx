import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();
const mockCreateWorkspace = vi.fn();
const mockSetCurrentWorkspaceId = vi.fn();
const mockRefresh = vi.fn();

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
    listMembers: vi.fn(),
    addMember: vi.fn(),
    updateWorkspace: vi.fn(),
    deleteWorkspace: vi.fn(),
    removeMember: vi.fn(),
    updateMemberRole: vi.fn(),
  };
});

import * as api from "@/lib/api-client";
import WorkspacePage from "@/app/workspace/page";

const OWNER_USER = { id: "owner-1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" };

function mockAuthenticated() {
  useAuthMock.mockReturnValue({ user: OWNER_USER, isAuthenticated: true, isLoading: false });
}

describe("WorkspacePage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("creates a workspace via the create-workspace form", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({
      workspaces: [],
      currentWorkspace: null,
      isLoading: false,
      setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
      refresh: mockRefresh,
      createWorkspace: mockCreateWorkspace,
    });
    mockCreateWorkspace.mockResolvedValue({
      id: "w1",
      name: "New Workspace",
      created_at: "",
      updated_at: "",
      my_role: "OWNER",
    });
    const user = userEvent.setup();

    render(<WorkspacePage />);
    await user.type(screen.getByLabelText(/new workspace name/i), "New Workspace");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => expect(mockCreateWorkspace).toHaveBeenCalledWith("New Workspace"));
  });

  it("switches the current workspace when a different one is clicked", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({
      workspaces: [
        { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
        { id: "w2", name: "Beta", created_at: "", updated_at: "", my_role: "MEMBER" },
      ],
      currentWorkspace: { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
      isLoading: false,
      setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
      refresh: mockRefresh,
      createWorkspace: mockCreateWorkspace,
    });
    vi.mocked(api.listMembers).mockResolvedValue([]);
    const user = userEvent.setup();

    render(<WorkspacePage />);
    await user.click(screen.getByRole("button", { name: /beta \(member\)/i }));

    expect(mockSetCurrentWorkspaceId).toHaveBeenCalledWith("w2");
  });

  it("hides rename, delete, and add-member controls for a VIEWER", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({
      workspaces: [{ id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "VIEWER" }],
      currentWorkspace: { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "VIEWER" },
      isLoading: false,
      setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
      refresh: mockRefresh,
      createWorkspace: mockCreateWorkspace,
    });
    vi.mocked(api.listMembers).mockResolvedValue([
      { user_id: "owner-1", email: "owner@example.com", role: "OWNER", created_at: "" },
    ]);

    render(<WorkspacePage />);
    await waitFor(() => expect(api.listMembers).toHaveBeenCalled());

    expect(screen.queryByLabelText(/^workspace name$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete workspace/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/add member by email/i)).not.toBeInTheDocument();
  });

  it("shows rename, delete, and add-member controls for an OWNER", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({
      workspaces: [{ id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" }],
      currentWorkspace: { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
      isLoading: false,
      setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
      refresh: mockRefresh,
      createWorkspace: mockCreateWorkspace,
    });
    vi.mocked(api.listMembers).mockResolvedValue([
      { user_id: "owner-1", email: "owner@example.com", role: "OWNER", created_at: "" },
    ]);

    render(<WorkspacePage />);
    await waitFor(() => expect(api.listMembers).toHaveBeenCalled());

    expect(screen.getByLabelText(/^workspace name$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete workspace/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/add member by email/i)).toBeInTheDocument();
  });
});
