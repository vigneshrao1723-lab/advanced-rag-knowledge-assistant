import { render, screen, waitFor, within } from "@testing-library/react";
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
    renameDocument: vi.fn(),
    deleteDocument: vi.fn(),
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
    // Scoped to the document row, not the page overall -- the status
    // filter dropdown also has a "READY" option elsewhere on the page.
    expect(within(screen.getByRole("listitem")).getByText("READY")).toBeInTheDocument();
    // Anchored at the start -- the download link's accessible name is
    // "Download report.pdf", which would otherwise also match.
    expect(screen.getByRole("link", { name: /^report\.pdf/i })).toHaveAttribute(
      "href",
      "/documents/d1"
    );
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

  const SAMPLE_DOCUMENT = {
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

  it("renames a document from the inline form", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listDocuments).mockResolvedValue([SAMPLE_DOCUMENT]);
    vi.mocked(api.renameDocument).mockResolvedValue({ ...SAMPLE_DOCUMENT, filename: "renamed.pdf" });
    const user = userEvent.setup();

    render(<DocumentsPage />);
    await screen.findByText("report.pdf");
    await user.click(screen.getByRole("button", { name: /rename report\.pdf/i }));
    const input = screen.getByLabelText(/document name/i);
    await user.clear(input);
    await user.type(input, "renamed.pdf");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(api.renameDocument).toHaveBeenCalledWith("w1", "d1", "renamed.pdf");
  });

  it("deletes a document after confirmation", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listDocuments).mockResolvedValue([SAMPLE_DOCUMENT]);
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();

    render(<DocumentsPage />);
    await screen.findByText("report.pdf");
    await user.click(screen.getByRole("button", { name: /delete report\.pdf/i }));

    expect(api.deleteDocument).toHaveBeenCalledWith("w1", "d1");
    await waitFor(() => expect(screen.queryByText("report.pdf")).not.toBeInTheDocument());
  });

  it("does not delete a document when the confirmation is declined", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listDocuments).mockResolvedValue([SAMPLE_DOCUMENT]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();

    render(<DocumentsPage />);
    await screen.findByText("report.pdf");
    await user.click(screen.getByRole("button", { name: /delete report\.pdf/i }));

    expect(api.deleteDocument).not.toHaveBeenCalled();
  });

  it("hides rename/delete controls for a VIEWER but still shows download", async () => {
    mockAuthenticated();
    mockWorkspace("VIEWER");
    vi.mocked(api.listDocuments).mockResolvedValue([SAMPLE_DOCUMENT]);

    render(<DocumentsPage />);

    await screen.findByText("report.pdf");
    expect(screen.queryByRole("button", { name: /rename report\.pdf/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete report\.pdf/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download report\.pdf/i })).toBeInTheDocument();
  });

  it("filters the document list by status and searches by filename", async () => {
    mockAuthenticated();
    mockWorkspace();
    vi.mocked(api.listDocuments).mockResolvedValue([SAMPLE_DOCUMENT]);
    const user = userEvent.setup();

    render(<DocumentsPage />);
    await screen.findByText("report.pdf");

    await user.selectOptions(screen.getByLabelText(/^status$/i), "READY");
    await waitFor(() =>
      expect(api.listDocuments).toHaveBeenLastCalledWith("w1", { status: "READY", q: undefined })
    );

    await user.type(screen.getByLabelText(/search by filename/i), "report");
    await waitFor(() =>
      expect(api.listDocuments).toHaveBeenLastCalledWith("w1", { status: "READY", q: "report" })
    );
  });
});
