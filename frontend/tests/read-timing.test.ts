import { describe, expect, it } from "vitest";
import { numericServerTimings } from "@/services/auth/timing.server";
describe("safe Server-Timing diagnostics", () => {
  it("keeps only numeric approved durations and strips upstream descriptions and identities", () => {
    expect(
      numericServerTimings(
        'auth;dur=12.5, wif;dur=40, bq;dur=900, api_total;dur=960, serialization;dur=2, bff;dur=1100, bff_serialization;dur=1, customer;dur=9, scope;desc="secret", auth;dur=-1, wif;dur=NaN, bq;dur=1;desc="customer"',
      ),
    ).toEqual({
      auth: 12.5,
      wif: 40,
      bq: 900,
      api_total: 960,
      serialization: 2,
      bff: 1100,
      bff_serialization: 1,
    });
    expect(numericServerTimings("")).toEqual({});
  });
});
