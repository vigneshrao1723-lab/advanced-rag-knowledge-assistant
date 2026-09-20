import { expect, test } from "@playwright/test";

import { loginViaUi, registerViaUi } from "./fixtures/auth-helpers";
import { extractResetLink, fetchMailpitMessageText, findLatestMailpitMessage } from "./fixtures/mailpit";
import { TEST_PASSWORD, TEST_PASSWORD_AFTER_RESET, uniqueEmail } from "./fixtures/users";

const apiBaseUrl = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

test.describe.serial("Password recovery", () => {
  const email = uniqueEmail("recovery");
  // Kept open across the whole block: this is the *pre-reset* session,
  // used at the end to prove a completed reset actually revokes it —
  // not just that the password changed (see the dedicated test below
  // for why "old password fails" alone doesn't prove that).
  let preResetPage: import("@playwright/test").Page;

  test.beforeAll(async ({ browser }) => {
    preResetPage = await browser.newPage();
    await registerViaUi(preResetPage, email, TEST_PASSWORD);
  });

  test.afterAll(async () => {
    await preResetPage.close();
  });

  test("requesting recovery for an existing account returns the generic, enumeration-resistant message", async ({
    page,
  }) => {
    await page.goto("/forgot-password");
    await page.getByLabel("Email").fill(email);
    await page.getByRole("button", { name: "Send reset link" }).click();

    await expect(
      page.getByText("If an account with that email exists, password reset instructions have been sent.")
    ).toBeVisible();
  });

  test("requesting recovery for a nonexistent account returns the identical message", async ({
    page,
  }) => {
    // The backend never reveals whether an email exists (enumeration
    // resistance) — the UI has no "found"/"not found" branch to begin
    // with (`app/forgot-password/page.tsx`), so the real proof is that
    // this nonexistent-email request produces the exact same visible
    // outcome as the existing-account request above.
    await page.goto("/forgot-password");
    await page.getByLabel("Email").fill(uniqueEmail("nonexistent"));
    await page.getByRole("button", { name: "Send reset link" }).click();

    await expect(
      page.getByText("If an account with that email exists, password reset instructions have been sent.")
    ).toBeVisible();
  });

  test("the recovery email arrives through the real SMTP capture and the link resets the password", async ({
    page,
  }) => {
    const message = await findLatestMailpitMessage(email, "Reset your password");
    const emailText = await fetchMailpitMessageText(message.ID);
    const resetLink = extractResetLink(emailText);

    // The reset token lives only in this URL, taken from the real
    // captured email — never typed in or fabricated by the test.
    await page.goto(resetLink);
    await expect(page.getByLabel("New password", { exact: true })).toBeVisible();

    await page.getByLabel("New password", { exact: true }).fill(TEST_PASSWORD_AFTER_RESET);
    await page.getByLabel("Confirm new password").fill(TEST_PASSWORD_AFTER_RESET);
    await page.getByRole("button", { name: "Reset password" }).click();

    await expect(page.getByText(/Your password has been reset/)).toBeVisible();
    // The reset token/link never persists to browser storage — nothing
    // beyond the URL itself ever carried it.
    const storage = await page.evaluate(() => ({
      local: { ...window.localStorage },
      session: { ...window.sessionStorage },
    }));
    expect(Object.keys(storage.local)).toHaveLength(0);
    expect(Object.keys(storage.session)).toHaveLength(0);
  });

  test("the old password no longer authenticates", async ({ page }) => {
    await loginViaUi(page, email, TEST_PASSWORD);
    // Stays on /login with the backend's own generic error — never
    // redirected in. The backend deliberately returns the same message
    // regardless of whether the email or the password was wrong
    // (`auth_service._GENERIC_LOGIN_ERROR`), so this also incidentally
    // re-confirms that enumeration-resistant behavior at login.
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByText("Incorrect email or password.")).toBeVisible();
  });

  test("the new password authenticates and reaches the dashboard", async ({ page }) => {
    await loginViaUi(page, email, TEST_PASSWORD_AFTER_RESET);
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByText(`Welcome back, ${email}`)).toBeVisible();
  });

  test("the pre-reset session's refresh capability was revoked by the reset", async () => {
    // A completed reset revokes every existing session for that user
    // (`session_repository.revoke_all_for_user`, ADR 0003). It does
    // *not* retroactively invalidate an already-issued, still-unexpired
    // access token — that's a documented, intentional trade-off (access
    // tokens are validated without a database round-trip on the hot
    // path), proven by the backend's own
    // `test_password_reset_does_not_retroactively_invalidate_an_already_issued_access_token`
    // test. The real, observable effect of revocation is that the
    // pre-reset session's *refresh* capability stops working — checked
    // directly here rather than waiting out the access token's own
    // expiry, which this suite has no need to do.
    //
    // `/api/v1/auth/refresh` is a state-changing POST, so it requires
    // the same CSRF header the app's own `lib/api-client.ts` attaches
    // automatically — read directly from the shared cookie jar here,
    // since `page.request` does not attach it on its own (see the CSRF
    // test in `auth.spec.ts` for the deliberate negative case).
    const cookies = await preResetPage.context().cookies();
    const csrfToken = cookies.find((cookie) => cookie.name === "csrf_token")?.value;
    expect(csrfToken, "csrf_token cookie must be present on the pre-reset session").toBeTruthy();

    const refreshResponse = await preResetPage.request.post(`${apiBaseUrl}/api/v1/auth/refresh`, {
      headers: { "X-CSRF-Token": csrfToken ?? "" },
    });
    expect(refreshResponse.status()).toBe(401);
  });
});
