import { getDashboardDataMode } from "@/services/api/server";
import { secureHeaders } from "@/services/auth/bff.server";
export function GET() {
  if (getDashboardDataMode() !== "live")
    return new Response(null, { status: 404 });
  const projectId = process.env.UP_FIREBASE_PROJECT_ID,
    apiKey = process.env.UP_FIREBASE_API_KEY;
  if (!projectId || !apiKey) return new Response(null, { status: 503 });
  return Response.json(
    { projectId, apiKey, authDomain: projectId + ".firebaseapp.com" },
    { headers: secureHeaders },
  );
}
