import { liveIntegrationHealth } from "@/services/auth/bff.server";
import { getDashboardDataMode } from "@/services/api/server";
export const dynamic = "force-dynamic";
export function GET(request: Request) {
  if (getDashboardDataMode() !== "live")
    return Response.json(
      { error: { code: "live_mode_required" } },
      { status: 424 },
    );
  return liveIntegrationHealth(request);
}
