import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageStub } from "@/components/page-stub";

describe("PageStub", () => {
  it("renders the title, description, and target issue", () => {
    render(
      <PageStub
        title="Documents"
        description="Upload and manage documents."
        issue="Issue #3"
      />
    );

    expect(screen.getByText("Documents")).toBeInTheDocument();
    expect(screen.getByText("Upload and manage documents.")).toBeInTheDocument();
    expect(screen.getByText(/Issue #3/)).toBeInTheDocument();
  });
});
