import { expect, test } from "@playwright/test";

import { registerViaUi } from "./fixtures/auth-helpers";
import { TEST_PASSWORD, uniqueEmail } from "./fixtures/users";

/** Browser-level smoke test for Issue #5, Slice 5.1's primary flow:
 * LOGIN -> WORKSPACE -> UPLOAD DOCUMENT -> DOCUMENT PROCESSES -> READY
 * -> OPEN CHAT -> ASK QUESTION -> SHOW ANSWER -> SHOW CITATIONS. Runs
 * against the real frontend, real backend, real PostgreSQL, real Redis
 * (no mocks), matching this project's other E2E specs. One `test.describe.serial`
 * block sharing one page/session, mirroring `auth.spec.ts`'s own
 * rationale (one shared peer IP against the base rate limiter).
 */
test.describe.serial("Upload a document and ask a grounded question about it", () => {
  const email = uniqueEmail("docschat");

  test("registers, creates a workspace, uploads and processes a document, then gets a grounded, cited answer", async ({
    page,
  }) => {
    await registerViaUi(page, email, TEST_PASSWORD);

    // Create a workspace.
    await page.goto("/workspace");
    await page.getByLabel("New workspace name").fill("Docs Chat E2E");
    await page.getByRole("button", { name: "Create" }).click();
    // `CardTitle` renders a styled `<div>`, not a semantic heading, and
    // the workspace name also appears in the nav's workspace-switcher
    // `<select>` — scope to the main content area to disambiguate.
    await expect(page.getByRole("main").getByText("Docs Chat E2E", { exact: true })).toBeVisible();

    // Upload a document whose content is real, extractable text.
    await page.goto("/documents");
    await page.setInputFiles("#document-upload", {
      name: "refund-policy.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Our refund policy allows returns within thirty days of purchase. " +
          "Contact customer support with your order number to start a return."
      ),
    });
    await expect(page.getByText("refund-policy.txt")).toBeVisible();

    // Wait for the pipeline to reach READY (polled every 3s by the page
    // itself) — a generous timeout since extraction/cleaning/chunking/
    // embedding/indexing all run synchronously, in-request, on the
    // backend's own `/process` call.
    await expect(page.getByText("READY")).toBeVisible({ timeout: 30_000 });

    // Ask a question in Chat and verify a real, grounded, cited answer.
    await page.goto("/chat");
    await page.getByRole("button", { name: "New conversation" }).click();
    await expect(page.getByText("Ask a question to get started.")).toBeVisible();

    await page.getByLabel("Ask a question").fill("What is the refund policy?");
    // `exact: true` -- Issue #6 added a second "Ask by voice" button to
    // the same form, which a plain substring match would also resolve.
    await page.getByRole("button", { name: "Ask", exact: true }).click();

    await expect(page.getByText(/refund policy/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/refund-policy\.txt/)).toBeVisible();
  });
});
