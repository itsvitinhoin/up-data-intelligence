import { authMutation } from "@/services/auth/bff.server";
import { getDashboardDataMode } from "@/services/api/server";
export function POST(request: Request) {
  return getDashboardDataMode() === "live"
    ? authMutation(request, "logout")
    : new Response(null, { status: 404 });
}
