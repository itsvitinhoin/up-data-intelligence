import type { MarketingCreative } from "@/types/domain";
export function ratio(
  numerator: number | null,
  denominator: number | null,
): number | null {
  return numerator !== null && denominator !== null && denominator > 0
    ? numerator / denominator
    : null;
}
export function rankCreatives(
  rows: MarketingCreative[],
  kind: "ctr" | "cost" | "results",
  b2c: boolean,
) {
  const value = (row: MarketingCreative) =>
    kind === "ctr"
      ? ratio(row.clicks === null ? null : row.clicks * 100, row.impressions)
      : kind === "cost"
        ? ratio(row.spend, b2c ? row.purchases : row.leads)
        : b2c
          ? row.purchases
          : row.leads;
  return rows
    .filter(
      (row) => value(row) !== null && (kind !== "results" || value(row)! > 0),
    )
    .toSorted(
      (a, b) =>
        (kind === "cost" ? value(a)! - value(b)! : value(b)! - value(a)!) ||
        a.id.localeCompare(b.id),
    )
    .slice(0, 3);
}
