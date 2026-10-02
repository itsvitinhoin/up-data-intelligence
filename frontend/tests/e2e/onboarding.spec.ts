import { expect, test } from "@playwright/test";
import { onboardingResult, syntheticCredential } from "../fixtures/onboarding";
test("Admin creates synthetic DRAFT brand; credential cleared; no dashboard queries", async ({
  page,
}) => {
  const dashboard: string[] = [];
  await page.route("**/api/dashboard/**", async (route) => {
    dashboard.push(new URL(route.request().url()).pathname);
    await route.fulfill({
      status: 404,
      json: { error: { code: "preview_binding_absent" } },
    });
  });
  await page.route("**/api/admin/onboarding", async (route) => {
    const req = route.request(),
      value = req.postDataJSON();
    expect(req.method()).toBe("POST");
    expect(req.url()).not.toContain(syntheticCredential);
    expect(value.sources.upzero.credential).toBe(syntheticCredential);
    expect(value.store.qualifying_order_statuses).toEqual([
      "RESERVED",
      "CONFIRMED",
      "PROCESSING",
      "INVOICED",
      "SHIPPED",
    ]);
    expect(value.store.slug).toBe("synthetic-brand");
    await expect(page.getByLabel("Chave/API Key UP Zero")).toHaveValue("");
    await route.fulfill({ status: 201, json: onboardingResult() });
  });
  await page.route("**/api/admin/onboarding/*", (route) =>
    route.fulfill({ json: onboardingResult() }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("button", { name: "Criar marca", exact: true }).click();
  await page
    .getByLabel("Nome da marca", { exact: true })
    .fill("Synthetic Brand");
  await page.getByLabel("Slug técnico").fill("synthetic-brand");
  await page.getByLabel("Início do histórico").fill("2026-01-01");
  await page.getByLabel("UP Zero", { exact: true }).check();
  await page.getByLabel("Chave/API Key UP Zero").fill(syntheticCredential);
  await page.getByRole("button", { name: "Criar marca com segurança" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Ver Dashboard de Synthetic Brand" }),
  ).toBeDisabled();
  await expect(page.getByText("Instalando", { exact: true })).toBeVisible();
  await expect(page.getByText("Pendente", { exact: true })).toBeVisible();
  expect(dashboard.every((path) => path.endsWith("/installation"))).toBe(true);
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
});
