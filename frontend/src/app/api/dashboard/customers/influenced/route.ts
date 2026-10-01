import { handleReadBridge } from "@/services/api/read-bridge.server";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  return handleReadBridge(request, "influencedCustomers");
}
