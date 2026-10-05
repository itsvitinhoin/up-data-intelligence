import { describe, it, expect } from "vitest";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor, adminApi } from "@/services/demo/admin";
import { defaultFilters } from "@/config/tenants";
import type { RequestContext } from "@/types/domain";
function context(): RequestContext {
  return {
    scope: {
      tenant_id: "demo-up",
      store_id: "mx-fashion-b2c",
      operation: "B2C",
    },
    session: sessionFor("maria-demo"),
    filters: { ...defaultFilters },
  };
}
describe("retail and brand integration boundaries", () => {
  it("keeps financial confirmation separate from commercial fulfillment and paid-media influence", async () => {
    const d = await demoApi.read("retail", context());
    expect(d.overview.map((m) => m.label)).toEqual([
      "Faturamento Captado",
      "Faturamento Aprovado",
      "Receita Cancelada",
      "% de Aprovação",
      "Clientes Novos",
      "Clientes Recorrentes",
      "CAC",
      "% de Recompra",
    ]);
    expect(
      d.overview.find((m) => m.label === "Faturamento Aprovado")?.value,
    ).toBeNull();
    expect(d.paidRate).toBeNull();
    expect(d.series.every((s) => s.approved === null)).toBe(true);
    expect(d.performance).toHaveLength(9);
    for (const label of [
      "Investimento de Mídia Total",
      "ROAS Captado",
      "ROAS Aprovado",
      "Custo por Sessão",
    ])
      expect(d.performance.find((m) => m.label === label)?.value).toBeNull();
  });
  it("scopes retail sessions and product sales to period and keeps stock independent", async () => {
    const c = context();
    const d = await demoApi.read("retail", c);
    const products = await demoApi.read("products", c);
    c.filters.from = "2026-09-20";
    c.filters.to = "2026-09-25";
    const smaller = await demoApi.read("retail", c);
    const selected = await demoApi.read("products", c);
    expect(
      Number(smaller.performance.find((m) => m.label === "Sessões")?.value),
    ).toBeLessThan(
      Number(d.performance.find((m) => m.label === "Sessões")?.value),
    );
    selected.forEach((p, i) => {
      expect(p.variantSales?.reduce((s, v) => s + (v.units ?? NaN), 0)).toBe(
        p.units,
      );
      expect(p.units).toBeLessThan(products[i].units);
      expect(p.stock).toBe(products[i].stock);
    });
    c.filters.from = "2027-01-01";
    c.filters.to = "2027-01-03";
    expect(await demoApi.read("products", c)).toEqual([]);
    expect(
      (await demoApi.read("retail", c)).performance.find(
        (m) => m.label === "Taxa de Conversão",
      )?.value,
    ).toBeNull();
  });
  it("retail customer lists ignore paid-media filtering", async () => {
    const c = context();
    const all = await demoApi.read("customers", c);
    c.filters.media = "yes";
    expect(await demoApi.read("customers", c)).toEqual(all);
  });
  it("brand settings stay scoped and reject credential fields", async () => {
    const s = sessionFor("up-admin");
    const brands = await adminApi.brands(s);
    const b = brands[0];
    await adminApi.saveBrand(
      {
        ...b,
        integrations: [
          { provider: "Google Ads", enabled: true, accountId: "demo-google" },
        ],
      },
      s,
    );
    const updated = await adminApi.brands(s);
    expect(updated[0].integrations?.[0].accountId).toBe("demo-google");
    expect(updated[1]).toEqual(brands[1]);
    await expect(
      adminApi.saveBrand(
        {
          ...b,
          integrations: [
            {
              provider: "ERP",
              enabled: true,
              accountId: "demo",
              ...{ apiKey: "not-a-key" },
            },
          ],
        },
        s,
      ),
    ).rejects.toMatchObject({ status: 400 });
    await expect(
      adminApi.saveBrand(b, sessionFor("maria-demo")),
    ).rejects.toMatchObject({ status: 403 });
    await adminApi.saveBrand(b, s);
  });
});
