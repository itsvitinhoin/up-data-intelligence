import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";
const config: NextConfig = {
  poweredByHeader: false,
  turbopack: { root: fileURLToPath(new URL(".", import.meta.url)) },
  devIndicators: false,
};
export default config;
