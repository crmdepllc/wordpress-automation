import { defineConfig, devices } from "@playwright/test";

// Points at the live WP sandbox (Docker), not the Next.js dashboard — this
// suite screenshots agent-generated WordPress pages, not our own app.
const WP_BASE_URL = process.env.WP_BASE_URL ?? "http://localhost:8080";

export default defineConfig({
  testDir: "./tests-visual",
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: WP_BASE_URL,
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
