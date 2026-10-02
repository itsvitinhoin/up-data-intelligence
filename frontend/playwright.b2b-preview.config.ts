import { defineConfig } from "@playwright/test";
const live = process.env.DASHBOARD_E2E_LIVE === "1";
export default defineConfig({
  testDir: "tests/e2e",
  testMatch: live
    ? "b2b-real-preview.spec.ts"
    : ["b2b-real-preview.spec.ts", "installation.spec.ts"],
  workers: 1,
  fullyParallel: false,
  timeout: 90000,
  // 30s bounds the functional DEV live test; it is not an application SLO.
  // Measure query_duration_ms/bytes_processed separately; production needs its own cache/read model and SLO.
  expect: { timeout: live ? 30000 : 5000 },
  outputDir: "test-results/b2b-preview",
  use: {
    baseURL: live ? "http://127.0.0.1:3100" : "http://127.0.0.1:3115",
    viewport: { width: 1440, height: 1050 },
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
    screenshot: "off",
    trace: "off",
  },
  // Offline: only Next on a separate port, every bridge response intercepted in the spec.
  // No Python process, backend URL, token or GCP access. Live: operator starts both separately.
  webServer: live
    ? undefined
    : {
        command:
          "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3115",
        url: "http://127.0.0.1:3115",
        reuseExistingServer: false,
        env: {
          DASHBOARD_DATA_MODE: "read-api-preview",
          DASHBOARD_OFFLINE_TEST: "1",
          DASHBOARD_READ_API_BASE_URL: "",
          DASHBOARD_DEV_PREVIEW_TOKEN: "",
        },
      },
});
