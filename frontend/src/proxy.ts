import { NextResponse, type NextRequest } from "next/server";
export function proxy(request: NextRequest) {
  if (process.env.DASHBOARD_DATA_MODE !== "live") return NextResponse.next();
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ].join("; ");
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  // External identity headers are never trusted by the BFF.
  headers.delete("x-up-session");
  headers.delete("x-dashboard-preview-token");
  headers.delete("x-up-admin-preview-token");
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
export const config = {
  matcher: "/((?!_next/static|_next/image|favicon.ico).*)",
};
