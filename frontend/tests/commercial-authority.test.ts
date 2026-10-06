import { describe, expect, it } from "vitest";
import { decodeReadEnvelope } from "@/services/api/http";
import { parseIntelligence } from "@/services/api/intelligence";
import { managerMetrics } from "@/dashboard/presenters";
import { metadata, performance } from "./fixtures/restoration";

describe("UP Zero commercial authority and exact observed progression", () => {
  it("uses commercial ROAS, preserves paid count and never substitutes influence", () => {
    const data = {
      ...performance,
      commercial_requested_revenue: "200.0100",
      commercial_paid_revenue: null,
      commercial_roas_requested: "2.0001",
      commercial_roas_paid: null,
      available_media_spend: "100.00",
      roas_requested: "0.5",
      registration_cost: "10.00",
      commercial_orders_paid: 2,
      media_platforms: ["META"],
    };
    expect(
      parseIntelligence("performance", data).commercial_paid_revenue,
    ).toBeNull();
    const metrics = managerMetrics(
      [
        "roas_requested",
        "roas_captured",
        "total_media_spend",
        "registration_cost",
      ],
      "performance",
      data,
      metadata,
    );
    expect(metrics.map((m) => m.value)).toEqual([
      "2.0001",
      "2.0001",
      "100.00",
      "10.00",
    ]);
    expect(metrics[0].hint).toContain("UP Zero");
    expect(() =>
      parseIntelligence("performance", {
        ...data,
        commercial_requested_revenue: 200.01,
      }),
    ).toThrow();
    expect(() =>
      parseIntelligence("performance", {
        ...data,
        commercial_orders_paid: 1.5,
      }),
    ).toThrow();
    expect(
      managerMetrics(
        ["orders_paid"],
        "overview",
        { orders_paid: 2, revenue_paid: null },
        metadata,
      )[0].value,
    ).toBe("2");
  });
  it("accepts backend monthly authority and rejects duplicate months or floating money", () => {
    const row = {
      month: "2026-09",
      requested: "0.30",
      fulfilled: "0.15",
      orders: 2,
      paid_orders: 1,
      paid_revenue: null,
      meta_spend: "0.10",
      available_media_spend: "0.10",
      commercial_roas_requested: "3",
      requested_ticket: "0.15",
      recurring_rate: "100",
    };
    const parsed = parseIntelligence("performance", {
      ...performance,
      monthly: [row],
    });
    expect(parsed.monthly).toEqual([row]);
    expect(() =>
      parseIntelligence("performance", { ...performance, monthly: [row, row] }),
    ).toThrow();
    expect(() =>
      parseIntelligence("performance", {
        ...performance,
        monthly: [{ ...row, requested: 0.3 }],
      }),
    ).toThrow();
    expect(() =>
      parseIntelligence("performance", {
        ...performance,
        monthly: [{ ...row, month: "2026-13" }],
      }),
    ).toThrow();
  });
  it("parses fifth and sixth exactly, preserves unknown and rejects duplicate stages", () => {
    const stages = Array.from({ length: 6 }, (_, i) => ({
      stage: i + 1,
      buyers_observed: i === 4 ? 2 : i === 5 ? 1 : 0,
      share_observed: null,
      continuation_observed: null,
      requested_revenue_observed: i === 5 ? null : "0",
      accumulated_requested_revenue_observed: i === 5 ? null : "0",
      mean_days_observed: null,
    }));
    const data = {
      buyers_observed: 2,
      recurring_buyers_observed: 1,
      retention_observed: "0.5",
      retention_ticket_observed: null,
      frequency_observed: "2",
      progression: [],
      cohorts: [],
      exact_purchase_stages: stages,
      exact_purchase_stages_basis:
        "observed_purchase_number_in_selected_period",
    };
    const envelope = { data, metadata, pagination: null };
    const result = decodeReadEnvelope("retention", envelope);
    expect(
      result.data.exact_purchase_stages?.map((s) => s.buyers_observed),
    ).toEqual([0, 0, 0, 0, 2, 1]);
    expect(
      result.data.exact_purchase_stages?.[5].requested_revenue_observed,
    ).toBeNull();
    expect(result.metadata.history_complete).toBe(false);
    expect(() =>
      decodeReadEnvelope("retention", {
        ...envelope,
        data: {
          ...data,
          exact_purchase_stages: [...stages.slice(0, 5), stages[4]],
        },
      }),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope("retention", {
        ...envelope,
        data: { ...data, exact_purchase_stages_basis: "five_plus_split" },
      }),
    ).toThrow();
  });
});
