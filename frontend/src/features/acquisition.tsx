"use client";
import { B2BReadBoundary } from "@/hooks/use-dashboard-read";

import { LeadCards } from "@/components/lead-cards";
import { OrderDialog } from "@/components/order-dialog";
import type { ColumnDef } from "@tanstack/react-table";
import { useResource } from "@/hooks/use-resource";
import { FiltersBar } from "@/components/shell";
import {
  PageHead,
  Panel,
  MetricCard,
  Loading,
  Failure,
  Notice,
} from "@/components/ui-kit";
import { DataTable } from "@/components/data-table";
import { customerColumns, orderColumns } from "@/components/business";
import { ConversionVelocity } from "@/features/lifecycle";
import { ticket } from "@/services/api/overview-presenter";
import { date } from "@/lib/format";
import type { Customer, Metric, Order } from "@/types/domain";
const columns: ColumnDef<Customer>[] = [
  ...customerColumns.filter(
    (column) =>
      "accessorKey" in column &&
      ["name", "city", "state"].includes(String(column.accessorKey)),
  ),
  {
    accessorKey: "firstPurchase",
    header: "Primeira compra observada",
    cell: (c) => date(c.getValue<string>()),
  },
];
const firstOrderColumns: ColumnDef<Order>[] = orderColumns.map<
  ColumnDef<Order>
>((column) =>
  "accessorKey" in column && column.accessorKey === "id"
    ? {
        ...column,
        cell: ({ row }) => <OrderDialog id={row.original.id} allOrigins />,
      }
    : column,
);
function DemoAcquisitionPage() {
  const q = useResource("acquisition");
  const metrics: Metric[] = q.compare((data) => [
    {
      label: "Clientes compradores",
      value: data.buyerCount === null ? null : String(data.buyerCount),
      format: "number",
      hint: "Todos os compradores da marca no período",
    },
    {
      label: "Primeiras compras observadas",
      value: String(data.customers.length),
      format: "number",
      hint: "Clientes cuja primeira compra observada está no recorte",
    },
    {
      label: "Novos clientes confirmados",
      value:
        data.confirmedNewCustomers === null
          ? null
          : String(data.confirmedNewCustomers),
      format: "number",
      hint: "Exige histórico comercial completo",
    },
    {
      label: "% primeiras compras observadas",
      value: data.buyerCount
        ? String((data.customers.length / data.buyerCount) * 100)
        : null,
      format: "percent",
      hint: "Primeiras compras observadas / compradores do período",
    },
    {
      label: "Receita solicitada · primeira compra",
      value: data.requested,
      format: "currency",
      hint: "Somente o primeiro pedido qualificante observado",
    },
    {
      label: "Receita atendida · primeira compra",
      value: data.fulfilled,
      format: "currency",
      hint: "Atendimento comercial não confirma pagamento",
    },
    {
      label: "Ticket solicitado · primeira compra",
      value: ticket(data.requested, data.firstOrders.length),
      format: "currency",
      hint: "Solicitado / primeiros pedidos observados",
    },
    {
      label: "Ticket atendido · primeira compra",
      value: ticket(data.fulfilled, data.firstOrders.length),
      format: "currency",
      hint: "Atendido / primeiros pedidos observados",
    },
  ]);
  return (
    <>
      <PageHead
        eyebrow="B2B · Aquisição da marca"
        title={
          <>
            Novos relacionamentos,{" "}
            <em className="hl hl--up">todas as origens.</em>
          </>
        }
        description="A entrada de compradores na base inteira da marca, com ou sem participação de mídia paga."
      />
      <FiltersBar showChannel={false} />
      <Notice>
        Todas as origens estão incluídas. Com o histórico atual, primeira compra
        observada não comprova que o cliente seja novo para a marca. Novos
        confirmados permanecem indisponíveis.
      </Notice>
      {q.isPending ? (
        <Loading page />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <>
          <LeadCards />
          <section aria-label="Indicadores de aquisição" className="metrics">
            {metrics.map((item, index) => (
              <MetricCard key={item.label} item={item} index={index} />
            ))}
          </section>
          <ConversionVelocity />
          <Panel
            title="Clientes com primeira compra observada"
            subtitle="Base geral da marca · independe de participação de campanhas"
          >
            <DataTable data={q.data.customers} columns={columns} />
          </Panel>
          <Panel
            title="Primeiros pedidos observados"
            subtitle="Um primeiro pedido qualificante por cliente, dentro do período selecionado"
          >
            <DataTable data={q.data.firstOrders} columns={firstOrderColumns} />
          </Panel>
        </>
      )}
    </>
  );
}

export function AcquisitionPage() {
  return (
    <B2BReadBoundary>
      <DemoAcquisitionPage />
    </B2BReadBoundary>
  );
}
