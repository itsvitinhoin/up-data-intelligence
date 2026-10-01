"use client";
import { B2BReadBoundary } from "@/hooks/use-dashboard-read";
import { RealAcquisition } from "./b2b-read-pages";

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
  const metrics: Metric[] = q.data
    ? [
        {
          label: "Clientes compradores",
          value: String(q.data.buyerCount),
          format: "number",
          hint: "Todos os compradores da marca no período",
        },
        {
          label: "Primeiras compras observadas",
          value: String(q.data.customers.length),
          format: "number",
          hint: "Clientes cuja primeira compra observada está no recorte",
        },
        {
          label: "Novos clientes confirmados",
          value:
            q.data.confirmedNewCustomers === null
              ? null
              : String(q.data.confirmedNewCustomers),
          format: "number",
          hint: "Exige histórico comercial completo",
        },
        {
          label: "% primeiras compras observadas",
          value: q.data.buyerCount
            ? String((q.data.customers.length / q.data.buyerCount) * 100)
            : null,
          format: "percent",
          hint: "Primeiras compras observadas / compradores do período",
        },
        {
          label: "Receita solicitada · primeira compra",
          value: q.data.requested,
          format: "currency",
          hint: "Somente o primeiro pedido qualificante observado",
        },
        {
          label: "Receita atendida · primeira compra",
          value: q.data.fulfilled,
          format: "currency",
          hint: "Atendimento comercial não confirma pagamento",
        },
        {
          label: "Ticket solicitado · primeira compra",
          value: q.data.firstOrders.length
            ? String(Number(q.data.requested) / q.data.firstOrders.length)
            : null,
          format: "currency",
          hint: "Solicitado / primeiros pedidos observados",
        },
        {
          label: "Ticket atendido · primeira compra",
          value: q.data.firstOrders.length
            ? String(Number(q.data.fulfilled) / q.data.firstOrders.length)
            : null,
          format: "currency",
          hint: "Atendido / primeiros pedidos observados",
        },
      ]
    : [];
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
        <Loading />
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
    <B2BReadBoundary
      real={(metadata) => <RealAcquisition metadata={metadata} />}
    >
      <DemoAcquisitionPage />
    </B2BReadBoundary>
  );
}
