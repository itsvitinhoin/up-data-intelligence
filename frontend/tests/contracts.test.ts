import { describe, it, expect, vi, afterEach } from "vitest";
import { demoApi } from "@/services/demo/adapter";
import { adminApi, authorizedTenants, sessionFor } from "@/services/demo/admin";
import { createHttpApi } from "@/services/api/http";
import { defaultFilters } from "@/config/tenants";
import { queryKey } from "@/hooks/use-resource";
import type { RequestContext } from "@/types/domain";
function context(user = "up-admin"): RequestContext {
  return {
    scope: {
      tenant_id: "demo-up",
      store_id: "mx-fashion-b2b",
      operation: "B2B",
    },
    session: sessionFor(user),
    filters: { ...defaultFilters },
  };
}
afterEach(() => vi.unstubAllGlobals());
describe("UP / brand access model", () => {
  it("UP sees all brands; Maria sees only MX Fashion and its two operations", () => {
    expect(
      authorizedTenants(sessionFor("up-admin")).flatMap((t) => t.brands).length,
    ).toBe(3);
    const brands = authorizedTenants(sessionFor("maria-demo")).flatMap(
      (t) => t.brands,
    );
    expect(brands.map((b) => b.name)).toEqual(["MX Fashion"]);
    expect(brands[0].operations.map((o) => o.type)).toEqual(["B2B", "B2C"]);
    expect(
      authorizedTenants(sessionFor("lume-demo"))[0].brands[0].operations,
    ).toHaveLength(1);
  });
  it("rejects another brand even inside the same tenant", async () => {
    const c = context("maria-demo");
    c.scope.store_id = "lume-b2b";
    await expect(demoApi.read("customers", c)).rejects.toMatchObject({
      status: 403,
    });
    c.session.store_ids.push("lume-b2b");
    await expect(demoApi.read("customers", c)).rejects.toMatchObject({
      status: 403,
    });
  });
  it("denies all internal administration to customer identities", async () => {
    const s = sessionFor("maria-demo");
    await expect(adminApi.brands(s)).rejects.toMatchObject({ status: 403 });
    await expect(adminApi.users(s)).rejects.toMatchObject({ status: 403 });
    await expect(adminApi.meta(s)).rejects.toMatchObject({ status: 403 });
    await expect(
      adminApi.saveUser(
        {
          id: "x",
          name: "X",
          email: "x@example.test",
          role: "ADMIN",
          brand_id: "demo-mx",
        },
        s,
      ),
    ).rejects.toMatchObject({ status: 403 });
  });
  it("rejects mismatched tenant/store pairs", async () => {
    const c = context();
    c.scope.tenant_id = "demo-horizonte";
    await expect(demoApi.read("customers", c)).rejects.toMatchObject({
      status: 403,
    });
  });
  it("creates a brand, binds user and gives it no existing brand data", async () => {
    const admin = sessionFor("up-admin");
    await adminApi.saveBrand(
      {
        id: "brand-test",
        name: "Marca sintética nova",
        cnpj: "DEMO",
        logo: "",
        segment: "Moda",
        operation: "B2B",
      },
      admin,
    );
    await adminApi.saveUser(
      {
        id: "new-user",
        name: "Pessoa sintética",
        email: "person@new.example",
        phone: "",
        role: "VIEWER",
        brand_id: "brand-test",
      },
      admin,
    );
    const s = sessionFor("new-user");
    const allowed = authorizedTenants(s);
    expect(allowed).toHaveLength(1);
    expect(allowed[0].brands[0].name).toBe("Marca sintética nova");
    const c = {
      ...context(),
      session: s,
      scope: {
        tenant_id: allowed[0].id,
        store_id: allowed[0].brands[0].operations[0].id,
        operation: "B2B" as const,
      },
    };
    expect(await demoApi.read("customers", c)).toEqual([]);
    expect(await demoApi.read("orders", c)).toEqual([]);
    expect(await demoApi.read("campaigns", c)).toEqual([]);
  });
  it("global Meta inventory requires UP and prevents a shared account binding", async () => {
    const s = sessionFor("up-admin");
    await adminApi.configureMetaDemo(s);
    const data = await adminApi.meta(s);
    expect(data.accounts).toHaveLength(2);
    expect(JSON.stringify(data)).not.toMatch(/access_token|secret_data/);
    const brands = await adminApi.brands(s);
    await adminApi.saveBrand(
      { ...brands[0], meta_account_id: data.accounts[0].meta_account_id },
      s,
    );
    await expect(
      adminApi.saveBrand(
        { ...brands[1], meta_account_id: data.accounts[0].meta_account_id },
        s,
      ),
    ).rejects.toMatchObject({ status: 400 });
  });
});
describe("customer, campaign and metric contracts", () => {
  it("keeps B2B timeline scoped and omits unsupported B2C journey", async () => {
    const c = context("maria-demo");
    const a = await demoApi.customer("c1", c),
      b = await demoApi.customer("c2", c);
    expect(
      a.timeline.every(
        (e) => e.customer_id === "c1" && e.store_id === c.scope.store_id,
      ),
    ).toBe(true);
    expect(new Set([...a.timeline, ...b.timeline].map((e) => e.id)).size).toBe(
      a.timeline.length + b.timeline.length,
    );
    expect(a.timeline.map((e) => e.type)).toContain("cart_created");
    expect(a.timeline.map((e) => e.type)).toContain("checkout_started");
    c.scope = {
      tenant_id: "demo-up",
      store_id: "mx-fashion-b2c",
      operation: "B2C",
    };
    const retail = await demoApi.customer("c1", c);
    expect(retail.timeline).toEqual([]);
  });
  it("non-influenced customers have no paid touch or campaigns", async () => {
    const c = context();
    const customer = (await demoApi.read("customers", c)).find((r) => !r.paid)!;
    const detail = await demoApi.customer(customer.id, c);
    expect(detail.timeline.some((e) => e.type === "paid_touch")).toBe(false);
    expect(detail.campaigns).toEqual([]);
  });
  it("deduplicates revenue and orders across overlapping campaigns", async () => {
    const c = context();
    const influence = await demoApi.read("influence", c);
    const details = await Promise.all(
      influence.campaigns.map((p) => demoApi.campaign(p.id, c)),
    );
    expect(details.reduce((s, d) => s + d.orders.length, 0)).toBeGreaterThan(
      influence.orders.length,
    );
    expect(new Set(influence.orders.map((o) => o.id)).size).toBe(
      influence.orders.length,
    );
    const unique = new Map(
      details.flatMap((d) => d.orders).map((o) => [o.id, o]),
    );
    const cents = [...unique.values()].reduce(
      (s, o) => s + BigInt(o.requested.replace(".", "")),
      0n,
    );
    expect(BigInt(influence.requested.replace(".", ""))).toBe(cents);
    for (const d of details) {
      expect(
        d.customers.every((r) => d.orders.some((o) => o.customer_id === r.id)),
      ).toBe(true);
      expect(d.campaign.orders).toBe(d.orders.length);
    }
  });
  it("provides all 25 B2B KPIs and all 13 B2C KPIs, preserving unknowns", async () => {
    const c = context();
    const b = await demoApi.read("overview", c);
    expect(b.metrics).toHaveLength(25);
    expect(
      b.metrics.find((m) => m.label === "Pedidos Pagos")?.value,
    ).toBeNull();
    expect(
      b.metrics.find((m) => m.label === "Clientes Novos")?.value,
    ).toBeNull();
    expect(
      b.metrics.find((m) => m.label === "CAC Novo Cliente")?.value,
    ).toBeNull();
    c.scope = { ...c.scope, store_id: "mx-fashion-b2c", operation: "B2C" };
    const retail = await demoApi.read("overview", c);
    expect(retail.metrics).toHaveLength(13);
    expect(
      retail.metrics.find((m) => m.label === "Faturamento Aprovado")?.value,
    ).toBeNull();
    expect(
      retail.metrics.find((m) => m.label === "Receita Aberta")?.value,
    ).toBeNull();
  });
  it("exposes four repurchase transitions and conditional rates", async () => {
    const rows = await demoApi.read("retention", context());
    expect(rows.map((r) => r.sequence)).toEqual([
      "Compra 1 → Compra 2",
      "Compra 2 → Compra 3",
      "Compra 3 → Compra 4",
      "Compra 4 → Compra 5+",
    ]);
    expect(
      rows.every(
        (r) =>
          r.mean !== null && r.median !== null && r.rate >= 0 && r.rate <= 100,
      ),
    ).toBe(true);
  });
  it("geography totals reconcile to city details and do not invent new customers", async () => {
    const rows = await demoApi.read("geography", context());
    for (const r of rows) {
      expect(r.newCustomers).toBeNull();
      expect(r.cities.reduce((s, c) => s + c.orders, 0)).toBe(r.orders);
      expect(r.cities.reduce((s, c) => s + c.requested, 0)).toBeCloseTo(
        r.requested,
      );
      expect(r.averageTicket).toBeCloseTo(r.requested / r.orders);
    }
  });
  it("cache separates users, brands, operations and filters", () => {
    const c = context();
    expect(queryKey("customers", c)).not.toEqual(
      queryKey("customers", { ...c, session: sessionFor("maria-demo") }),
    );
    expect(queryKey("customers", c)).not.toEqual(
      queryKey("customers", {
        ...c,
        scope: { ...c.scope, store_id: "lume-b2b" },
      }),
    );
    expect(queryKey("customers", c)).not.toEqual(
      queryKey("customers", { ...c, filters: { ...c.filters, days: 7 } }),
    );
  });
  it("supports filter empty states, aborted requests and unknown IDs", async () => {
    const c = context();
    c.filters.search = "not-found";
    expect(await demoApi.read("customers", c)).toEqual([]);
    await expect(demoApi.customer("unknown", c)).rejects.toMatchObject({
      status: 404,
    });
    await expect(demoApi.campaign("unknown", c)).rejects.toMatchObject({
      status: 404,
    });
    const controller = new AbortController();
    const request = demoApi.read("overview", {
      ...c,
      signal: controller.signal,
    });
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });
  it("read transport validates the envelope and sends scope without tokens", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: [],
          pagination: { page_size: 20, cursor: null, has_more: false },
          metadata: {
            contract_version: "1.0.0",
            store_id: "mx-fashion",
            generation: 1,
            policy_hash: "a".repeat(64),
            currency: "BRL",
            reporting_timezone: "America/Sao_Paulo",
            as_of: "2026-09-28T03:00:00Z",
            report_from: "2026-09-01",
            report_to: "2026-09-28",
            history_complete: false,
            facts_complete: true,
            limitations: [],
          },
        }),
        { status: 200 },
      ),
    );
    const api = createHttpApi("https://api.example.test", fetcher);
    const scope = {
      tenant_id: "tenant-mx",
      store_id: "mx-fashion",
      operation: "B2B" as const,
    };
    expect((await api.customers(scope)).data).toEqual([]);
    const [url, options] = fetcher.mock.calls[0];
    expect(url.searchParams.get("tenant_id")).toBe("tenant-mx");
    expect(url.searchParams.get("store_id")).toBe("mx-fashion");
    expect(options.credentials).toBe("include");
    expect(options.headers.Authorization).toBeUndefined();
  });
});

describe("B2B Overview structure", () => {
  it("keeps unknown tickets and ROI null and deduplicates campaign orders", async () => {
    const data = (await demoApi.read("overview", context())).b2b!;
    expect(data.revenue.map((m) => m.label)).toEqual([
      "Faturamento Solicitado",
      "Faturamento Atendido",
      "% de Atendimento",
      "Gap de Atendimento",
    ]);
    expect(data.customers[1].secondary?.label).toBe(
      "Ticket Médio de Aquisição",
    );
    expect(data.customers[2].secondary?.label).toBe("Ticket Médio de Retenção");
    expect(data.customers[1].secondary?.value).toBeNull();
    expect(data.customers[2].secondary?.value).toBeNull();
    expect(data.media.find((m) => m.label === "ROI")?.value).toBeNull();
    expect(new Set(data.attributedOrders.map((o) => o.id)).size).toBe(
      data.attributedOrders.length,
    );
    expect(
      data.attributedOrders.every((o) => o.campaign_names.length > 0),
    ).toBe(true);
    expect(
      data.series.every((d) => d.newCustomers === null && d.spend === null),
    ).toBe(true);
    const c = context();
    c.scope.operation = "B2C";
    c.scope.store_id = "mx-fashion-b2c";
    expect((await demoApi.read("overview", c)).b2b).toBeUndefined();
  });
});
