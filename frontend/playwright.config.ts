import { defineConfig, devices } from "@playwright/test";

/**
 * Browser-level E2E coverage for the authentication/password-recovery
 * flows (docs/DEPLOYMENT.md). Runs against the real frontend, real
 * backend, real PostgreSQL, real Redis, and real Mailpit — no mocks —
 * matching this project's established "no mock substitute for the real
 * datastore" precedent (ADR 0002/0006 §16), extended here to the full
 * stack. Assumes those services are already running and reachable
 * (`docker compose -f infra/compose/docker-compose.yml up`, or CI's own
 * equivalent job) — this config does not start them.
 *
 * `workers: 1` / `fullyParallel: false` is deliberate, not a default
 * left alone: the backend's own rate limiters (base token buckets and
 * the deterministic abuse layer, ADR 0006) key partly by source IP, and
 * every Playwright-driven request in this run shares the same peer
 * address. Running specs in parallel would risk spurious 429s unrelated
 * to what any individual test is actually checking — a real
 * consequence of this project's own security design, not something to
 * route around by weakening it. Each spec file is also deliberately
 * economical with how many `register`/`login`/`forgot-password` calls
 * it makes for the same reason.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  timeout: 30_000,
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
