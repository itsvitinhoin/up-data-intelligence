import { handleOnboardingBridge } from "@/services/api/onboarding-bridge.server";
export const dynamic = "force-dynamic";
export function POST(request: Request) {
  return handleOnboardingBridge(request);
}
