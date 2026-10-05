import { test, expect, type Page } from "@playwright/test";
import { claims, mockedAuth } from "../fixtures/product-auth";
import { restorationResources } from "../fixtures/restoration-routes";
import { envelope, overview } from "../fixtures/restoration";
async function signIn(page: Page) {
  await mockedAuth(page);
  await restorationResources(page);
  await page.goto("/");
  await page.getByLabel("E-mail", { exact: true }).fill(claims.email);
  await page
    .getByLabel("Senha", { exact: true })
    .fill("OfflineSyntheticPassword!2026");
  await page
    .getByRole("button", { name: "Entrar", exact: true })
    .first()
    .click();
  await expect(page.locator(".workspace-strip .badge")).toHaveText(
    /Dados reais/,
  );
}
test("main loader plays intact video inline and leaves navigation available", async ({
  page,
}) => {
  await signIn(page);
  let release!: () => void;
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/dashboard/overview?**", async (route) => {
    await hold;
    await route.fulfill({ json: envelope(overview) });
  });
  await page.goto("/b2b", { waitUntil: "domcontentloaded" });
  const video = page.locator(".page-loader video");
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute("src", "/media/up-loader.mp4");
  expect(
    await video.evaluate((el: HTMLVideoElement) => ({
      rate: el.playbackRate,
      muted: el.muted,
      inline: el.playsInline,
      loop: el.loop,
    })),
  ).toEqual({ rate: 1.5, muted: true, inline: true, loop: true });
  await expect(
    page.getByRole("button", { name: /Buscar cliente/ }),
  ).toBeEnabled();
  release();
  await expect(video).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toContainText("50,01");
});
test("reduced motion never mounts video and a request failure ends loading", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signIn(page);
  await page.route("**/api/dashboard/overview?**", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: "read_unavailable" } },
    }),
  );
  await page.goto("/b2b");
  await expect(page.locator(".page-loader video")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Tentar novamente/ }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Buscar cliente/ }),
  ).toBeEnabled();
});
