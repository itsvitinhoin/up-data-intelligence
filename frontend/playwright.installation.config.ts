import { defineConfig } from "@playwright/test";
// Offline only. The caller starts and verifies the local server separately.
// Every read/write API in these specs is intercepted with synthetic responses.
export default defineConfig({
  testDir: "tests/e2e",
  testMatch: ["installation.spec.ts", "onboarding.spec.ts"],
  workers: 1,
  timeout: 90000,
  expect: { timeout: 5000 },
  outputDir: "test-results/installation",
  use: {
    baseURL: "http://127.0.0.1:3117",
    viewport: { width: 1440, height: 1050 },
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
    screenshot: "off",
    trace: "off",
  },
});
