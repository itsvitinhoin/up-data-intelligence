import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "onboarding.spec.ts",
  workers: 1,
  timeout: 90000,
  expect: { timeout: 5000 },
  use: {
    baseURL: "http://127.0.0.1:3116",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
    trace: "off",
    screenshot: "off",
  },
  outputDir: "test-results/onboarding",
  webServer: {
    command:
      "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3116",
    url: "http://127.0.0.1:3116",
    reuseExistingServer: false,
    env: {
      UP_ADMIN_ONBOARDING_DEV: "1",
      UP_ADMIN_API_BASE_URL: "",
      UP_ADMIN_DEV_TOKEN: "",
      DASHBOARD_OFFLINE_TEST: "1",
      DASHBOARD_DATA_MODE: "read-api-preview",
      DASHBOARD_READ_API_BASE_URL: "",
      DASHBOARD_DEV_PREVIEW_TOKEN: "",
    },
  },
});
