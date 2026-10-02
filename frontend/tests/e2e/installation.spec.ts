import { test, expect } from "@playwright/test";
import { installationFixture } from "../fixtures/installation";

test("Admin opens MX certified partial window; out-of-coverage request is rejected", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const state = installationFixture();
  const calls: URL[] = [];
  await page.route("**/api/dashboard/**", async (route) => {
    const url = new URL(route.request().url());
    calls.push(url);
    if (url.searchParams.get("workspace_operation_id") !== "mx-fashion-b2b") {
      await route.fulfill({
        status: 404,
        json: { error: { code: "preview_binding_absent" } },
      });
      return;
    }
    if (url.pathname.endsWith("/installation")) {
      await route.fulfill({ json: state });
      return;
    }
    if (!url.pathname.endsWith("/overview"))
      throw new Error("Unexpected route in synthetic onboarding test");
    await route.fulfill({
      json: {
        data: {
          requested_revenue: "250.00",
          fulfilled_revenue: "200.00",
          fulfillment_gap: "50.00",
          fulfillment_rate: "0.8",
          cancelled_requested_revenue: "0.00",
          orders_requested: 2,
          orders_cancelled: 0,
          buyers_observed: 2,
          recurring_buyers_observed: 0,
          purchase_frequency_observed: "1",
          new_customers_confirmed: null,
          ltv_complete: null,
          cac: null,
          revenue_paid: null,
          series: [
            {
              date: "2026-09-01",
              requested: "250.00",
              fulfilled: "200.00",
              orders: 2,
              new_customers_confirmed: null,
            },
          ],
        },
        pagination: null,
        metadata: {
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
        },
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(
    page.getByRole("region", { name: "Instalação de mx-fashion" }),
  ).toContainText("Dados parciais disponíveis");
  await expect(
    page.getByRole("region", { name: "Instalação de mx-fashion" }),
  ).toContainText("Analytics Facts");
  await page
    .getByRole("button", { name: "Editar integração de MX Fashion" })
    .click();
  await expect(page.getByRole("dialog")).toContainText("RAW pendente: Sim");
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Ver Dashboard de MX Fashion" })
    .click();
  await expect(page).toHaveURL(/\/b2b$/);
  await expect(
    page.getByText(
      "Histórico ainda está sendo processado. Os dados exibidos correspondem ao período atualmente certificado.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toContainText("250,00");
  const overview = calls.find((url) => url.pathname.endsWith("/overview"));
  expect(overview?.searchParams.get("from")).toBe("2026-09-01");
  expect(overview?.searchParams.get("to")).toBe("2026-09-27");
  const before = calls.filter((url) =>
    url.pathname.endsWith("/overview"),
  ).length;
  await page.getByRole("button", { name: /Filtrar período/ }).click();
  await page.getByLabel("Data de início", { exact: true }).fill("2026-08-01");
  await page.getByLabel("Data de fim", { exact: true }).fill("2026-08-31");
  await expect(page.getByRole("button", { name: /Aplicar/ })).toBeDisabled();
  await expect(
    page.getByText("Histórico deste período ainda está sendo processado."),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toContainText("250,00");
  expect(calls.filter((url) => url.pathname.endsWith("/overview")).length).toBe(
    before,
  );
  expect(errors).toEqual([]);
});

test("Admin cannot open real dashboard without certified coverage", async ({
  page,
}) => {
  await page.route("**/api/dashboard/**", async (route) => {
    const url = new URL(route.request().url());
    await route.fulfill(
      url.searchParams.get("workspace_operation_id") === "mx-fashion-b2b"
        ? { json: installationFixture("INSTALLING", false) }
        : { status: 404, json: { error: { code: "preview_binding_absent" } } },
    );
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Instalação de mx-fashion" }),
  ).toContainText("Instalando");
  await expect(
    page.getByRole("button", { name: "Ver Dashboard de MX Fashion" }),
  ).toBeDisabled();
});

test("client sees processing state instead of numbers when no window is certified", async ({
  page,
}) => {
  let overviewReads = 0;
  await page.route("**/api/dashboard/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/overview")) overviewReads++;
    if (!url.pathname.endsWith("/installation"))
      throw new Error("Uncertified view must not read Analytics");
    await route.fulfill({ json: installationFixture("INSTALLING", false) });
  });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name: /Maria/ }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("button", { name: "B2B", exact: true }).click();
  await expect(
    page.getByText("Histórico deste período ainda está sendo processado."),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toHaveCount(0);
  expect(overviewReads).toBe(0);
});
