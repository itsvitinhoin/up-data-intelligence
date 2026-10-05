import { test, expect } from "@playwright/test";
import { claims, mockedAuth } from "../fixtures/product-auth";
test("live admin preserves the approved shell, search and brand cards using only server catalog", async ({
  page,
}) => {
  await mockedAuth(page, "ADMIN_UP");
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Uma visão completa/ }),
  ).toBeVisible();
  await page.getByLabel("E-mail", { exact: true }).fill(claims.email);
  await page
    .getByLabel("Senha", { exact: true })
    .fill("OfflineSyntheticPassword!2026");
  await page
    .getByRole("button", { name: "Entrar", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL("/admin");
  await expect(
    page.getByRole("navigation", { name: "Administração UP", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".sidebar .brand-name")).toHaveText("UP Admin");
  await expect(
    page.getByRole("heading", { name: "Controle de marcas." }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Pesquisar marca", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".workspace-grid.brand-integrations > .card"),
  ).toHaveCount(1);
  await expect(page.getByText("Lume Studio", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("Ambiente demonstrativo", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("DEV · Acesso interno", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("combobox", { name: /ERP de/ })).toBeDisabled();
  await page.getByRole("button", { name: /Ver integração de/ }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Edição de credenciais e integrações ainda indisponível",
  );
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Criar marca", exact: true }).click();
  await expect(
    page.getByRole("dialog").getByLabel("Nome da marca"),
  ).toBeVisible();
  await expect(
    page
      .getByRole("dialog")
      .getByText("Cadastro seguro da marca.", { exact: false }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Ver Dashboard de/ }).click();
  await expect(page).toHaveURL("/b2b");
  await expect(
    page.getByRole("navigation", { name: "Principal", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "ERP", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Campanhas", exact: true }),
  ).toBeVisible();
});
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
