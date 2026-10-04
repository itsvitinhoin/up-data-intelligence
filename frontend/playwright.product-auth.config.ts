import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "product-auth.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 90000,
  expect: { timeout: 15000 },
  outputDir: "test-results/product-auth",
  use: {
    baseURL: "https://127.0.0.1:3119",
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
    command:
      "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3119 --experimental-https --experimental-https-key /tmp/product19-offline.key --experimental-https-cert /tmp/product19-offline.crt",
    url: "https://127.0.0.1:3119",
    reuseExistingServer: false,
    ignoreHTTPSErrors: true,
    env: {
      DASHBOARD_DATA_MODE: "live",
      UP_READ_SERVICE_URL: "",
      UP_ADMIN_SERVICE_URL: "",
    },
  },
});
