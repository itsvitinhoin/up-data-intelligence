import { sessionResponse } from "@/services/auth/bff.server";
import { getDashboardDataMode } from "@/services/api/server";
export const dynamic = "force-dynamic";
export function GET(request: Request) {
  return getDashboardDataMode() === "live"
    ? sessionResponse(request)
    : new Response(null, { status: 404 });
}
