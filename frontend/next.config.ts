import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";
const config: NextConfig = {
  poweredByHeader: false,
  // Next dev normally logs full request URLs; identifiers/query strings stay private.
  logging:
    process.env.DASHBOARD_DATA_MODE === "read-api-preview" ? false : undefined,
  // Separate artifacts/lock for offline browser tests; never select a data adapter here.
  distDir:
    process.env.NODE_ENV === "development" &&
    process.env.DASHBOARD_OFFLINE_TEST === "1"
      ? ".next-offline"
      : ".next",
  turbopack: { root: fileURLToPath(new URL(".", import.meta.url)) },
  devIndicators: false,
};
export default config;
