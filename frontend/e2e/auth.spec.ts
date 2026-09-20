import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { loginViaUi, logoutViaUi, readBrowserStorage, registerViaUi } from "./fixtures/auth-helpers";
import { TEST_PASSWORD, uniqueEmail } from "./fixtures/users";

const apiBaseUrl = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

test.describe("Registration", () => {
  test("rejects a short password client-side, before any request is sent", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Email").fill(uniqueEmail("shortpw"));
    await page.getByLabel("Password").fill("short");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText("Password must be at least 8 characters.")).toBeVisible();
    // Still on /register — the invalid submission never reached the API.
    await expect(page).toHaveURL(/\/register$/);
  });
});

// One shared page walks the full register -> verify session -> reload
// -> logout -> protected-route journey in order. `test.describe.serial`
// only guarantees ordering (and skips the rest of the block after a
// failure) — it does not, by itself, share a `page`/context between
// tests, so the page is created once in `beforeAll` and referenced
// directly rather than through the default per-test `page` fixture.
// This also means exactly one `registerViaUi` call for the whole
// block: the backend's base rate limiter for `register` allows only 5
// requests/60s per source IP (`app/core/rate_limit.py`), and every
// Playwright request in this run shares one peer address — see
// `playwright.config.ts` for the full rationale.
test.describe.serial("Registration establishes a real, cookie-based session", () => {
  const email = uniqueEmail("journey");
  let sharedPage: Page;

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage();
  });

  test.afterAll(async () => {
    await sharedPage.close();
  });

  test("registering through the real UI reaches the dashboard", async () => {
    await registerViaUi(sharedPage, email, TEST_PASSWORD);
    await expect(sharedPage.getByText(`Welcome back, ${email}`)).toBeVisible();
  });

  test("no access token is exposed in localStorage or sessionStorage after registration", async () => {
    const storage = await readBrowserStorage(sharedPage);
    expect(Object.keys(storage.local)).toHaveLength(0);
    expect(Object.keys(storage.session)).toHaveLength(0);
  });

  test("the session survives a full page reload", async () => {
    await sharedPage.reload();
    await expect(sharedPage.getByText(`Welcome back, ${email}`)).toBeVisible();
  });

  test("logging out ends the session and the protected dashboard is no longer reachable", async () => {
    await logoutViaUi(sharedPage);
    await sharedPage.goto("/dashboard");
    await expect(sharedPage).toHaveURL(/\/login$/);
  });

  test("an unauthenticated visitor is redirected away from a protected route", async () => {
    // Fresh navigation on the same (now logged-out) page — no cookies
    // authenticate this request either way, matching a genuinely
    // unauthenticated visitor.
    await sharedPage.goto("/workspace");
    await expect(sharedPage).toHaveURL(/\/login$/);
  });
});

test.describe.serial("Login with an existing account, CSRF, and a protected mutation", () => {
  const email = uniqueEmail("login");
  let sharedPage: Page;

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage();
    await registerViaUi(sharedPage, email, TEST_PASSWORD);
    await logoutViaUi(sharedPage);
  });

  test.afterAll(async () => {
    await sharedPage.close();
  });

  test("a registered user can log in through the real UI and reach the dashboard", async () => {
    await loginViaUi(sharedPage, email, TEST_PASSWORD);
    await expect(sharedPage).toHaveURL(/\/dashboard$/);
    await expect(sharedPage.getByText(`Welcome back, ${email}`)).toBeVisible();
  });

  test("no access token is exposed in localStorage or sessionStorage after login", async () => {
    const storage = await readBrowserStorage(sharedPage);
    expect(Object.keys(storage.local)).toHaveLength(0);
    expect(Object.keys(storage.session)).toHaveLength(0);
  });

  test("a state-changing request without the CSRF header is rejected", async () => {
    // `sharedPage.request` shares this context's cookie jar (including
    // the httpOnly access-token cookie and the non-httpOnly csrf_token
    // cookie) but, unlike the app's own `lib/api-client.ts`, does not
    // automatically echo the CSRF cookie back as an `X-CSRF-Token`
    // header — exactly the request shape the double-submit pattern
    // exists to reject (ADR 0005). This exercises the real backend
    // middleware, not a stub of it.
    const response = await sharedPage.request.post(`${apiBaseUrl}/api/v1/workspaces`, {
      data: { name: "should-be-rejected" },
    });
    expect(response.status()).toBe(403);
  });

  test("creating a workspace through the real UI succeeds (CSRF header attached correctly)", async () => {
    await sharedPage.goto("/workspace");
    await expect(sharedPage.getByText("Your workspaces")).toBeVisible();

    const workspaceName = `E2E workspace ${Date.now()}`;
    await sharedPage.getByLabel("New workspace name").fill(workspaceName);
    await sharedPage.getByRole("button", { name: "Create" }).click();

    // The new workspace legitimately renders in more than one place
    // once created (the workspace switcher, the list, and its own
    // detail heading) — scoped to the main content's heading
    // specifically to avoid an unrelated strict-mode ambiguity.
    await expect(
      sharedPage.getByRole("main").getByText(workspaceName, { exact: true })
    ).toBeVisible();
  });
});
