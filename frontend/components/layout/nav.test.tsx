import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockPush = vi.fn();
const mockLogout = vi.fn();
const mockSetCurrentWorkspaceId = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const useAuthMock = vi.fn();
const useWorkspaceMock = vi.fn();

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock("@/lib/workspace-context", () => ({
  useWorkspace: () => useWorkspaceMock(),
}));

import { Nav } from "@/components/layout/nav";

describe("Nav", () => {
  afterEach(() => {
    mockPush.mockReset();
    mockLogout.mockReset();
    mockSetCurrentWorkspaceId.mockReset();
    useAuthMock.mockReset();
    useWorkspaceMock.mockReset();
  });

  it("shows login/register links when unauthenticated", () => {
    useAuthMock.mockReturnValue({ user: null, isAuthenticated: false, logout: mockLogout });
    useWorkspaceMock.mockReturnValue({ workspaces: [], currentWorkspace: null, setCurrentWorkspaceId: mockSetCurrentWorkspaceId });

    render(<Nav />);

    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /register/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });

  it("shows the current user and a workspace selector when authenticated", () => {
    useAuthMock.mockReturnValue({
      user: { id: "u1", email: "user@example.com", created_at: "2026-01-01T00:00:00Z" },
      isAuthenticated: true,
      logout: mockLogout,
    });
    useWorkspaceMock.mockReturnValue({
      workspaces: [
        { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
        { id: "w2", name: "Beta", created_at: "", updated_at: "", my_role: "MEMBER" },
      ],
      currentWorkspace: { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
      setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
    });

    render(<Nav />);

    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /current workspace/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Acme" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Beta" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
  });

  it("calls logout and redirects to /login when the logout button is clicked", async () => {
    mockLogout.mockResolvedValue(undefined);
    useAuthMock.mockReturnValue({
      user: { id: "u1", email: "user@example.com", created_at: "2026-01-01T00:00:00Z" },
      isAuthenticated: true,
      logout: mockLogout,
    });
    useWorkspaceMock.mockReturnValue({
      workspaces: [],
      currentWorkspace: null,
      setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
    });
    const user = userEvent.setup();

    render(<Nav />);
    await user.click(screen.getByRole("button", { name: /log out/i }));

    expect(mockLogout).toHaveBeenCalled();
  });

  it("switches workspace when a different option is selected", async () => {
    useAuthMock.mockReturnValue({
      user: { id: "u1", email: "user@example.com", created_at: "2026-01-01T00:00:00Z" },
      isAuthenticated: true,
      logout: mockLogout,
    });
    useWorkspaceMock.mockReturnValue({
      workspaces: [
        { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
        { id: "w2", name: "Beta", created_at: "", updated_at: "", my_role: "MEMBER" },
      ],
      currentWorkspace: { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
      setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
    });
    const user = userEvent.setup();

    render(<Nav />);
    await user.selectOptions(screen.getByRole("combobox", { name: /current workspace/i }), "w2");

    expect(mockSetCurrentWorkspaceId).toHaveBeenCalledWith("w2");
  });
});
