import { expect, type Page } from "@playwright/test";
import {
  brandSummariesFixture,
  integrationHealthFixture,
  connectionConfigurationFixture,
  historyPlanFixture,
} from "./brand-integrations";
import { installationV2Fixture } from "./installation";
// Offline network emulation only. No Google credentials, live sources or private APIs.
const catalog = {
  data: {
    role: "CLIENT_USER",
    tenants: ["synthetic-tenant"],
    workspaces: [
      {
        tenant_id: "synthetic-tenant",
        brand_id: "synthetic-brand",
        workspace_operation_id: "synthetic-workspace",
        operation: "B2B",
      },
    ],
  },
};
export const claims = {
  sub: "synthetic-user",
  user_id: "synthetic-user",
  email: "synthetic@example.invalid",
  email_verified: true,
  auth_time: Math.floor(Date.now() / 1000),
  iat: Math.floor(Date.now() / 1000),
  exp: Math.floor(Date.now() / 1000) + 3600,
  aud: "synthetic-project",
  iss: "https://securetoken.google.com/synthetic-project",
  firebase: { sign_in_provider: "password" },
};
const idToken = [
  Buffer.from(JSON.stringify({ alg: "RS256", typ: "JWT" })).toString(
    "base64url",
  ),
  Buffer.from(JSON.stringify(claims)).toString("base64url"),
  "offline-signature",
].join(".");
export async function mockedAuth(
  page: Page,
  role: "CLIENT_USER" | "ADMIN_UP" = "CLIENT_USER",
) {
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({
      json: {
        apiKey: "synthetic-public-key",
        projectId: "synthetic-project",
        authDomain: "synthetic-project.firebaseapp.com",
      },
    }),
  );
  await page.route("https://identitytoolkit.googleapis.com/**", (r) => {
    const url = r.request().url();
    if (url.includes("accounts:lookup"))
      return r.fulfill({
        json: {
          users: [
            {
              localId: "synthetic-user",
              email: claims.email,
              emailVerified: true,
              providerUserInfo: [
                { providerId: "password", email: claims.email },
              ],
              passwordHash: "offline-only",
              lastLoginAt: String(Date.now()),
              createdAt: String(Date.now()),
            },
          ],
        },
      });
    return r.fulfill({
      json: {
        localId: "synthetic-user",
        email: claims.email,
        displayName: "",
        idToken,
        refreshToken: "offline-only-ephemeral",
        expiresIn: "3600",
        registered: true,
      },
    });
  });
  await page.route("**/api/auth/csrf", (r) =>
    r.fulfill({ json: { data: { csrf_token: "a".repeat(64) } } }),
  );
  await page.route("**/api/session", (r) =>
    r.request().headers()["cookie"]?.includes("__Host-up_session=offline")
      ? r.fulfill({ json: { data: { ...catalog.data, role } } })
      : r.fulfill({
          status: 401,
          json: { error: { code: "unauthenticated" } },
        }),
  );
  await page.route("**/api/auth/session", async (r) => {
    expect(r.request().headers()["x-up-csrf"]).toBe("a".repeat(64));
    await page.context().addCookies([
      {
        name: "__Host-up_session",
        value: "offline",
        url: "https://127.0.0.1:3119",
        secure: true,
        httpOnly: true,
        sameSite: "Lax",
        expires: Date.now() / 1000 + 43200,
      },
    ]);
    await r.fulfill({ json: { data: { authenticated: true } } });
  });
  await page.route("**/api/auth/logout", async (r) => {
    expect(r.request().method()).toBe("POST");
    expect(r.request().headers()["x-up-csrf"]).toBe("a".repeat(64));
    await page.context().clearCookies();
    await r.fulfill({ json: { data: { authenticated: false } } });
  });
  await page.route("**/api/admin/brands", (r) =>
    r.fulfill({ json: brandSummariesFixture() }),
  );
  await page.route("**/api/admin/integrations/health?**", (r) =>
    r.fulfill({ json: integrationHealthFixture() }),
  );
  await page.route("**/api/admin/integrations/configuration?**", (r) => {
    expect(r.request().method()).toBe("GET"); // Never rotate for browser acceptance.
    return r.fulfill({ json: connectionConfigurationFixture() });
  });
  let historyRequested = false;
  await page.route("**/api/admin/integrations/history?**", (r) => {
    if (r.request().method() === "POST") {
      expect(r.request().headers()["x-up-csrf"]).toBe("a".repeat(64));
      expect(r.request().postDataJSON()).toEqual({
        provider: "upzero",
        from: "2026-08-01",
        to: "2026-08-31",
      });
      historyRequested = true;
      return r.fulfill({ status: 202, json: { data: historyPlanFixture() } });
    }
    return r.fulfill({
      json: { data: historyRequested ? [historyPlanFixture()] : [] },
    });
  });
  await page.route("**/api/dashboard/**", async (r) => {
    if (r.request().url().includes("/installation"))
      return r.fulfill({ json: installationV2Fixture() });
    return r.fulfill({
      status: 424,
      json: { error: { code: "coverage_not_certified" } },
    });
  });
}
