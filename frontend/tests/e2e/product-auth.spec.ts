import { test, expect, type Page } from "@playwright/test";
import { installationV2Fixture } from "../fixtures/installation";
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
const claims = {
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
async function mockedAuth(page: Page) {
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
      ? r.fulfill({ json: catalog })
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
  await page.route("**/api/dashboard/**", async (r) => {
    if (r.request().url().includes("/installation"))
      return r.fulfill({ json: installationV2Fixture() });
    return r.fulfill({
      status: 424,
      json: { error: { code: "coverage_not_certified" } },
    });
  });
}
test("live login → server catalog → unavailable real data → logout, with no persisted browser token", async ({
  page,
}) => {
  await mockedAuth(page);
  await page.goto("/b2b");
  await expect(page.getByLabel("E-mail", { exact: true })).toBeVisible();
  await expect(page.getByText("Usuário demonstrativo")).toHaveCount(0);
  await page.getByLabel("E-mail", { exact: true }).fill(claims.email);
  await page
    .getByLabel("Senha", { exact: true })
    .fill("OfflineSyntheticPassword!2026");
  await page
    .getByRole("button", { name: "Entrar", exact: true })
    .first()
    .click();
  await expect(page.getByLabel("E-mail", { exact: true })).toHaveCount(0);
  await page.goto("/b2b");
  await expect(
    page
      .getByText(/Cobertura ainda não|Dados reais indisponíveis/)
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByText("Dados demonstrativos", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: /Buscar cliente/ }).click();
  await expect(
    page.getByRole("dialog").getByText("Cobertura ainda não certificada"),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog").locator(".search-results a"),
  ).toHaveCount(1);
  await page.keyboard.press("Escape");
  const storage = await page.evaluate(async () => ({
    local: Object.keys(localStorage),
    session: Object.keys(sessionStorage),
    cookie: document.cookie,
    databases: (await indexedDB.databases()).map((d) => d.name ?? ""),
  }));
  expect(storage.local).not.toEqual(
    expect.arrayContaining([expect.stringMatching(/firebase.*auth|token/i)]),
  );
  expect(storage.session).not.toEqual(
    expect.arrayContaining([expect.stringMatching(/firebase.*auth|token/i)]),
  );
  expect(storage.cookie).not.toContain("__Host-up_session");
  expect(storage.databases.filter((d) => /firebase.*auth/i.test(d))).toEqual(
    [],
  );
  const session = (await page.context().cookies()).find(
    (c) => c.name === "__Host-up_session",
  )!;
  expect(session.secure).toBe(true);
  expect(session.httpOnly).toBe(true);
  expect(session.sameSite).toBe("Lax");
  await page.getByRole("button", { name: /Sair/ }).click();
  await expect(page.getByLabel("E-mail", { exact: true })).toBeVisible();
  await page.goto("/customers");
  await expect(page.getByLabel("E-mail", { exact: true })).toBeVisible();
});
test("first access and password reset explain verification without granting product access", async ({
  page,
}) => {
  await mockedAuth(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Primeiro acesso", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Primeiro acesso" }),
  ).toBeVisible();
  await page.getByLabel("E-mail", { exact: true }).fill(claims.email);
  await page
    .getByLabel("Senha", { exact: true })
    .fill("OfflineSyntheticPassword!2026");
  await page.getByRole("button", { name: "Criar conta", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "A criação da conta não concede acesso",
  );
  expect(
    (await page.context().cookies()).some(
      (c) => c.name === "__Host-up_session",
    ),
  ).toBe(false);
  await page
    .getByRole("button", { name: "Esqueci minha senha", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Enviar instruções", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Se houver uma conta válida",
  );
});
