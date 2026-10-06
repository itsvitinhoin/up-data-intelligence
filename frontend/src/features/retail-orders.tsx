"use client";
import dynamic from "next/dynamic";
import type { ColumnDef } from "@tanstack/react-table";
import { useResource } from "@/hooks/use-resource";
import { useWorkspace } from "@/features/providers";
import { periodDays } from "@/lib/period";
import { OrderDialog } from "@/components/order-dialog";
import { DataTable } from "@/components/data-table";
import { FiltersBar } from "@/components/shell";
import {
  PageHead,
  Panel,
  MetricCard,
  Loading,
  Failure,
  Notice,
} from "@/components/ui-kit";
import { money, date } from "@/lib/format";
import type { Order, Metric } from "@/types/domain";
import type { ExportColumn } from "@/lib/erp-export";
const Chart = dynamic(
  () =>
    import("@/components/retail-orders-chart").then((m) => m.RetailOrdersChart),
  { ssr: false },
);
const columns: ColumnDef<Order>[] = [
  {
    accessorKey: "id",
    header: "Pedido",
    cell: (c) => <OrderDialog id={c.getValue<string>()} />,
  },
  {
    accessorKey: "date",
    header: "Data",
    cell: (c) => date(c.getValue<string>()),
  },
  { accessorKey: "requestedQuantity", header: "Peças" },
  {
    accessorKey: "requested",
    header: "Faturamento captado",
    cell: (c) => money(c.getValue<string>()),
  },
  { accessorKey: "status", header: "Status comercial" },
];
const exports: ExportColumn<Order>[] = [
  { header: "Pedido", value: (r) => r.id },
  { header: "Data", value: (r) => r.date },
  { header: "Peças", value: (r) => r.requestedQuantity },
  { header: "Faturamento captado", value: (r) => r.requested },
  { header: "Status comercial", value: (r) => r.status },
];
export function RetailOrdersPage() {
  const { filters, dataMode } = useWorkspace();
  const current = useResource("orders"),
    all = useResource("order_history"),
    retail = useResource("retail");
  const metrics = retail.data?.overview.slice(0, 4).map((m, i): Metric =>
    i === 3
      ? {
          ...m,
          label: "% de Faturamento Pago",
          hint:
            dataMode === "demo"
              ? "B2C · DADOS DEMONSTRATIVOS · pagamento simulado no cenário sintético."
              : "Valor com pagamento confirmado / faturamento captado × 100. Fonte financeira não conectada.",
        }
      : m,
  );
  const series =
    current.data &&
    periodDays(filters).map((date) => {
      const rows = current.data!.filter((o) => o.date === date);
      return {
        date,
        orders: rows.length,
        revenue: rows.reduce((sum, o) => sum + Number(o.requested), 0),
      };
    });
  return (
    <>
      <PageHead
        eyebrow="B2C · Pedidos"
        title={
          <>
            Pedidos e <em className="hl hl--up">faturamento.</em>
          </>
        }
        description="Indicadores comerciais, evolução e duas visões do histórico de pedidos."
      />
      <FiltersBar />
      <Notice>
        {dataMode === "demo"
          ? "B2C · DADOS DEMONSTRATIVOS · pagamento simulado. "
          : "Pagamento e faturamento aprovado aguardam a fonte financeira. "}{" "}
        O histórico completo abaixo ignora somente o período e os filtros
        comerciais do topo, mantendo a marca e operação autorizadas.
      </Notice>
      {retail.isPending ? (
        <Loading />
      ) : retail.isError ? (
        <Failure retry={() => void retail.refetch()} />
      ) : (
        <section className="metrics" aria-label="Indicadores de pedidos B2C">
          {metrics?.map((m) => (
            <MetricCard key={m.label} item={m} />
          ))}
        </section>
      )}
      <Panel
        title="Pedidos × Faturamento por período"
        subtitle="Número de pedidos e valor captado por dia no recorte selecionado"
      >
        {current.isPending ? (
          <Loading />
        ) : current.isError ? (
          <Failure retry={() => void current.refetch()} />
        ) : (
          <Chart data={series ?? []} />
        )}
      </Panel>
      <Panel
        title="Pedidos no recorte"
        subtitle="Período e filtros selecionados no topo"
      >
        {current.isPending ? (
          <Loading />
        ) : current.isError ? (
          <Failure retry={() => void current.refetch()} />
        ) : (
          <DataTable
            data={current.data}
            columns={columns}
            exportColumns={exports}
          />
        )}
      </Panel>
      <Panel
        title="Todos os pedidos"
        subtitle="Histórico demonstrativo da operação · independente do período selecionado"
      >
        {all.isPending ? (
          <Loading />
        ) : all.isError ? (
          <Failure retry={() => void all.refetch()} />
        ) : (
          <DataTable
            data={all.data}
            columns={columns}
            exportColumns={exports}
          />
        )}
      </Panel>
    </>
  );
}
