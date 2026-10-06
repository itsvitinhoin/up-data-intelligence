import { describe, expect, it } from "vitest";
import { decodeReadEnvelope } from "@/services/api/http";
import { metaCampaignView } from "@/services/api/meta-ads";
import { metadata } from "./fixtures/restoration";
import {
  metaPeriodMetric as metric,
  metaPeriodData as data,
} from "./fixtures/meta-period";
const decode = (value: unknown) =>
  decodeReadEnvelope("metaAds", { data: value, pagination: null, metadata })
    .data;
describe("official Meta period contract", () => {
  it("preserves money and provider unique reach without creating commercial revenue", () => {
    const r = decode(data());
    expect(r.summary.reach).toBe(800);
    expect(r.summary.frequency).toBe("1.25");
    expect(r.series?.[0].roas).toBe("3.333333333333333333");
    expect(metaCampaignView(r.campaigns[0])).toMatchObject({
      spend: "0.30",
      requested: null,
      fulfilled: null,
      orders: null,
      roasRequested: null,
      roasFulfilled: null,
    });
  });
  it("preserves unknown purchases and unmaterialized daily coverage", () => {
    const value = data();
    const r = decode({
      ...value,
      summary: {
        ...value.summary,
        meta_reported_purchases: null,
        meta_reported_purchase_value: null,
        cpa: null,
        roas: null,
      },
      series: null,
    });
    expect(r.series).toBeNull();
    expect(r.summary.meta_reported_purchases).toBeNull();
  });
  it.each([
    "float",
    "negative",
    "duplicate",
    "wrong-level",
    "credential-url",
    "foreign-origin",
    "outside-window",
    "duplicate-day",
    "float-series",
    "commercial-field",
  ])("rejects %s", (reason) => {
    const v: Record<string, unknown> = data();
    const base = data();
    if (reason === "float") v.summary = { ...base.summary, spend: 0.3 };
    if (reason === "negative") v.summary = { ...base.summary, reach: -1 };
    if (reason === "duplicate")
      v.campaigns = [...base.campaigns, ...base.campaigns];
    if (reason === "wrong-level") v.ads = [metric("campaign")];
    if (reason === "credential-url")
      v.ads = [
        {
          ...metric("ad"),
          preview_url:
            "https://scontent.test.fbcdn.net/p.jpg?access_token=synthetic",
        },
      ];
    if (reason === "foreign-origin")
      v.ads = [
        { ...metric("ad"), preview_url: "https://unapproved.example/p.jpg" },
      ];
    if (reason === "outside-window")
      v.series = [{ ...base.series[0], date: "2026-10-05" }];
    if (reason === "duplicate-day") v.series = [...base.series, ...base.series];
    if (reason === "float-series")
      v.series = [{ ...base.series[0], spend: 0.3 }];
    if (reason === "commercial-field")
      v.summary = { ...base.summary, requested_revenue: "1.00" };
    expect(() => decode(v)).toThrow();
  });
});
