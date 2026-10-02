import { handleInstallationBridge } from "@/services/api/installation-bridge.server";
export const dynamic = "force-dynamic";
export function GET(request: Request) {
  return handleInstallationBridge(request);
}
