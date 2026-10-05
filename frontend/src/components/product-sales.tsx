"use client";
import dynamic from "next/dynamic";
import { useWorkspace } from "@/features/providers";
import { Panel } from "@/components/ui-kit";
import { ListExport } from "@/components/exports";
import type { Product } from "@/types/domain";
const Bars = dynamic(
  () => import("@/components/erp-charts").then((m) => m.ErpBreakdown),
  { ssr: false },
);
export function ProductSales({ product }: { product: Product }) {
  const { dataMode } = useWorkspace();
  const sales = product.variantSales;
  return (
    <>
      {(["color", "size"] as const).map((key) => {
        const grouped = new Map<string, number>();
        const unknown = new Set<string>();
        sales?.forEach((row) => {
          const label = row[key];
          if (label === null) return;
          if (row.units === null) unknown.add(label);
          else grouped.set(label, (grouped.get(label) ?? 0) + row.units);
        });
        unknown.forEach((label) => grouped.delete(label));
        const rows = [...grouped].map(([label, value]) => ({ label, value }));
        const title = key === "color" ? "Vendas por cor" : "Vendas por tamanho";
        return (
          <Panel
            key={key}
            title={title}
            subtitle={
              dataMode === "demo"
                ? "Peças vendidas · distribuição demonstrativa, independente do estoque"
                : product.variantSalesBasis
                  ? "Peças atendidas observadas no período · atributos do catálogo atual"
                  : "Vendas por variante · cobertura ainda não certificada"
            }
            action={
              <ListExport rows={rows} name={`vendas-${product.sku}-${key}`} />
            }
          >
            {rows.length ? (
              <div role="group" aria-label={title}>
                <Bars data={rows} currency={false} />
              </div>
            ) : (
              <p className="muted">
                Vendas por variante ainda não disponíveis.
              </p>
            )}
          </Panel>
        );
      })}
    </>
  );
}
