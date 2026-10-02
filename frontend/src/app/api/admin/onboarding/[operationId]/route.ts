import { handleOnboardingBridge } from "@/services/api/onboarding-bridge.server";
export const dynamic = "force-dynamic";
export async function GET(
  request: Request,
  context: { params: Promise<{ operationId: string }> },
) {
  return handleOnboardingBridge(request, (await context.params).operationId);
}
