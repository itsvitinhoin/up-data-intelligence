import { test, expect, type Page } from "@playwright/test";
import { restorationResources } from "../fixtures/restoration-routes";
import { metadata, order } from "../fixtures/restoration";
// Explicit loopback preview only. Live opt-in never intercepts real responses.
const live = process.env.DASHBOARD_E2E_LIVE === "1";
async function login(page: Page, name = "Maria") {
  await page.goto("/");
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name, exact: false }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  if (name === "Maria")
    await page.getByRole("button", { name: "B2B", exact: true }).click();
}
async function nav(page: Page, path: string) {
  await page.locator(`nav a[href="${path}"]`).first().click();
  await expect(page).toHaveURL(path);
}
async function realBadge(page: Page) {
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    /Dados reais/,
  );
  await expect(page.locator(".workspace-strip")).not.toContainText(
    "Dados demonstrativos",
  );
}
test("one-round B2B V1 traversal retains original components and explicit nulls", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (!live) await restorationResources(page, true);
  await login(page);
  await realBadge(page);
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Indicadores de Leads" }),
  ).toBeVisible();
  await expect(page.locator(".period-trigger")).toBeEnabled();
  if (!live)
    await expect(page.locator(".period-trigger")).toContainText(
      "01/09/2026 – 27/09/2026",
    );
  await nav(page, "/b2b/commercial");
  await realBadge(page);
  await page.locator(".screen-table-body button").first().click();
  await expect(page.getByRole("dialog")).toContainText("Solicitado");
  await page.keyboard.press("Escape");
  await nav(page, "/b2b/acquisition");
  await realBadge(page);
  await expect(
    page
      .locator(".metric")
      .filter({ hasText: "Novos clientes confirmados" })
      .locator(".metric-value"),
  ).toHaveText("—");
  await nav(page, "/b2b/retention");
  await realBadge(page);
  await expect(
    page.getByRole("heading", { name: "Progressão de recompra", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".purchase-stage")).toHaveCount(5);
  await nav(page, "/b2b/customers");
  await realBadge(page);
  await page.locator(".screen-table-body a").first().click();
  await expect(page.locator(".profile-strip")).toBeVisible();
  await expect(
    page.getByRole("tab", { name: "Jornada", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Pedidos", exact: true }).click();
  await expect(page.locator(".screen-table-body button").first()).toBeVisible();
  await nav(page, "/b2b/products");
  await realBadge(page);
  await page.locator(".screen-table-body .prod").first().click();
  await expect(page.getByRole("dialog")).toContainText("Estoque e grade");
  await expect(page.getByRole("dialog")).toContainText("não disponível");
  await page.keyboard.press("Escape");
  await nav(page, "/b2b/geography");
  await realBadge(page);
  await expect(page.locator(".brazil-map path")).toHaveCount(27);
  await nav(page, "/b2b/performance");
  await realBadge(page);
  await expect(page.locator(".metrics .metric")).toHaveCount(8);
  await page.getByRole("combobox", { name: "Operação da marca" }).click();
  await page
    .getByRole("option", { name: "MX Fashion · B2C", exact: true })
    .click();
  await expect(page).toHaveURL("/b2c");
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    "Dados demonstrativos",
  );
  expect(errors).toEqual([]);
});
test("unbound brand remains explicitly demo", async ({ page }) => {
  if (!live) await restorationResources(page, true);
  await login(page, "Gestor Lume");
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    "Dados demonstrativos",
  );
});
test("offline complete cursor collection, local pagination/status and unavailable read never uses fixtures", async ({
  page,
}) => {
  test.skip(live, "Offline injection only; never replace live results.");
  await restorationResources(page, true);
  let unavailable = false;
  const cursors: (string | null)[] = [];
  await page.route("**/api/dashboard/orders?**", async (route) => {
    if (unavailable)
      return route.fulfill({
        status: 503,
        json: { error: { code: "read_temporarily_unavailable" } },
      });
    const cursor = new URL(route.request().url()).searchParams.get("cursor");
    cursors.push(cursor);
    const start = cursor ? 6 : 0;
    await route.fulfill({
      json: {
        metadata: {
          ...metadata,
          store_id: "mx-fashion",
          generation: 7,
          as_of: "2026-09-28T03:00:00Z",
          report_to: "2026-09-28",
        },
        data: Array.from({ length: 6 }, (_, i) => ({
          ...order,
          store_id: "mx-fashion",
          order_id: `synthetic-${start + i}`,
          order_status: start ? "CANCELED" : "CONFIRMED",
        })),
        pagination: {
          page_size: 100,
          cursor: cursor ? null : "synthetic-opaque-cursor",
          has_more: !cursor,
        },
      },
    });
  });
  await login(page);
  await nav(page, "/b2b/commercial");
  await expect(page.locator(".screen-table-body tr")).toHaveCount(6);
  await expect(page.locator(".pagination")).toContainText("12 registros");
  await page
    .getByRole("button", { name: "Próxima página", exact: true })
    .click();
  await expect(page.locator(".screen-table-body")).toContainText("synthetic-6");
  expect(cursors).toContain("synthetic-opaque-cursor");
  await page
    .getByRole("combobox", { name: "Status do pedido", exact: true })
    .click();
  await page.getByRole("option", { name: "Cancelado", exact: true }).click();
  await expect(page.locator(".pagination")).toContainText(
    "6 registros · Página 1 de 1",
  );
  await expect(
    page.getByRole("button", { name: "Página anterior", exact: true }),
  ).toBeDisabled();
  unavailable = true;
  await login(page);
  await nav(page, "/b2b/commercial");
  await expect(
    page.getByRole("heading", { name: "Não foi possível carregar os dados." }),
  ).toBeVisible();
  await expect(page.locator(".screen-table-body tr")).toHaveCount(0);
  await expect(
    page.getByText("Dados demonstrativos", { exact: true }),
  ).toHaveCount(0);
});
test("Intelligence uses original customer tabs, Performance, Meta campaign panels and drill-down", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (!live) await restorationResources(page, true);
  await login(page);
  await realBadge(page);
  await nav(page, "/b2b/customers");
  await page.locator(".screen-table-body a").first().click();
  await realBadge(page);
  await expect(
    page.getByRole("tab", { name: "Jornada", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".timeline")).toBeVisible();
  await page.getByRole("tab", { name: "Produtos", exact: true }).click();
  await expect(page.locator(".screen-table-body .prod").first()).toBeVisible();
  await page
    .getByRole("tab", { name: "Mídia e campanhas", exact: true })
    .click();
  if (!live)
    await expect(
      page.getByText("Campanha sintética", { exact: true }),
    ).toBeVisible();
  await nav(page, "/b2b/performance");
  await realBadge(page);
  await expect(
    page.getByRole("heading", {
      name: "Faturamento × Investimento por período",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Campanhas", exact: true }).click();
  await nav(page, "/campaigns/meta");
  await realBadge(page);
  await expect(
    page.locator(".marketing-rankings .creative-ranking"),
  ).toHaveCount(3);
  if (!live) await page.getByLabel("Buscar campanha").fill("sintética");
  await page
    .locator('.screen-table-body a[href^="/campaigns/"]')
    .first()
    .click();
  await realBadge(page);
  await expect(
    page.getByRole("tab", { name: "Clientes influenciados" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Pedidos influenciados" }).click();
  await page.locator(".screen-table-body button").first().click();
  await expect(page.getByRole("dialog")).toContainText("SKU-sintético");
  await page.keyboard.press("Escape");
  expect(errors).toEqual([]);
});
