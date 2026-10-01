import { test, expect, type Page } from "@playwright/test";
// Synthetic offline envelopes only. Live opt-in uses the exact same traversal without fixtures.
const live = process.env.DASHBOARD_E2E_LIVE === "1";
const metadata = {
  contract_version: "1.0.0",
  store_id: "mx-fashion",
  generation: 7,
  policy_hash: "a".repeat(64),
  currency: "BRL",
  reporting_timezone: "America/Sao_Paulo",
  as_of: "2026-09-28T03:00:00Z",
  report_from: "2026-09-01",
  report_to: "2026-09-28",
  history_complete: false,
  facts_complete: true,
  limitations: ["history_incomplete"],
};
const customer = {
  store_id: "mx-fashion",
  customer_id: "synthetic-customer",
  customer_type: "B2B",
  name: "Comprador sintético",
  state: null,
  city: null,
  purchases_observed: 1,
  first_purchase_at_observed: "2026-09-02T12:00:00Z",
  requested_lifetime_observed: "50.00",
  ltv_complete: null,
};
const order = {
  store_id: "mx-fashion",
  customer_id: customer.customer_id,
  order_id: "synthetic-order",
  created_at: "2026-09-02T12:00:00Z",
  order_status: "CONFIRMED",
  payment_status: "unpaid",
  requested_total: "50.00",
  fulfilled_total: null,
  requested_items_qty: 2,
  fulfilled_items_qty: null,
};
const values: Record<string, unknown> = {
  overview: {
    requested_revenue: "86319.62",
    fulfilled_revenue: "73220.13",
    fulfillment_gap: "13099.49",
    fulfillment_rate: "0.8482443504732759481563982789",
    cancelled_requested_revenue: "6262.75",
    orders_requested: 18,
    orders_cancelled: 2,
    buyers_observed: 16,
    recurring_buyers_observed: 0,
    purchase_frequency_observed: "1",
    new_customers_confirmed: null,
    ltv_complete: null,
    cac: null,
    revenue_paid: null,
    series: [
      {
        date: "2026-09-01",
        requested: "86319.62",
        fulfilled: "73220.13",
        orders: 18,
        new_customers_confirmed: null,
      },
    ],
  },
  orders: [order],
  customers: [customer],
  acquisition: {
    buyers_observed: 16,
    first_purchase_customers_observed: 16,
    first_purchase_orders_observed: 16,
    requested_first_purchase_observed: "80000.00",
    fulfilled_first_purchase_observed: "72000.00",
    confirmed_new_customers: null,
  },
  retention: {
    buyers_observed: 16,
    recurring_buyers_observed: 0,
    retention_observed: "0",
    retention_ticket_observed: null,
    frequency_observed: "1",
    progression: [1, 2, 3, 4].map((from_purchase) => ({
      from_purchase,
      to_purchase: from_purchase === 4 ? "5+" : String(from_purchase + 1),
      customers_reached_observed: 0,
      continuation_observed: from_purchase === 1 ? "0" : null,
      mean_days_observed: null,
      median_days_observed: null,
    })),
    cohorts: [
      {
        cohort_month: "2026-09-01",
        reporting_month: "2026-09-01",
        month: 0,
        buyers_observed: 16,
        rate: null,
        observed_rate: null,
        period_complete: false,
      },
    ],
  },
  products: [
    {
      store_id: "mx-fashion",
      product_key: "synthetic-product",
      product_id: null,
      sku: "SYNTHETIC-SKU",
      name: null,
      requested_revenue: "50.00",
      fulfilled_revenue: null,
      units_requested: "2",
      units_fulfilled: null,
      orders_observed: 1,
      buyers_unique: null,
    },
  ],
};
async function mocks(page: Page) {
  await page.route("**/api/dashboard/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("workspace_operation_id") !== "mx-fashion-b2b") {
      await route.fulfill({
        status: 404,
        json: { error: { code: "preview_binding_absent" } },
      });
      return;
    }
    const path = url.pathname.replace("/api/dashboard/", "");
    if (path === "geography") {
      await route.fulfill({
        status: 424,
        json: { error: { code: "geography_coverage_not_certified" } },
      });
      return;
    }
    const isDetail = path.startsWith("customers/") && !path.endsWith("/orders");
    const data = isDetail
      ? {
          profile: customer,
          commercial: {
            qualifying_orders_observed: 1,
            requested_revenue_observed: "50.00",
            fulfilled_revenue_observed: null,
            first_purchase_at_observed: customer.first_purchase_at_observed,
            last_purchase_at_observed: customer.first_purchase_at_observed,
            ltv_complete: null,
          },
        }
      : path.endsWith("/orders")
        ? [order]
        : values[path];
    if (data === undefined)
      throw new Error("Unexpected resource in offline traversal");
    await route.fulfill({
      json: {
        data,
        pagination: Array.isArray(data)
          ? { page_size: 25, cursor: null, has_more: false }
          : null,
        metadata,
      },
    });
  });
}
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
test("one-round B2B V1 traversal: real, partial and explicitly unavailable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  if (!live) await mocks(page);
  await login(page);
  await realBadge(page);
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toContainText("86.319,62");
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toContainText("73.220,13");
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    "Dados reais · Histórico parcial",
  );
  await expect(page.locator(".period-trigger")).toBeEnabled();
  await expect(page.locator(".period-trigger")).toContainText(
    "01/09/2026 – 27/09/2026",
  );
  await expect(page.locator("footer.note")).toContainText("Dados reais");
  await expect(page.locator("footer.note")).toContainText("Histórico parcial");
  await expect(page.locator(".print-context")).toContainText(
    "Dados reais · Histórico parcial",
  );
  await nav(page, "/b2b/commercial");
  await realBadge(page);
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await nav(page, "/b2b/acquisition");
  await realBadge(page);
  await expect(
    page.getByRole("heading", {
      name: "Primeira compra observada",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page
      .locator(".metric")
      .filter({ hasText: "Novos confirmados" })
      .locator(".metric-value"),
  ).toHaveText("—");
  await nav(page, "/b2b/retention");
  await realBadge(page);
  await expect(
    page.getByRole("heading", { name: "Progressão de compras", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".purchase-stage")).toHaveCount(4);
  await nav(page, "/b2b/customers");
  await realBadge(page);
  await page.locator("tbody tr a").first().click();
  await realBadge(page);
  await expect(
    page.getByRole("heading", { name: "Resumo do cliente", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Pedidos observados do cliente",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await expect(page.locator(".timeline")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: /Campanhas participantes/ }),
  ).toHaveCount(0);
  await expect(
    page.getByText(/Ainda não disponível nesta geração/),
  ).toBeVisible();
  await page.goBack();
  await realBadge(page);
  await nav(page, "/b2b/products");
  await realBadge(page);
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: /Estoque|Grade|ABC|Views/ }),
  ).toHaveCount(0);
  await nav(page, "/b2b/geography");
  await expect(
    page.getByText(
      "Cobertura geográfica ainda não certificada para esta publicação.",
    ),
  ).toBeVisible();
  await expect(page.locator(".brazil-map path")).toHaveCount(27);
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    "Cobertura ainda não disponível",
  );
  await expect(page.locator("tbody tr")).toHaveCount(0);
  await nav(page, "/b2b/performance");
  await expect(
    page.getByText(
      "Performance e influência aguardam materialização das camadas de mídia.",
    ),
  ).toBeVisible();
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    "Cobertura ainda não disponível",
  );
  await expect(page.locator(".metric")).toHaveCount(0);
  await expect(page.locator("tbody tr")).toHaveCount(0);
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
  if (!live) await mocks(page);
  await login(page, "Gestor Lume");
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    "Dados demonstrativos",
  );
});

test("offline cursor pagination resets after a status change; read failure never renders fixtures", async ({
  page,
}) => {
  test.skip(
    live,
    "Offline error/next-page injection only; never replace live results.",
  );
  await mocks(page);
  let unavailable = false;
  await page.route("**/api/dashboard/orders?**", async (route) => {
    if (unavailable) {
      await route.fulfill({
        status: 503,
        json: { error: { code: "read_temporarily_unavailable" } },
      });
      return;
    }
    const params = new URL(route.request().url()).searchParams;
    const second = params.has("cursor");
    await route.fulfill({
      json: {
        metadata,
        data: [
          {
            ...order,
            order_id: second ? "synthetic-next-page" : "synthetic-first-page",
            order_status: params.get("status") ?? "CONFIRMED",
          },
        ],
        pagination: {
          page_size: 25,
          cursor: second ? null : "synthetic-opaque-cursor",
          has_more: !second,
        },
      },
    });
  });
  await login(page);
  await nav(page, "/b2b/commercial");
  await expect(page.locator("tbody")).toContainText("synthetic-first-page");
  await page.getByRole("button", { name: "Próxima", exact: true }).click();
  await expect(page.locator("tbody")).toContainText("synthetic-next-page");
  await page.getByRole("combobox", { name: "Status do pedido" }).click();
  await page.getByRole("option", { name: "CANCELED", exact: true }).click();
  await expect(page.locator("tbody")).toContainText("synthetic-first-page");
  await expect(
    page.getByRole("button", { name: "Anterior", exact: true }),
  ).toBeDisabled();
  unavailable = true;
  await page.getByRole("combobox", { name: "Status do pedido" }).click();
  await page.getByRole("option", { name: "SHIPPED", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Não foi possível carregar os dados." }),
  ).toBeVisible();
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    "Dados reais indisponíveis",
  );
  await expect(page.locator("tbody tr")).toHaveCount(0);
});
