import { test, expect } from "@playwright/test";

test("compares B2B metrics and clients using the previous equal-length demo period", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  // This test must never contact a live bridge/backend.
  await page.route("**/api/dashboard/**", (route) => route.abort());
  await page.goto("/");
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name: /Maria/ }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("button", { name: "B2B", exact: true }).click();
  await expect(page).toHaveURL(/\/b2b$/);
  const revenue = page.getByRole("region", { name: "Indicadores de Receita" });
  await expect(
    revenue.getByText("Comparação indisponível").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: /Filtrar período/ }).click();
  await page.getByLabel("Data de início", { exact: true }).fill("2026-09-16");
  await page.getByLabel("Data de fim", { exact: true }).fill("2026-09-30");
  await page.getByRole("button", { name: /Aplicar/ }).click();
  await expect(revenue.getByText("vs. período anterior").first()).toBeVisible();
  await expect(revenue.locator(".metric-comparison").first()).toContainText(
    "Anterior:",
  );
  await expect(revenue.locator(".metric-comparison").first()).toHaveAttribute(
    "title",
    /01\/09\/2026 – 15\/09\/2026/,
  );
  await page.locator('nav a[href="/b2b/customers"]').first().click();
  await expect(
    page.getByRole("region", { name: "Indicadores de clientes" }),
  ).toContainText("vs. período anterior");
  await page.locator('nav a[href="/b2b/retention"]').first().click();
  await expect(
    page.getByRole("region", { name: "Indicadores de Retenção" }),
  ).toContainText("vs. período anterior");
  await expect(
    page.getByRole("region", { name: "Indicadores de Retenção" }),
  ).toContainText("p.p.");
  expect(errors).toEqual([]);
});

test("compares B2C and campaign metrics and keeps missing financial/inventory coverage explicit", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/dashboard/**", (route) => route.abort());
  await page.goto("/");
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name: /Maria/ }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("button", { name: "B2C", exact: true }).click();
  await page.getByRole("button", { name: /Filtrar período/ }).click();
  await page.getByLabel("Data de início", { exact: true }).fill("2026-09-16");
  await page.getByLabel("Data de fim", { exact: true }).fill("2026-09-30");
  await page.getByRole("button", { name: /Aplicar/ }).click();
  const overview = page.getByRole("region", { name: "Indicadores B2C" });
  await expect(
    overview.locator(".metric").filter({ hasText: "Faturamento Captado" }),
  ).toContainText("vs. período anterior");
  await expect(
    overview.locator(".metric").filter({ hasText: "Faturamento Aprovado" }),
  ).toContainText("Comparação indisponível");
  await page.locator('nav a[href="/b2c/performance"]').first().click();
  await expect(
    page
      .getByRole("region", { name: "Indicadores de Performance B2C" })
      .locator(".metric")
      .filter({ hasText: "Investimento em Meta" }),
  ).toContainText("vs. período anterior");
  await page.locator("nav").getByRole("button", { name: "Campanhas" }).click();
  await page.locator('nav a[href="/campaigns/meta"]').first().click();
  await expect(
    page.getByRole("region", { name: "Indicadores de Marketing" }),
  ).toContainText("vs. período anterior");
  await expect
    .poll(() =>
      page
        .locator(".metric")
        .evaluateAll((nodes) =>
          nodes.every(
            (node) => getComputedStyle(node.parentElement!).opacity === "1",
          ),
        ),
    )
    .toBe(true);
  await page.screenshot({
    path: "/tmp/up-metric-comparison-ready.png",
    fullPage: true,
  });
  await page.locator('nav a[href="/b2c/stock"]').first().click();
  const inventory = page.getByRole("region", {
    name: "Indicadores de estoque B2C",
  });
  await expect(inventory).toContainText("Comparação indisponível");
  await expect(inventory.getByText("vs. período anterior")).toHaveCount(0);
  expect(errors).toEqual([]);
});
