import { describe, expect, it } from "vitest";
import { demoApi } from "@/services/demo/adapter";
import { sessionFor } from "@/services/demo/admin";
import { rankCreatives, ratio } from "@/lib/marketing";
import { defaultFilters } from "@/config/tenants";
import type { RequestContext } from "@/types/domain";
const context = (): RequestContext => ({
  scope: { tenant_id: "demo-up", store_id: "mx-fashion-b2b", operation: "B2B" },
  session: sessionFor("maria-demo"),
  filters: { ...defaultFilters },
});
describe("Marketing metrics and rankings", () => {
  it("reconciles ad spend to campaigns and daily totals, with weighted CTR", async () => {
    const data = await demoApi.read("marketing", context());
    const spend = data.creatives.reduce((s, a) => s + a.spend, 0);
    expect(data.campaigns.reduce((s, a) => s + Number(a.spend), 0)).toBeCloseTo(
      spend,
      2,
    );
    expect(data.series.reduce((s, a) => s + a.spend, 0)).toBeCloseTo(spend, 2);
    expect(data.series.reduce((s, a) => s + a.leads, 0)).toBe(
      data.creatives.reduce((s, a) => s + a.leads, 0),
    );
    expect(
      data.creatives.every(
        (a) =>
          a.preview.startsWith("/demo-creatives/") &&
          a.id.startsWith("mx-fashion-b2b:"),
      ),
    ).toBe(true);
    const ranked = rankCreatives(data.creatives, "ctr", false);
    expect(ranked[0].id).toBe(
      [...data.creatives].sort(
        (a, b) => b.clicks / b.impressions - a.clicks / a.impressions,
      )[0].id,
    );
  });
  it("excludes zero-denominator creatives and selects B2C cost by purchases", async () => {
    const data = await demoApi.read("marketing", context());
    const [a] = data.creatives;
    const rows = [
      { ...a, id: "a", spend: 100, leads: 100, purchases: 1 },
      { ...a, id: "b", spend: 100, leads: 1, purchases: 100 },
      { ...a, id: "zero", leads: 0, purchases: 0, impressions: 0 },
    ];
    expect(rankCreatives(rows, "cost", false)[0].id).toBe("a");
    expect(rankCreatives(rows, "cost", true)[0].id).toBe("b");
    expect(rankCreatives(rows, "ctr", false).some((a) => a.id === "zero")).toBe(
      false,
    );
    expect(rankCreatives(rows, "cost", true).some((a) => a.id === "zero")).toBe(
      false,
    );
    expect(ratio(1, 0)).toBeNull();
    expect(rankCreatives([], "ctr", false)).toEqual([]);
  });
  it("respects channel, dates and brand access without leaking other brands", async () => {
    const c = context();
    c.filters.days = 7;
    const data = await demoApi.read("marketing", c);
    expect(data.series).toHaveLength(7);
    c.filters.channel = "organic";
    expect((await demoApi.read("marketing", c)).creatives).toHaveLength(0);
    c.scope.store_id = "lume-b2b";
    await expect(demoApi.read("marketing", c)).rejects.toMatchObject({
      status: 403,
    });
  });
});
