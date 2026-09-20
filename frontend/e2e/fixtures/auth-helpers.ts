import { expect, type Page } from "@playwright/test";

/** Registers through the real UI (not a direct API call) — this is
 * itself part of what's under test (form → API → cookie), not just
 * setup. Registration also auto-authenticates (`lib/auth-context.tsx`),
 * so this ends with the browser on `/dashboard`. */
export async function registerViaUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

export async function loginViaUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
}

export async function logoutViaUi(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

/** Reads what JavaScript can actually see in browser storage — the
 * thing this project's cookie-only auth model (ADR 0005) specifically
 * guarantees is empty. */
export async function readBrowserStorage(
  page: Page
): Promise<{ local: Record<string, string>; session: Record<string, string> }> {
  return page.evaluate(() => ({
    local: { ...window.localStorage },
    session: { ...window.sessionStorage },
  }));
}
