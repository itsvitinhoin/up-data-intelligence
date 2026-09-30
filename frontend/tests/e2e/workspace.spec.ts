import { test, expect, type Page } from "@playwright/test";
async function login(page: Page, name = "Admin UP") {
  await page.goto("/");
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name, exact: false }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
}
async function client(page: Page) {
  await login(page, "Maria");
  await expect(
    page.getByRole("heading", { name: "Escolha sua operação." }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Lume Studio" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "B2B", exact: true }).click();
  await expect(page).toHaveURL("/b2b");
  await expect(
    page.getByRole("region", { name: "Indicadores de Receita" }),
  ).toContainText("Faturamento Solicitado");
}
async function nav(page: Page, path: string) {
  if (path.startsWith("/campaigns/")) {
    const group = page
      .locator("nav")
      .getByRole("button", { name: "Campanhas" });
    if ((await group.getAttribute("aria-expanded")) !== "true")
      await group.click();
  }
  await page.locator(`nav a[href="${path}"]`).first().click();
  await expect(page).toHaveURL(path);
  await expect(page.locator("main h1")).toBeVisible();
}
test("UP manages integrations and users for each brand", async ({ page }) => {
  await login(page);
  await expect(page).toHaveURL("/admin");
  await expect(
    page.getByRole("heading", { name: /Controle de marcas/ }),
  ).toBeVisible();
  await expect(page.locator('nav a[href="/admin"]').first()).toHaveText(
    "Marcas",
  );
  await expect(page.locator('nav a[href="/admin/integrations"]')).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("img", { name: "Sem conexão ativa de MX Fashion" }),
  ).toBeVisible();
  await expect(
    page.getByText("Data de criação não informada").first(),
  ).toBeVisible();
  await expect(
    page.getByText("Faturamento Solicitado", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", {
      name: "Editar integração de MX Fashion",
      exact: true,
    })
    .click();
  await page.getByRole("checkbox", { name: /Meta Ads/ }).check();
  await page
    .getByRole("button", { name: "Carregar contas demonstrativas" })
    .click();
  await page
    .getByRole("combobox", { name: "Conta de anúncio Meta", exact: true })
    .click();
  await page
    .getByRole("option", { name: "MX Fashion Ads Account · demo", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Gerenciar credencial · Meta Ads" })
    .click();
  await expect(page.getByLabel("Chave de API · Meta Ads")).toBeDisabled();
  await page
    .getByRole("button", { name: "Salvar configurações da marca" })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText("0 integrações ativas · 1 preparadas"),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Sem conexão ativa de MX Fashion" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Criar marca" }).click();
  await page.getByLabel("Nome da marca").fill("Nova marca sintética");
  await page.getByLabel("CNPJ", { exact: true }).fill("DEMO");
  await page.getByLabel("Segmento", { exact: true }).fill("Moda");
  await page.getByRole("button", { name: "Salvar marca" }).click();
  await expect(
    page.getByText("Nova marca sintética", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/^Criada em /).last()).toBeVisible();
  await nav(page, "/admin/users");
  await page.getByRole("button", { name: "Criar usuário" }).click();
  await page.getByLabel("Nome", { exact: true }).fill("Nova usuária demo");
  await page.getByLabel("Email fictício").fill("nova@sample.example");
  await expect(page.getByLabel("Senha", { exact: true })).toBeDisabled();
  await page.getByRole("combobox", { name: "Marca vinculada" }).click();
  await page.getByRole("option", { name: "Nova marca sintética" }).click();
  await page
    .getByRole("button", { name: "Salvar usuário", exact: true })
    .click();
  await expect(
    page.getByText("nova@sample.example", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sair", exact: true }).first().click();
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name: /Nova usuária demo/ }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Nova marca sintética" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "MX Fashion", exact: true }),
  ).toHaveCount(0);
});
test("unified admin cards open the selected brand dashboard", async ({
  page,
}) => {
  await login(page);
  const legacy = await page.request.get("/admin/integrations", {
    maxRedirects: 0,
  });
  expect(legacy.status()).toBe(307);
  expect(legacy.headers().location).toBe("/admin");
  const card = page
    .locator(".brand-integrations .card")
    .filter({ hasText: "MX Fashion" });
  await card.getByRole("combobox", { name: "Operação de MX Fashion" }).click();
  await page.getByRole("option", { name: "B2C", exact: true }).click();
  await card
    .getByRole("button", { name: "Ver Dashboard de MX Fashion" })
    .click();
  await expect(page).toHaveURL("/b2c");
  await expect(
    page.getByRole("combobox", { name: "Marca e operação" }),
  ).toContainText("MX Fashion · B2C");
  await nav(page, "/admin");
  await expect(
    page.getByRole("heading", { name: /Controle de marcas/ }),
  ).toBeVisible();
});
test("admin brand search filters cards by name, including accents", async ({
  page,
}) => {
  await login(page);
  const cards = page.locator(".brand-integrations .card");
  await expect(cards).toHaveCount(3);
  const search = page.getByRole("textbox", { name: "Pesquisar marca" });
  await search.fill("LúMe");
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText("Lume Studio");
  await expect(page.getByText("1 de 3 marcas")).toBeVisible();
  await search.fill("marca inexistente");
  await expect(cards).toHaveCount(0);
  await expect(page.getByText("Nenhuma marca encontrada")).toBeVisible();
  await search.clear();
  await expect(cards).toHaveCount(3);
});
test("client is restricted to linked brand, single operation enters directly", async ({
  page,
}) => {
  await client(page);
  await expect(page.locator('nav a[href^="/admin"]')).toHaveCount(0);
  await expect(page.locator('nav a[href="/settings"]')).toHaveCount(0);
  await expect(page.locator('nav a[href="/journey"]')).toHaveCount(0);
  await page.getByRole("combobox", { name: "Operação da marca" }).click();
  await expect(page.getByRole("option")).toHaveCount(2);
  await expect(page.getByRole("option", { name: /Lume|Orla/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.evaluate(() => window.history.pushState(null, "", "/admin"));
  await expect(
    page.getByRole("heading", { name: "Acesso restrito" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Voltar à sua marca" }).click();
  await page.getByRole("button", { name: "Encerrar sessão" }).click();
  await page.getByRole("combobox", { name: "Usuário demonstrativo" }).click();
  await page.getByRole("option", { name: /Gestor Lume/ }).click();
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL("/b2b");
  await expect(
    page.getByRole("heading", { name: "Escolha sua operação." }),
  ).toHaveCount(0);
  await expect(
    page.locator("nav").getByRole("button", { name: "B2C", exact: true }),
  ).toHaveCount(0);
});
test("customer timeline, campaigns and influenced orders are navigable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await client(page);
  await nav(page, "/b2b/customers");
  await page
    .getByRole("textbox", { name: "Filtrar clientes" })
    .fill("sem-resultado");
  await expect(page.getByText("Nenhum resultado neste recorte")).toBeVisible();
  await page.getByRole("textbox", { name: "Filtrar clientes" }).fill("");
  await page.getByRole("link", { name: /Ateliê Jardim/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Ateliê Jardim",
  );
  await expect(page.getByText("Carrinho criado")).toBeVisible();
  await expect(page.getByText("Checkout iniciado")).toBeVisible();
  await page.getByRole("tab", { name: "Pedidos", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Histórico de pedidos" }),
  ).toBeVisible();
  await nav(page, "/campaigns/meta");
  await page.locator('table a[href^="/campaigns/"]').first().click();
  await expect(
    page.getByRole("tab", { name: "Clientes influenciados" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Pedidos influenciados" }).click();
  await expect(
    page.getByRole("columnheader", { name: "Campanha", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("approved map and all B2B/B2C navigation work", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await client(page);
  for (const path of [
    "/b2b/acquisition",
    "/b2b/commercial",
    "/b2b/performance",
    "/b2b/products",
    "/b2b/retention",
  ])
    await nav(page, path);
  await expect(
    page.getByRole("region", { name: "Compra 5+", exact: true }),
  ).toBeVisible();
  await nav(page, "/b2b/geography");
  await page.getByRole("button", { name: /Minas Gerais:/ }).click();
  await expect(page.locator(".selected-state")).toContainText("Minas Gerais");
  await expect(
    page.getByText("Principais cidades", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Ticket médio solicitado", { exact: true }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Métrica do mapa" }).click();
  await expect(page.getByRole("option")).toHaveCount(6);
  await page
    .getByRole("option", { name: "Receita Atendida", exact: true })
    .click();
  await page.getByRole("combobox", { name: "Operação da marca" }).click();
  await page
    .getByRole("option", { name: "MX Fashion · B2C", exact: true })
    .click();
  for (const path of [
    "/b2c",
    "/b2c/orders",
    "/b2c/customers",
    "/b2c/retention",
    "/b2c/products",
    "/b2c/stock",
    "/b2c/performance",
  ])
    await nav(page, path);
  expect(errors).toEqual([]);
});
test("mobile client navigation and brand selector remain scoped", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await client(page);
  await page.getByRole("button", { name: "Abrir navegação" }).click();
  await expect(
    page.getByRole("dialog").locator('a.nav-item[href^="/b2b"]'),
  ).toHaveCount(8);
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "B2B", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("dialog").locator('a[href="/b2b/customers"]').click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Conheça cada",
  );
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.getByRole("button", { name: "Encerrar sessão" }).click();
  await expect(
    page.getByRole("button", { name: "Entrar", exact: true }),
  ).toBeVisible();
});

test("B2B Overview follows commercial hierarchy with embedded customer tickets", async ({
  page,
}) => {
  await client(page);
  const customers = page.getByRole("region", {
    name: "Indicadores de Clientes",
  });
  await expect(
    customers
      .locator(".metric")
      .filter({ has: page.getByText("Novos", { exact: true }) }),
  ).toContainText("Ticket Médio de Aquisição");
  await expect(
    customers
      .locator(".metric")
      .filter({ has: page.getByText("Recorrentes", { exact: true }) }),
  ).toContainText("Ticket Médio de Retenção");
  await expect(
    page.getByRole("heading", { name: "Novos × Recorrentes por período" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Pedidos atribuídos a campanhas" }),
  ).toHaveCount(0);
  const relationship = page.getByRole("region", {
    name: "Indicadores de Relacionamento",
  });
  await expect(relationship.locator(".metric")).toHaveCount(4);
  await expect(relationship).toContainText("Frequência");
  await expect(relationship).toContainText("LTV geral da marca");
  await expect(relationship).toContainText("Dias médios para primeira compra");
  await expect(relationship).toContainText(
    "Dias médios para compras recorrentes",
  );
  await expect(
    page.getByRole("heading", {
      name: "Faturamento × Investimento por período",
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Indicadores de Mídia" }),
  ).toHaveCount(0);
  await expect(
    page
      .getByRole("region", { name: "Indicadores de Leads" })
      .locator(".metric"),
  ).toHaveCount(4);
  const positions = await page
    .locator(".b2b-overview > *")
    .evaluateAll((elements) => elements.map((e) => e.textContent));
  expect(positions[0]).toContain("Faturamento Solicitado");
  expect(positions[1]).toContain("Qualificação de leads");
  expect(positions[2]).toContain("Eficiência de Atendimento");
  expect(positions[3]).toContain("Pedidos Atendidos");
  expect(positions[4]).toContain("Ticket Médio de Aquisição");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("Campaigns displays marketing rankings, preview and searchable campaigns", async ({
  page,
}) => {
  await client(page);
  await nav(page, "/campaigns/meta");
  await expect(
    page.getByRole("region", { name: "Indicadores de Marketing" }),
  ).toContainText("Faturamento atribuído");
  await expect(
    page.getByRole("heading", {
      name: "Menor CPA · custo por compra",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Ver criativo.*Maior CTR/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("Prévia ilustrativa");
  await expect(page.getByRole("dialog").getByRole("img")).toBeVisible();
  await page.keyboard.press("Escape");
  await page
    .getByRole("textbox", { name: "Buscar campanha" })
    .fill("nenhuma-campanha");
  await expect(page.getByText("Nenhum resultado neste recorte")).toBeVisible();
  await page.getByRole("textbox", { name: "Buscar campanha" }).fill("");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
});

test("global period, variant stock, lifecycle and order dialogs", async ({
  page,
}) => {
  await client(page);
  await expect(
    page.locator(".topbar").getByRole("button", { name: /Filtrar período:/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Filtrar período:/ }).click();
  await page
    .getByRole("button", { name: "Personalizado", exact: true })
    .click();
  await page.getByLabel("Data de início", { exact: true }).fill("2026-09-25");
  await page.getByLabel("Data de fim", { exact: true }).fill("2026-09-27");
  await page.getByRole("button", { name: "Aplicar período" }).click();
  await expect(
    page.getByRole("button", { name: /Filtrar período:/ }),
  ).toContainText("25/09/2026 – 27/09/2026");
  await nav(page, "/b2b/performance");
  await page
    .getByRole("button", { name: /Ver pedido / })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("CNPJ");
  await expect(page.getByRole("dialog")).toContainText("E-mail");
  await expect(page.getByRole("dialog")).toContainText("Telefone");
  await expect
    .poll(() =>
      page.getByRole("dialog").evaluate((element) => {
        const box = element.getBoundingClientRect();
        return box.top >= 0 && box.bottom <= window.innerHeight;
      }),
    )
    .toBe(true);
  await expect(
    page.getByRole("region", { name: "Produtos do pedido" }),
  ).toContainText("Tamanho");
  await page.keyboard.press("Escape");
  await nav(page, "/b2b/products");
  await page.locator("button.prod").first().click();
  await expect(page.getByRole("dialog")).toContainText("Cor / tamanho");
  await expect(page.getByRole("dialog")).toContainText("Sem estoque");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Filtrar período:/ }).click();
  await page.getByRole("button", { name: "Este mês", exact: true }).click();
  await page.getByRole("button", { name: "Aplicar período" }).click();
  await nav(page, "/b2b/retention");
  await expect(
    page.getByRole("region", { name: "Compra 5+", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Mês 0", exact: true }),
  ).toBeVisible();
  await nav(page, "/b2b/acquisition");
  await expect(
    page.getByRole("region", { name: "Velocidade de conversão" }),
  ).toContainText("Mediana até o pedido");
  await page
    .getByRole("button", { name: /Ver pedido / })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("Produtos do pedido");
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.getByRole("button", { name: /Filtrar período:/ }).click();
  await expect(
    page.getByRole("button", { name: "Esta semana", exact: true }),
  ).toBeVisible();
});

test("B2B separates brand acquisition from paid performance and removes redundant operation controls", async ({
  page,
}) => {
  await client(page);
  await expect(
    page.getByRole("group", { name: "Operação", exact: true }),
  ).toHaveCount(0);
  const menu = page.locator('.sidebar nav a.nav-item[href^="/b2b"]');
  await expect(menu).toHaveText([
    "Overview",
    "Pedidos",
    "Aquisição",
    "Retenção",
    "Clientes",
    "Produtos",
    "Geografia",
    "Performance",
  ]);
  await nav(page, "/b2b/acquisition");
  await expect(
    page.getByRole("heading", {
      name: "Clientes com primeira compra observada",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Clientes influenciados", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Canal", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: /Essência Boutique/ }),
  ).toBeVisible();
  await nav(page, "/b2b/performance");
  await expect(
    page.getByRole("heading", { name: "Clientes influenciados", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Pedidos influenciados", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metrics .metric")).toHaveCount(8);
  await expect(
    page.locator(".metrics + .card").getByRole("heading"),
  ).toHaveText("Faturamento × Investimento por período");
  const trend = page.getByRole("img", {
    name: "Investimento e receita influenciada",
  });
  await expect(trend.locator(".recharts-line-curve")).toHaveCount(2);
  await expect(trend.locator(".recharts-bar")).toHaveCount(0);
  await expect(
    page.locator(".metric").filter({ hasText: "Investimento em mídias" }),
  ).toHaveCount(1);
  await expect(
    page.locator(".metric").filter({
      has: page.locator(".metric-label").getByText("ROI", { exact: true }),
    }),
  ).toContainText("Não confirmado");
  await page
    .getByRole("button", { name: /Ver pedido / })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("Produtos do pedido");
  await page.keyboard.press("Escape");
  await nav(page, "/b2b/commercial");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Pedidos no período",
  );
});

test("flat B2B navigation and shared lead cohort cards respond to the period", async ({
  page,
}) => {
  await client(page);
  const menu = page.locator(".sidebar nav");
  await expect(
    menu.getByRole("button", { name: "B2B", exact: true }),
  ).toHaveCount(0);
  await expect(menu.locator('a.nav-item[href^="/b2b"] svg')).toHaveCount(8);
  await expect(menu.locator('a[href="/b2b"]')).toHaveAttribute(
    "aria-current",
    "page",
  );
  const leads = page.getByRole("region", { name: "Indicadores de Leads" });
  await expect(leads.locator(".metric")).toHaveCount(4);
  const overviewCards = await leads.innerText();
  await nav(page, "/b2b/acquisition");
  await expect(menu.locator('a[href="/b2b/acquisition"]')).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(leads).toHaveText(overviewCards, { useInnerText: true });
  await page.getByRole("button", { name: /Filtrar período:/ }).click();
  await page
    .getByRole("button", { name: "Personalizado", exact: true })
    .click();
  await page.getByLabel("Data de início", { exact: true }).fill("2026-09-28");
  await page.getByLabel("Data de fim", { exact: true }).fill("2026-09-28");
  await page.getByRole("button", { name: "Aplicar período" }).click();
  await expect(
    leads.locator(".metric").first().locator(".metric-value"),
  ).toHaveText("1");
  await expect(
    leads.locator(".metric").nth(1).locator(".metric-value"),
  ).toHaveText("0");
  await expect(
    leads.locator(".metric").nth(2).locator(".metric-value"),
  ).toHaveText("0%");
  await expect(leads.locator(".metric").nth(3)).toContainText("Não confirmado");
  const filteredCards = await leads.innerText();
  await nav(page, "/b2b");
  await expect(leads).toHaveText(filteredCards, { useInnerText: true });
});

test("retention headline and state registrations are visible without duplicate customer menu", async ({
  page,
}) => {
  await client(page);
  await expect(page.locator('nav a[href="/customers"]')).toHaveCount(0);
  await nav(page, "/b2b/retention");
  const metrics = page.getByRole("region", { name: "Indicadores de Retenção" });
  await expect(metrics.locator(".metric")).toHaveCount(4);
  await expect(metrics).toContainText("Ticket Médio de Retenção");
  await expect(
    page
      .getByRole("img", { name: "Percentual de retenção por período" })
      .locator(".recharts-line-curve"),
  ).toHaveCount(1);
  await nav(page, "/b2b/geography");
  await page.getByRole("button", { name: /Minas Gerais:/ }).click();
  await expect(page.getByLabel("Resumo do estado")).toContainText(
    "Cadastros Aprovados (Sem Compra)",
  );
  await expect(page.getByLabel("Resumo do estado")).toContainText(
    "% de Conversão",
  );
});

test("ERP has six scoped views, filters, expandable items, history and real exports", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await client(page);
  await page
    .locator(".sidebar nav")
    .getByRole("button", { name: "ERP", exact: true })
    .click();
  await nav(page, "/erp");
  await expect(
    page.getByRole("region", { name: "Indicadores ERP" }).locator(".metric"),
  ).toHaveCount(8);
  await expect(
    page.getByRole("img", { name: "Faturamento e pedidos ERP" }),
  ).toBeVisible();
  await nav(page, "/erp/pedidos");
  await page
    .getByRole("button", { name: /Itens do pedido ERP-/ })
    .first()
    .click();
  await expect(page.getByRole("region", { name: /Itens ERP-/ })).toContainText(
    "Custo",
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar XLSX" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/pedidos-erp.*\.xlsx$/);
  const stream = await download.createReadStream();
  const parts: Buffer[] = [];
  for await (const chunk of stream!) parts.push(Buffer.from(chunk));
  expect(Buffer.concat(parts).subarray(0, 2).toString()).toBe("PK");
  await page
    .getByRole("textbox", { name: "Buscar pedido ERP" })
    .fill("inexistente");
  await expect(page.getByText("Nenhum resultado neste recorte")).toBeVisible();
  await page.getByRole("textbox", { name: "Buscar pedido ERP" }).fill("");
  await page.getByRole("combobox", { name: "Status ERP" }).click();
  await page.getByRole("option", { name: "CANCELADO", exact: true }).click();
  await expect(page.locator(".list .screen-table-body > tr")).toHaveCount(1);
  await nav(page, "/erp/clientes");
  await page.locator(".list tbody button").first().click();
  await expect(page.getByRole("dialog")).toContainText("Histórico de pedidos");
  await expect(page.getByRole("dialog")).toContainText(
    "LTV definitivo não confirmado",
  );
  await page.keyboard.press("Escape");
  await nav(page, "/erp/produtos");
  await page
    .getByRole("button", { name: /Variantes de / })
    .first()
    .click();
  await expect(page.getByRole("region", { name: /Grade / })).toContainText(
    "Tamanho",
  );
  await expect(page.getByRole("region", { name: /Grade / })).toContainText(
    "Cor",
  );
  await nav(page, "/erp/estoque");
  await page.getByRole("combobox", { name: "Estoque ERP" }).click();
  await page
    .getByRole("option", { name: "Estoque negativo", exact: true })
    .click();
  await expect(page.getByRole("button", { name: /Variantes de / })).toHaveCount(
    1,
  );
  await nav(page, "/erp/vendedores");
  await expect(
    page.getByRole("heading", { name: "Produtividade comercial" }),
  ).toBeVisible();
  const csvPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar CSV" }).click();
  expect((await csvPromise).suggestedFilename()).toMatch(
    /vendedores-erp.*\.csv$/,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page
    .getByRole("navigation", { name: "Áreas do ERP" })
    .getByRole("link", { name: "Produtos", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Desempenho do catálogo" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  expect(errors).toEqual([]);
});

test("metric explanations use accessible tooltips and page PDF is portrait", async ({
  page,
}) => {
  await client(page);
  const info = page
    .getByRole("button", { name: "Sobre Taxa de conversão", exact: false })
    .first();
  const card = page.locator(".metric").filter({ has: info });
  await expect(card.locator(".metric-foot")).toHaveCount(0);
  await info.hover();
  await expect(page.getByRole("tooltip")).toContainText(
    "Cada lead conta uma vez",
  );
  await page.keyboard.press("Escape");
  await info.focus();
  await expect(page.getByRole("tooltip")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.evaluate(() => {
    window.print = () => {
      document.body.dataset.printCalled = "true";
    };
  });
  await page.getByRole("button", { name: "Exportar PDF", exact: true }).click();
  await expect(page.locator("body")).toHaveAttribute(
    "data-print-called",
    "true",
  );
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".sidebar")).toBeHidden();
  const pdf = await page.pdf({
    preferCSSPageSize: true,
    printBackground: true,
  });
  expect(pdf.toString("latin1")).toMatch(
    /\/MediaBox\s*\[0 0 594\.?\d* 841\.?\d*\]/,
  );
});

test("lists export current page or every filtered row and print the full table", async ({
  page,
}) => {
  await client(page);
  await nav(page, "/b2b/customers");
  const current = await page.locator(".screen-table-body tr").count();
  const total = await page.locator(".print-table-body tr").count();
  expect(total).toBeGreaterThan(current);
  async function csv(all: boolean) {
    await page
      .getByRole("button", { name: "Exportar lista: lista", exact: true })
      .click();
    const download = page.waitForEvent("download");
    await page
      .getByRole("menuitem", {
        name: all ? /^Todos .*CSV$/ : /^Página atual .*CSV$/,
      })
      .click();
    const file = await download;
    const stream = await file.createReadStream();
    const chunks = [];
    for await (const chunk of stream!) chunks.push(chunk);
    return Buffer.concat(chunks).toString("utf8");
  }
  expect((await csv(false)).split("\r\n")).toHaveLength(current + 1);
  const full = await csv(true);
  expect(full.split("\r\n")).toHaveLength(total + 1);
  await page.getByRole("button", { name: "Próxima página" }).click();
  expect(await csv(false)).not.toEqual(full);
  await page
    .getByRole("textbox", { name: "Filtrar clientes" })
    .fill("Ateliê Jardim");
  await expect(page.locator(".pagination")).toContainText("1 registros");
  expect((await csv(true)).split("\r\n")).toHaveLength(2);
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".screen-table-body")).toBeHidden();
  await expect(page.locator(".print-table-body")).toBeVisible();
});

test("brand registration uploads a logo, persists platform and ERP in demo session", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("button", { name: "Criar marca" }).click();
  await expect(page.getByLabel("URL do logo")).toHaveCount(0);
  await page.getByLabel("Nome da marca").fill("Marca upload demo");
  await page.getByLabel("CNPJ", { exact: true }).fill("DEMO");
  await page.getByLabel("Segmento", { exact: true }).fill("Moda");
  await page.getByLabel("Logo da marca").setInputFiles({
    name: "invalid.svg",
    mimeType: "image/svg+xml",
    buffer: Buffer.from("<svg/>"),
  });
  await expect(page.getByRole("alert")).toContainText("até 2 MB");
  const image = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 32;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#0458fe";
    ctx.fillRect(0, 0, 32, 32);
    return c.toDataURL("image/png").split(",")[1];
  });
  await page.getByLabel("Logo da marca").setInputFiles({
    name: "logo.png",
    mimeType: "image/png",
    buffer: Buffer.from(image, "base64"),
  });
  await expect(page.getByAltText("Prévia da logo")).toBeVisible();
  await page.getByRole("combobox", { name: "Plataforma", exact: true }).click();
  await page.getByRole("option", { name: "Shopify", exact: true }).click();
  await page.getByRole("combobox", { name: "ERP", exact: true }).click();
  await page.getByRole("option", { name: "Bling", exact: true }).click();
  await page.getByRole("button", { name: "Salvar marca" }).click();
  await expect(page.getByAltText("Logo de Marca upload demo")).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Plataforma de Marca upload demo" }),
  ).toHaveText("Shopify");
  await expect(
    page.getByRole("combobox", { name: "ERP de Marca upload demo" }),
  ).toHaveText("Bling");
  await page
    .getByRole("combobox", { name: "ERP de Marca upload demo" })
    .click();
  await page.getByRole("option", { name: "Miré", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "ERP de Marca upload demo" }),
  ).toHaveText("Miré");
});

test("B2C has flat navigation, eight overview cards, unified performance and variant sales", async ({
  page,
}) => {
  await client(page);
  await page.getByRole("combobox", { name: "Operação da marca" }).click();
  await page
    .getByRole("option", { name: "MX Fashion · B2C", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Indicadores B2C" }).locator(".metric"),
  ).toHaveCount(8);
  await expect(
    page.getByRole("img", { name: "Porcentagem de vendas pagas" }),
  ).toContainText("Pagamento não confirmado");
  await expect(
    page
      .locator(".sidebar nav")
      .getByRole("button", { name: "B2C", exact: true }),
  ).toHaveCount(0);
  for (const old of ["grade", "acquisition", "media", "funnel"])
    await expect(page.locator(`nav a[href="/b2c/${old}"]`)).toHaveCount(0);
  await nav(page, "/b2c/performance");
  await expect(
    page
      .getByRole("region", { name: "Indicadores de Performance B2C" })
      .locator(".metric"),
  ).toHaveCount(9);
  await expect(
    page.getByRole("heading", { name: "Funil de conversão", exact: true }),
  ).toBeVisible();
  await nav(page, "/b2c/customers");
  await expect(
    page.getByRole("combobox", { name: "Influência de mídia" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("columnheader", { name: "Mídia", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: /Ateliê Jardim/ }).click();
  await expect(
    page.getByRole("tab", { name: "Mídia e campanhas" }),
  ).toHaveCount(0);
  await nav(page, "/b2c/products");
  await page.locator(".screen-table-body .prod").first().click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Vendas por cor" }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "Vendas por tamanho" }),
  ).toBeVisible();
  await expect(dialog.getByText("Atendido", { exact: true })).toHaveCount(0);
  await expect(
    dialog.getByText("Faturamento captado", { exact: true }),
  ).toBeVisible();
  await expect(dialog.locator(".recharts-bar-rectangle").first()).toBeVisible();
});

test("B2C orders separate period and history, with retail-only order details", async ({
  page,
}) => {
  await client(page);
  await page.getByRole("combobox", { name: "Operação da marca" }).click();
  await page
    .getByRole("option", { name: "MX Fashion · B2C", exact: true })
    .click();
  await nav(page, "/b2c/orders");
  await expect(page.locator('nav a[href="/b2c/revenue"]')).toHaveCount(0);
  await expect(
    page
      .getByRole("region", { name: "Indicadores de pedidos B2C" })
      .locator(".metric"),
  ).toHaveCount(4);
  await expect(
    page.getByRole("img", {
      name: "Quantidade de pedidos e faturamento por período",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Filtrar período/ }).click();
  await page.getByRole("button", { name: "Últimos 7 dias" }).click();
  await page.getByRole("button", { name: /Aplicar período/ }).click();
  const range = page
    .getByRole("heading", { name: "Pedidos no recorte" })
    .locator("../../..");
  const all = page
    .getByRole("heading", { name: "Todos os pedidos" })
    .locator("../../..");
  await expect
    .poll(async () => all.locator(".print-table-body tr").count())
    .toBeGreaterThan(await range.locator(".print-table-body tr").count());
  await all.getByRole("button", { name: "Ver pedido 2102" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("columnheader")).toContainText([
    "Produto",
    "Cor",
    "Tamanho",
    "Peças compradas",
    "Valor",
  ]);
  await expect(dialog.getByText("CNPJ", { exact: true })).toHaveCount(0);
  await expect(dialog.getByText("Qtd. solicitada")).toHaveCount(0);
  await expect(dialog.getByText("Qtd. atendida")).toHaveCount(0);
  await expect(dialog.getByText("Valor do pedido")).toBeVisible();
});

test("B2C customer detail has only retail metrics and no journey", async ({
  page,
}) => {
  await client(page);
  await page.getByRole("combobox", { name: "Operação da marca" }).click();
  await page
    .getByRole("option", { name: "MX Fashion · B2C", exact: true })
    .click();
  await nav(page, "/b2c/customers");
  await page.getByRole("link", { name: /Ateliê Jardim/ }).click();
  const metrics = page.getByRole("region", {
    name: "Indicadores do cliente B2C",
  });
  await expect(metrics.locator(".metric")).toHaveCount(4);
  for (const label of ["Pedidos", "Receita", "Frequência de Compra", "LTV"])
    await expect(metrics.getByText(label, { exact: true })).toBeVisible();
  for (const label of [
    "Jornada",
    "Receita solicitada",
    "Receita atendida",
    "Peças Solicitadas",
    "Peças Atendidas",
    "Empresa",
  ])
    await expect(page.getByText(label, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("tab")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Histórico de pedidos" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ver pedido 2100" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Peças compradas");
});

test("B2C stock ignores dates and filters active products; campaign submenus preserve coverage", async ({
  page,
}) => {
  await client(page);
  await page.getByRole("combobox", { name: "Operação da marca" }).click();
  await page
    .getByRole("option", { name: "MX Fashion · B2C", exact: true })
    .click();
  await nav(page, "/b2c/products");
  await expect(
    page
      .getByRole("region", { name: "Indicadores de análise de produtos B2C" })
      .locator(".metric"),
  ).toHaveCount(4);
  for (const title of [
    "Vendas por categoria",
    "Vendas por tamanho",
    "Vendas por cor",
  ])
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await page.getByRole("combobox", { name: "Curva ABC" }).click();
  await page.getByRole("option", { name: "Promissores" }).click();
  const ranking = page
    .getByRole("heading", { name: "Ranking de produtos" })
    .locator("../../..");
  await expect(
    ranking.locator(".screen-table-body .curve-dot--promising"),
  ).toHaveCount(1);
  await expect(ranking.locator(".screen-table-body .grade-tag")).toHaveCount(1);
  await nav(page, "/b2c/stock");
  await expect(
    page.getByRole("button", { name: /Filtrar período/ }),
  ).toHaveCount(0);
  await expect(
    page
      .getByRole("region", { name: "Indicadores de estoque B2C" })
      .locator(".metric"),
  ).toHaveCount(4);
  const table = page
    .getByRole("heading", { name: "Estoque e grade" })
    .locator("../../..");
  await table.getByRole("combobox", { name: "Situação do produto" }).click();
  await page.getByRole("option", { name: "Inativos" }).click();
  await expect(table.locator(".screen-table-body tr")).toHaveCount(1);
  await table.getByRole("combobox", { name: "Situação do produto" }).click();
  await page.getByRole("option", { name: "Todos", exact: true }).click();
  await expect(
    table.locator(".screen-table-body .color-dot").first(),
  ).toHaveAttribute("title", /#/);
  await nav(page, "/campaigns/meta");
  await expect(
    page
      .getByRole("region", { name: "Indicadores de Marketing" })
      .locator(".metric"),
  ).toHaveCount(8);
  await expect(
    page.getByRole("heading", { name: "Menor CPA · custo por compra" }),
  ).toBeVisible();
  await nav(page, "/campaigns/google");
  await expect(
    page
      .getByRole("region", { name: "Indicadores de Google Ads" })
      .locator(".metric"),
  ).toHaveCount(8);
  await expect(page.getByText("Sem campanhas de Google Ads")).toBeVisible();
  for (const path of ["/campaigns/pinterest", "/campaigns/tiktok"])
    await nav(page, path);
});
