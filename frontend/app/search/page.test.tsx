import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
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
    search: vi.fn(),
  };
});

import * as api from "@/lib/api-client";
import SearchPage from "@/app/search/page";

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

describe("SearchPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("searches and renders ranked results with source info", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.search).mockResolvedValue({
      query: "refund policy",
      method: "hybrid",
      results: [
        {
          rank: 0,
          chunk_id: "c1",
          document_id: "d1",
          document_filename: "policy.txt",
          page: null,
          section: null,
          content: "Our refund policy allows returns within thirty days.",
          score: 0.92,
        },
      ],
    });
    const user = userEvent.setup();

    render(<SearchPage />);
    await user.type(screen.getByLabelText(/search query/i), "refund policy");
    await user.click(screen.getByRole("button", { name: /^search$/i }));

    expect(api.search).toHaveBeenCalledWith("w1", "refund policy");
    expect(await screen.findByText("policy.txt")).toBeInTheDocument();
    expect(
      screen.getByText("Our refund policy allows returns within thirty days.")
    ).toBeInTheDocument();
  });

  it("shows a no-results message for an empty result set", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.search).mockResolvedValue({ query: "nonsense", method: "hybrid", results: [] });
    const user = userEvent.setup();

    render(<SearchPage />);
    await user.type(screen.getByLabelText(/search query/i), "nonsense");
    await user.click(screen.getByRole("button", { name: /^search$/i }));

    expect(await screen.findByText(/no results for "nonsense"/i)).toBeInTheDocument();
  });

  it("prompts to select a workspace when none is current", async () => {
    mockAuthenticated();
    useWorkspaceMock.mockReturnValue({ workspaces: [], currentWorkspace: null, isLoading: false });

    render(<SearchPage />);

    expect(await screen.findByText(/select or create a workspace/i)).toBeInTheDocument();
  });
});
