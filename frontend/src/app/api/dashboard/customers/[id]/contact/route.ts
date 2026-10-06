import { liveRead } from "@/services/auth/bff.server";
import { getDashboardDataMode } from "@/services/api/server";
export const dynamic = "force-dynamic";
export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (getDashboardDataMode() !== "live")
    return Response.json(
      { error: { code: "authenticated_contact_required" } },
      { status: 404, headers: { "Cache-Control": "private, no-store" } },
    );
  const { id } = await context.params;
  return liveRead(request, "customerContact", id);
}
