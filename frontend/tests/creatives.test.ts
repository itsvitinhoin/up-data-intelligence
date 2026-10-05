import { describe, expect, it } from "vitest";
import { parseCreatives, creativeView } from "@/services/api/creatives";
import { decodeReadEnvelope } from "@/services/api/http";
import { rankCreatives } from "@/lib/marketing";
import { metadata, envelope } from "./fixtures/restoration";
import { creative } from "./fixtures/creatives";

describe("certified creative contracts", () => {
  it("validates the envelope and preserves exact decimal transport", () => {
    const result = decodeReadEnvelope("creatives", envelope([creative]));
    expect(result.data[0].spend).toBe("123.450000001");
    expect(result.data[0].meta_reported_purchase_value).toBe("250.12");
    const view = creativeView(result.data[0]);
    expect(view.source).toBe("real");
    expect(view.preview).toBe(creative.preview_url);
    expect(view.leads).toBeNull();
    expect(rankCreatives([view], "cost", true)).toHaveLength(1);
  });
  it("keeps unknown conversion metrics out of CPA/purchase rankings", () => {
    const row = {
      ...creative,
      cpa: null,
      meta_reported_purchases: null,
      meta_reported_purchase_value: null,
      preview_url: null,
      reporting_definition: {
        ...creative.reporting_definition,
        purchase_action_type: null,
      },
    };
    const view = creativeView(parseCreatives([row], metadata)[0]);
    expect(view.purchases).toBeNull();
    expect(rankCreatives([view], "cost", true)).toEqual([]);
    expect(rankCreatives([view], "results", true)).toEqual([]);
    expect(rankCreatives([view], "ctr", true)).toHaveLength(1);
  });
  it.each([
    { store_id: "foreign" },
    { basis: "campaign_daily" },
    { spend: 123.45 },
    { reach: 50 },
    { frequency: "2" },
    { report_from: "2025-01-01" },
    { preview_url: "https://untrusted.invalid/image" },
    { preview_url: "https://media.fbcdn.net/image?access_token=synthetic" },
    { preview_observed_at: null },
    { evidence_hash: "bad" },
    { email: "synthetic@example.invalid" },
    {
      reporting_definition: {
        ...creative.reporting_definition,
        level: "campaign",
      },
    },
  ])("rejects unsafe scope, grain, decimals, metadata or URL: %j", (patch) => {
    expect(() =>
      parseCreatives([{ ...creative, ...patch }], metadata),
    ).toThrow();
  });
  it("rejects duplicate ads and fabricated purchases without a definition", () => {
    expect(() => parseCreatives([creative, creative], metadata)).toThrow();
    expect(() =>
      parseCreatives(
        [
          {
            ...creative,
            reporting_definition: {
              ...creative.reporting_definition,
              purchase_action_type: null,
            },
          },
        ],
        metadata,
      ),
    ).toThrow();
  });
});
