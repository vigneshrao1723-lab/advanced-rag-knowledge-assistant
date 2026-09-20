import { expect, test } from "@playwright/test";

const apiBaseUrl = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

test.describe("Application availability", () => {
  test("home page loads with no fatal console errors", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      // Chromium logs any non-2xx network response as a console "error"
      // regardless of whether the application handles it — and it always
      // will here: on mount, `lib/auth-context.tsx` asks
      // `GET /api/v1/users/me` "am I logged in?", which correctly and
      // intentionally returns 401 for a genuinely anonymous visitor
      // (caught immediately, `setUser(null)`). That is expected,
      // already-tested behavior, not a fatal error — a real unhandled
      // exception is what `pageerror` below exists to catch instead.
      if (message.text().startsWith("Failed to load resource:")) return;
      consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    const response = await page.goto("/");
    expect(response?.ok()).toBeTruthy();
    await expect(page.getByRole("link", { name: "Advanced RAG Knowledge Assistant" })).toBeVisible();

    expect(consoleErrors, `Unexpected browser console errors:\n${consoleErrors.join("\n")}`).toEqual(
      []
    );
  });

  test("an unauthenticated visitor sees the log in / register entry points", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Register" })).toBeVisible();
  });

  test("the backend readiness endpoint the application depends on is reachable and ready", async ({
    request,
  }) => {
    const response = await request.get(`${apiBaseUrl}/api/v1/health/ready`);
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.status).toBe("ready");
  });
});
