import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockPush = vi.fn();

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

import { CommandPalette } from "@/components/command-palette";

const mockSetCurrentWorkspaceId = vi.fn();

function mockAuthenticated() {
  useAuthMock.mockReturnValue({ isAuthenticated: true });
}

function mockWorkspaces() {
  useWorkspaceMock.mockReturnValue({
    workspaces: [
      { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
      { id: "w2", name: "Beta", created_at: "", updated_at: "", my_role: "MEMBER" },
    ],
    currentWorkspace: { id: "w1", name: "Acme", created_at: "", updated_at: "", my_role: "OWNER" },
    setCurrentWorkspaceId: mockSetCurrentWorkspaceId,
  });
}

describe("CommandPalette", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when unauthenticated", () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false });
    useWorkspaceMock.mockReturnValue({
      workspaces: [],
      currentWorkspace: null,
      setCurrentWorkspaceId: vi.fn(),
    });

    render(<CommandPalette />);

    expect(screen.queryByRole("button", { name: /open command palette/i })).not.toBeInTheDocument();
  });

  it("opens via the visible trigger button and lists navigation actions", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.click(screen.getByRole("button", { name: /open command palette/i }));

    expect(screen.getByRole("dialog", { name: /command palette/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /go to documents/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /go to collections/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /go to search/i })).toBeInTheDocument();
  });

  it("opens with Ctrl+K from anywhere on the page", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.keyboard("{Control>}k{/Control}");

    expect(screen.getByRole("dialog", { name: /command palette/i })).toBeInTheDocument();
  });

  it("filters actions as the query changes", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.click(screen.getByRole("button", { name: /open command palette/i }));
    await user.type(screen.getByLabelText(/search actions/i), "collections");

    expect(screen.getByRole("option", { name: /go to collections/i })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /go to documents/i })).not.toBeInTheDocument();
  });

  it("navigates via Enter after arrow-key selection, then closes", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.click(screen.getByRole("button", { name: /open command palette/i }));
    await user.keyboard("{ArrowDown}{Enter}");

    expect(mockPush).toHaveBeenCalledWith("/documents");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("runs an action on click", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.click(screen.getByRole("button", { name: /open command palette/i }));
    await user.click(screen.getByRole("option", { name: /go to search/i }));

    expect(mockPush).toHaveBeenCalledWith("/search");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.click(screen.getByRole("button", { name: /open command palette/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lists a switch-workspace action for a non-current workspace", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.click(screen.getByRole("button", { name: /open command palette/i }));
    await user.click(screen.getByRole("option", { name: /switch workspace to "beta"/i }));

    expect(mockSetCurrentWorkspaceId).toHaveBeenCalledWith("w2");
  });

  it("does not list the current workspace as a switch target", async () => {
    mockAuthenticated();
    mockWorkspaces();
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.click(screen.getByRole("button", { name: /open command palette/i }));

    expect(
      screen.queryByRole("option", { name: /switch workspace to "acme"/i })
    ).not.toBeInTheDocument();
  });
});
