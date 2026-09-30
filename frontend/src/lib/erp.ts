import type { ErpProductRow } from "@/types/erp";
export function filterProducts(
  rows: ErpProductRow[],
  search: string,
  category: string,
  stock: string,
  sort: string,
) {
  const term = search.trim().toLocaleLowerCase("pt-BR");
  const key: Record<string, keyof ErpProductRow> = {
    revenue: "revenue",
    units: "units",
    stock: "stock",
    turnover: "turnoverPct",
    sales_power: "salesPower",
    margin: "grossMarginPct",
    coverage: "coverageDays",
  };
  return rows
    .filter(
      (p) =>
        (category === "all" || p.category === category) &&
        `${p.name} ${p.category} ${p.variants.map((v) => v.sku).join(" ")}`
          .toLocaleLowerCase("pt-BR")
          .includes(term) &&
        (stock === "all" ||
          p.variants.some((v) =>
            stock === "in_stock"
              ? v.stock > 0
              : stock === "negative"
                ? v.stock < 0
                : v.stock === 0,
          )),
    )
    .sort(
      (a, b) =>
        Number(b[key[sort] ?? "revenue"] ?? -1) -
        Number(a[key[sort] ?? "revenue"] ?? -1),
    );
}
