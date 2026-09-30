import type { Product } from "@/types/domain";
export const conversionRate = (p: Product) =>
  p.views > 0 ? (p.orders / p.views) * 100 : null;
export const brokenGrade = (p: Product) =>
  p.variants?.length
    ? p.variants.some((v) => v.stock === 0)
    : Object.values(p.sizes).some((v) => !v);
export const gradeStatus = (p: Product) =>
  brokenGrade(p) ? "Quebrada" : "Completa";
/** Demo rule: >=1.5% of views become orders and grade broken or stock exhausted. */
export const atRisk = (p: Product) =>
  (conversionRate(p) ?? 0) >= 1.5 && (brokenGrade(p) || p.stock === 0);
export function promising(p: Product, all: Product[]) {
  const ordered = all.map((r) => r.views).toSorted((a, b) => a - b);
  const median = ordered.length
    ? ordered[Math.floor((ordered.length - 1) / 2)]
    : 0;
  return (
    p.active !== false && p.views < median && (conversionRate(p) ?? 0) >= 1.5
  );
}
export function groupedSales(
  rows: Product[],
  key: "category" | "size" | "color",
) {
  const grouped = new Map<string, number>();
  for (const product of rows) {
    const cells =
      key === "category"
        ? [{ name: product.category ?? "Sem categoria", units: product.units }]
        : (product.variantSales?.map((v) => ({
            name: v[key],
            units: v.units,
          })) ?? []);
    for (const cell of cells)
      grouped.set(cell.name, (grouped.get(cell.name) ?? 0) + cell.units);
  }
  return [...grouped]
    .map(([label, value]) => ({ label, value }))
    .toSorted((a, b) => b.value - a.value || a.label.localeCompare(b.label));
}
export const turnoverPercent = (sold: number, stock: number) =>
  stock > 0 ? (sold / stock) * 100 : null;
export function stockPower(rows: Product[]) {
  const active = rows.filter((r) => r.active === true);
  if (active.some((r) => r.salePrice === null || r.salePrice === undefined))
    return null;
  return active.reduce((sum, r) => sum + r.stock * Number(r.salePrice), 0);
}
