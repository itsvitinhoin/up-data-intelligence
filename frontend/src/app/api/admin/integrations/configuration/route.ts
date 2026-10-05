import { liveConnectionConfiguration } from "@/services/auth/bff.server";
export const runtime = "nodejs";
export const GET = (request: Request) => liveConnectionConfiguration(request);
export const POST = (request: Request) => liveConnectionConfiguration(request);
