import { liveHistory } from "@/services/auth/bff.server";
export const runtime = "nodejs";
export const GET = (request: Request) => liveHistory(request);
export const POST = (request: Request) => liveHistory(request);
