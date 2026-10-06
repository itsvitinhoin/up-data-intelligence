import { test, expect } from "@playwright/test";
import { managerPage } from "../../src/dashboard/registry";
import { mkdir } from "node:fs/promises";
test("B2C V2, retained V1 and session personalization", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name: /Maria/ }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("button", { name: "B2C", exact: true }).click();
  await expect(page).toHaveURL("/b2c");
  await mkdir("/tmp/data19c/visuals", { recursive: true });
  for (const [path, name] of [
    ["/b2c", "overview"],
    ["/b2c/customers/overview", "clients-overview"],
    ["/b2c/customers", "clients"],
    ["/b2c/products", "products"],
    ["/b2c/stock", "stock"],
    ["/b2c/performance", "performance"],
    ["/b2c/performance/history", "history"],
  ]) {
    if (path !== "/b2c")
      await page.locator(`nav a[href="${path}"]`).first().click();
    await expect(page).toHaveURL(path);
    await expect(page.locator("main .page-head h1").first()).toHaveText(
      managerPage(path)!.title,
    );
    await expect(page.locator(".page-loader")).toHaveCount(0);
    await expect(
      page.getByRole("status", { name: "Carregando dados", exact: true }),
    ).toHaveCount(0);
    if (await page.locator(".metrics > div:has(.metric)").count())
      await expect(
        page.locator(".metrics > div:has(.metric)").last(),
      ).toHaveCSS("opacity", "1");
    await page.screenshot({
      path: `/tmp/data19c/visuals/b2c-${name}.png`,
      fullPage: true,
    });
  }
  await expect(
    page.getByRole("columnheader", { name: "Jan", exact: true }).first(),
  ).toBeVisible();
  await page.locator('nav a[href="/b2c/performance"]').first().click();
  await page.getByRole("combobox", { name: "Plataforma" }).click();
  await page.getByRole("option", { name: "Google", exact: true }).click();
  await expect(
    page.getByText("Investimento Google", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("b2c-demo-banner")).toContainText(
    "B2C · DADOS DEMONSTRATIVOS",
  );
});
