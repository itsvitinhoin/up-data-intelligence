import { handleOverviewBridge } from "@/services/api/overview-bridge.server";

export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  return handleOverviewBridge(request);
}
