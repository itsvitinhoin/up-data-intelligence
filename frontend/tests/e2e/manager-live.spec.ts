import { test, expect, type Page } from "@playwright/test";
import { claims, mockedAuth } from "../fixtures/product-auth";
import { envelope } from "../fixtures/restoration";
import { restorationResources } from "../fixtures/restoration-routes";
import { mkdir } from "node:fs/promises";
async function signIn(
  page: Page,
  role: "CLIENT_USER" | "ADMIN_UP" = "CLIENT_USER",
) {
  await mockedAuth(page, role);
  await restorationResources(page);
  await page.route("**/api/dashboard/funnel?**", (r) =>
    r.fulfill({
      json: {
        ...envelope({
          totals: Object.fromEntries(
            [
              "sessions",
              "product_views",
              "add_to_cart",
              "checkout_started",
              "purchase",
              "sessions_with_cart",
              "sessions_cart_then_checkout",
              "sessions_cart_checkout_purchase",
              "sessions_with_purchase",
              "events_without_session",
            ].map((key) => [key, null]),
          ),
          session_to_cart_rate: null,
          cart_to_checkout_rate: null,
          checkout_to_purchase_rate: null,
          days: [],
        }),
      },
    }),
  );
  await page.goto("/");
  await page.getByLabel("E-mail", { exact: true }).fill(claims.email);
  await page
    .getByLabel("Senha", { exact: true })
    .fill("OfflineSyntheticPassword!2026");
  await page
    .getByRole("button", { name: "Entrar", exact: true })
    .first()
    .click();
}
async function capture(page: Page, name: string) {
  await mkdir("/tmp/data19c/visuals", { recursive: true });
  await page.screenshot({
    path: `/tmp/data19c/visuals/${name}.png`,
    fullPage: true,
  });
}
test("manager B2B: controlled nav, unavailable semantics, widgets and detail reuse", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await signIn(page);
  const paths = [
    ["/b2b", "overview"],
    ["/b2b/performance", "performance"],
    ["/b2b/performance/funnel", "funnel"],
    ["/b2b/performance/new-customers", "new-customers"],
    ["/b2b/performance/repurchase", "repurchase"],
    ["/b2b/ecommerce/overview", "ecommerce"],
    ["/b2b/erp/overview", "erp"],
    ["/b2b/whatsapp/analysis", "whatsapp"],
  ];
  for (const [path, name] of paths) {
    await page.goto(path);
    await expect(page.locator("main .page-head h1").first()).toBeVisible();
    await expect(page.locator(".page-loader")).toHaveCount(0);
    await expect(
      page.getByRole("status", { name: "Carregando dados", exact: true }),
    ).toHaveCount(0);
    if (await page.locator(".metrics > div:has(.metric)").count())
      await expect(
        page.locator(".metrics > div:has(.metric)").last(),
      ).toHaveCSS("opacity", "1");
    await expect(
      page.getByText("Dados demonstrativos", { exact: true }),
    ).toHaveCount(0);
    await capture(page, `b2b-${name}`);
  }
  await page.goto("/b2b");
  await expect(
    page.getByText("Faturamento pago Ecommerce", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".metric")
      .filter({ hasText: "Faturamento pago Ecommerce" })
      .locator(".metric-value"),
  ).toHaveText("—");
  await page
    .getByRole("button", { name: "Personalizar Dashboard", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Indicadores", exact: true })
    .uncheck();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("region", { name: "Indicadores de gestão" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Personalizar Dashboard", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Restaurar página", exact: true })
    .click();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("region", { name: "Indicadores de gestão" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Personalizar Dashboard", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Descer metrics", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Tamanho de metrics", exact: true })
    .click();
  await page.getByRole("option", { name: "Meia largura", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(page.locator(".manager-widget").first()).toHaveAttribute(
    "data-widget",
    "commercial-trend",
  );
  await expect(page.locator('[data-widget="metrics"]')).toHaveClass(
    /manager-widget--half/,
  );
  await page
    .getByRole("button", { name: "Personalizar Dashboard", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Página inicial", exact: true })
    .click();
  await page
    .getByRole("option", {
      name: "Performance · Funil de Conversão",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Página inicial", exact: true }),
  ).toContainText("Funil de Conversão");
  await page
    .getByRole("button", { name: "Restaurar template", exact: true })
    .click();
  await page.keyboard.press("Escape");
  await page.goto("/b2b/ecommerce/orders");
  await page.locator(".screen-table-body button").first().click();
  await expect(page.getByRole("dialog")).toContainText("SKU-sintético");
  await page.keyboard.press("Escape");
  await page.goto("/b2b/ecommerce/products");
  await page.locator(".screen-table-body .prod").first().click();
  await expect(page.getByRole("dialog")).toContainText("Estoque e grade");
  await page.keyboard.press("Escape");
  await page.goto("/customers/synthetic-customer");
  let calls = 0;
  await page.route(
    "**/api/dashboard/customers/synthetic-customer/contact?**",
    (r) => {
      calls++;
      return r.fulfill({
        json: {
          data: {
            basis: "current_core_profile",
            observed_at: null,
            cpf: null,
            cnpj: null,
            email: "synthetic@example.invalid",
            phone: null,
          },
        },
      });
    },
  );
  expect(calls).toBe(0);
  await page.getByRole("button", { name: "Ver contato", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "synthetic@example.invalid",
  );
  await page.keyboard.press("Escape");
  await expect(
    page.getByText("synthetic@example.invalid", { exact: true }),
  ).toHaveCount(0);
  expect(calls).toBe(1);
  expect(errors).toEqual([]);
});
test("manager admin keeps secret/configuration/health/history dialogs and V1 access", async ({
  page,
}) => {
  await signIn(page, "ADMIN_UP");
  await expect(
    page.getByRole("heading", { name: /Controle de marcas/ }),
  ).toBeVisible();
  await capture(page, "admin");
  await page
    .getByRole("button", { name: "Configurar integrações" })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("Configurada");
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Saúde das integrações" })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("UP Zero");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Extrair histórico" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Cobertura");
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: /^Ver Dashboard de/ })
    .first()
    .click();
  await page
    .getByRole("button", { name: "Personalizar Dashboard", exact: true })
    .click();
  await page.getByRole("combobox", { name: "Template", exact: true }).click();
  await page
    .getByRole("option", { name: "Padrão atual · V1", exact: true })
    .click();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: /Sua operação em perspectiva/ }),
  ).toBeVisible();
});

test("unavailable funnel terminates in a failure, never an endless skeleton", async ({
  page,
}) => {
  await signIn(page);
  await page.route("**/api/dashboard/funnel?**", (r) =>
    r.fulfill({
      status: 424,
      json: { error: { code: "coverage_not_certified" } },
    }),
  );
  await page.goto("/b2b/performance/funnel");
  await expect(
    page
      .getByRole("heading", { name: "Não foi possível carregar os dados." })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByRole("status", { name: "Carregando dados" }),
  ).toHaveCount(0);
});
