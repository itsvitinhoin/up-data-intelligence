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
        sales?.forEach((row) =>
          grouped.set(row[key], (grouped.get(row[key]) ?? 0) + row.units),
        );
        const rows = [...grouped].map(([label, value]) => ({ label, value }));
        const title = key === "color" ? "Vendas por cor" : "Vendas por tamanho";
        return (
          <Panel
            key={key}
            title={title}
            subtitle={
              dataMode === "demo"
                ? "Peças vendidas · distribuição demonstrativa, independente do estoque"
                : "Vendas por variante · cobertura ainda não certificada"
            }
            action={
              <ListExport rows={rows} name={`vendas-${product.sku}-${key}`} />
            }
          >
            {sales?.length ? (
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
