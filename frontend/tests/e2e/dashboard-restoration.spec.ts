import { test, expect, type Page } from "@playwright/test";
import { claims, mockedAuth } from "../fixtures/product-auth";
import * as data from "../fixtures/restoration";
import { restorationResources as resources } from "../fixtures/restoration-routes";
async function ready(page: Page, path: string) {
  await page.goto(path);
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    /Dados reais/,
  );
  await expect(
    page.getByText("Dados demonstrativos", { exact: true }),
  ).toHaveCount(0);
}
test("authenticated original tree: real adapter contracts, dialogs, tabs, filters, search and mobile", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await mockedAuth(page);
  await resources(page);
  await page.goto("/");
  await page.getByLabel("E-mail", { exact: true }).fill(claims.email);
  await page
    .getByLabel("Senha", { exact: true })
    .fill("OfflineSyntheticPassword!2026");
  await page
    .getByRole("button", { name: "Entrar", exact: true })
    .first()
    .click();
  await ready(page, "/b2b");
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toContainText("50,01");
  await expect(
    page.getByRole("region", { name: "Indicadores de Leads" }),
  ).toBeVisible();
  await ready(page, "/b2b/commercial");
  await expect(page.locator(".screen-table-body tr")).toHaveCount(1);
  await page.locator(".screen-table-body button").first().click();
  await expect(page.getByRole("dialog")).toContainText("SKU-sintético");
  await expect(page.getByRole("dialog")).toContainText("Solicitado");
  await page.keyboard.press("Escape");
  await ready(page, "/b2b/customers");
  await expect(page.getByLabel("Filtrar clientes")).toBeVisible();
  await page.getByLabel("Filtrar clientes").fill("não encontrado");
  await expect(page.locator(".screen-table-body a")).toHaveCount(0);
  await page.getByLabel("Filtrar clientes").fill("Comprador");
  await page.locator(".screen-table-body a").first().click();
  await expect(page.locator(".profile-strip")).toContainText(
    data.customer.name,
  );
  await expect(
    page.getByRole("tab", { name: "Jornada", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".timeline")).toContainText(
    "Touchpoint de mídia observado",
  );
  await page.getByRole("tab", { name: "Pedidos", exact: true }).click();
  await page.locator(".screen-table-body button").first().click();
  await expect(page.getByRole("dialog")).toContainText("SKU-sintético");
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: "Produtos", exact: true }).click();
  await page.locator(".screen-table-body .prod").first().click();
  await expect(page.getByRole("dialog")).toContainText("Estoque e grade");
  await page.keyboard.press("Escape");
  await page
    .getByRole("tab", { name: "Mídia e campanhas", exact: true })
    .click();
  await expect(
    page.getByText("Campanha sintética", { exact: true }),
  ).toBeVisible();
  await ready(page, "/b2b/products");
  await page.locator(".screen-table-body .prod").first().click();
  await expect(page.getByRole("dialog")).toContainText("Desempenho comercial");
  await expect(page.getByRole("dialog")).toContainText("não disponível");
  await page.keyboard.press("Escape");
  await ready(page, "/b2b/geography");
  await expect(page.locator(".brazil-map path")).toHaveCount(27);
  await page.getByRole("button", { name: /São Paulo:/ }).click();
  await expect(
    page.getByText("Cidade sintética", { exact: true }).first(),
  ).toBeVisible();
  await ready(page, "/b2b/performance");
  await expect(page.locator(".metrics .metric")).toHaveCount(8);
  await expect(
    page.getByRole("heading", {
      name: "Faturamento × Investimento por período",
    }),
  ).toBeVisible();
  await expect(
    page.locator(".metric").filter({ hasText: "Investimento em mídias" }),
  ).toContainText(/R\$\s*100/);
  await ready(page, "/campaigns/meta");
  await expect(
    page.locator(".marketing-rankings .creative-ranking"),
  ).toHaveCount(3);
  await expect(page.locator(".creative-rank")).toHaveCount(3);
  await page
    .getByRole("button", { name: "Ver criativo Anúncio sintético — Maior CTR" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Métricas reportadas pelo Meta por anúncio",
  );
  await expect(page.getByRole("dialog")).not.toContainText(
    "métricas sintéticas",
  );
  await expect(page.getByRole("dialog")).toContainText("Compras Meta");
  await page.keyboard.press("Escape");
  await page.getByLabel("Buscar campanha").fill("inexistente");
  await expect(page.locator(".screen-table-body a")).toHaveCount(0);
  await page.getByLabel("Buscar campanha").fill("sintética");
  await page.locator(".screen-table-body a").first().click();
  await expect(
    page.getByRole("tab", { name: "Clientes influenciados" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Pedidos influenciados" }).click();
  await page.locator(".screen-table-body button").first().click();
  await expect(page.getByRole("dialog")).toContainText("SKU-sintético");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Buscar cliente/ }).click();
  await page
    .getByRole("dialog")
    .getByPlaceholder("Nome da empresa")
    .fill("Comprador");
  await page
    .getByRole("dialog")
    .locator('.search-results a[href="/customers/synthetic-customer"]')
    .click();
  await expect(page.locator(".profile-strip")).toContainText(
    data.customer.name,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await ready(page, "/b2b/products");
  await expect(page.locator(".screen-table-body .prod").first()).toBeVisible();
  await page.locator(".screen-table-body .prod").first().click();
  await expect(page.getByRole("dialog")).toContainText("Estoque e grade");
  await page.keyboard.press("Escape");
  expect(errors).toEqual([]);
});
