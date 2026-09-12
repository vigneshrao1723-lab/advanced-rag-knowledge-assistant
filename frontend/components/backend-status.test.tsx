import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackendStatus } from "@/components/backend-status";

describe("BackendStatus", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows ready once the backend readiness check succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        json: async () => ({ status: "ready", checks: { database: "ok" } }),
      })
    );

    render(<BackendStatus />);

    await waitFor(() =>
      expect(screen.getByText(/Backend reachable, database ready/)).toBeInTheDocument()
    );
  });

  it("shows unreachable when the fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network error")));

    render(<BackendStatus />);

    await waitFor(() => expect(screen.getByText(/Backend unreachable/)).toBeInTheDocument());
  });
});
