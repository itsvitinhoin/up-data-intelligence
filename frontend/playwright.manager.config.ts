import { defineConfig } from "@playwright/test";
const demo = process.env.MANAGER_TEST_MODE === "demo";
export default defineConfig({
  testDir: "tests/e2e",
  testMatch: demo ? "manager-demo.spec.ts" : "manager-live.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 120000,
  expect: { timeout: 15000 },
  outputDir: "test-results/manager",
  use: {
    baseURL: demo ? "http://127.0.0.1:3120" : "https://127.0.0.1:3119",
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 1050 },
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
    screenshot: "off",
    trace: "off",
    video: "off",
  },
  webServer: {
    command: demo
      ? "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3120"
      : "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3119 --experimental-https --experimental-https-key /tmp/product19-offline.key --experimental-https-cert /tmp/product19-offline.crt",
    url: demo ? "http://127.0.0.1:3120" : "https://127.0.0.1:3119",
    reuseExistingServer: false,
    ignoreHTTPSErrors: true,
    env: {
      DASHBOARD_DATA_MODE: demo ? "demo" : "live",
      UP_DASHBOARD_TEMPLATE: "manager-v2",
      UP_READ_SERVICE_URL: "",
      UP_ADMIN_SERVICE_URL: "",
    },
  },
});
