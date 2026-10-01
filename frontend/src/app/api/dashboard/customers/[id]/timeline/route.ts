import { handleReadBridge } from "@/services/api/read-bridge.server";
export const dynamic = "force-dynamic";
export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return handleReadBridge(request, "timeline", id);
}
