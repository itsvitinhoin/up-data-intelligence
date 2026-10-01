"use client";
import { B2BReadBoundary } from "@/hooks/use-dashboard-read";
import { RealCustomers, RealCustomer } from "./b2b-read-pages";

import { recordColumns } from "@/lib/list-export";
import { ListExport } from "@/components/exports";
import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowLeft, Building2, MapPin, Radio } from "lucide-react";
import Link from "next/link";
import { useWorkspace } from "@/features/providers";
import { useResource, useCustomer } from "@/hooks/use-resource";
import {
  PageHead,
  Panel,
  Loading,
  Failure,
  Choice,
  Notice,
  MetricCard,
} from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "@/components/data-table";
import {
  customerColumns,
  orderColumns,
  productColumns,
  Timeline,
  CampaignCard,
  MediaBadge,
} from "@/components/business";
import { OrderDialog } from "@/components/order-dialog";
import { retailCustomerMetrics } from "@/lib/retail-customer-metrics";
import type { ExportColumn } from "@/lib/erp-export";
import { date, money } from "@/lib/format";
import type { CustomerDetail, Order } from "@/types/domain";

const retailOrderColumns: ColumnDef<Order>[] = [
  {
    accessorKey: "id",
    header: "Pedido",
    cell: (cell) => <OrderDialog id={cell.getValue<string>()} allOrigins />,
  },
  {
    accessorKey: "date",
    header: "Data",
    cell: (cell) => date(cell.getValue<string>()),
  },
  { accessorKey: "requestedQuantity", header: "Peças compradas" },
  {
    accessorKey: "requested",
    header: "Valor",
    cell: (cell) => money(cell.getValue<string>()),
  },
  { accessorKey: "status", header: "Status comercial" },
];
const retailOrderExports: ExportColumn<Order>[] = [
  { header: "Pedido", value: (order) => order.id },
  { header: "Data", value: (order) => order.date },
  { header: "Peças compradas", value: (order) => order.requestedQuantity },
  { header: "Valor", value: (order) => order.requested },
  { header: "Status comercial", value: (order) => order.status },
];

function RetailCustomerDetail({ data }: { data: CustomerDetail }) {
  return (
    <>
      <Link className="back-link" href="/customers">
        <ArrowLeft size={15} /> Voltar para clientes
      </Link>
      <PageHead
        eyebrow="B2C · Cliente"
        title={data.customer.name}
        description={`${data.customer.city} · ${data.customer.state} / Compras observadas`}
        action={<span className="badge">{data.customer.segment}</span>}
      />
      <section className="metrics" aria-label="Indicadores do cliente B2C">
        {retailCustomerMetrics(data.orders).map((item) => (
          <MetricCard key={item.label} item={item} />
        ))}
      </section>
      <Notice>
        O histórico disponível é parcial. Receita representa valor captado de
        compras comerciais observadas; LTV real depende de histórico completo e
        pagamento confirmado.
      </Notice>
      <Panel
        title="Histórico de pedidos"
        subtitle="Pedidos observados desta operação, sem o filtro de período do topo"
      >
        <DataTable
          data={data.orders}
          columns={retailOrderColumns}
          exportColumns={retailOrderExports}
        />
      </Panel>
    </>
  );
}
function DemoCustomersPage() {
  const { filters, setFilters, scope } = useWorkspace();
  const b2c = scope?.operation === "B2C";
  const q = useResource("customers");
  return (
    <>
      <PageHead
        eyebrow="Relacionamento · Customer Intelligence"
        title={
          <>
            Conheça cada <em className="hl hl--up">cliente.</em>
          </>
        }
        description={
          b2c
            ? "Clientes novos e recorrentes, com histórico de compras da marca."
            : "Histórico comercial, recompra e participação de mídia em uma visão conectada."
        }
      />
      <FiltersBar />
      <Panel
        title="Sua carteira"
        subtitle={
          b2c
            ? "Clientes da operação selecionada"
            : "Empresas da operação selecionada"
        }
      >
        <div className="table-filters">
          <Input
            aria-label="Filtrar clientes"
            placeholder={
              b2c ? "Buscar cliente ou cidade" : "Buscar empresa ou cidade"
            }
            value={filters.search ?? ""}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
          />
          <Choice
            label="Estado"
            value={filters.state ?? "all"}
            onChange={(state) => setFilters({ ...filters, state })}
            options={[
              { value: "all", label: "Todos os estados" },
              ...["SP", "MG", "PR", "RJ", "SC", "GO", "BA", "RS"].map((s) => ({
                value: s,
                label: s,
              })),
            ]}
          />
          <Choice
            label="Segmento"
            value={filters.segment ?? "all"}
            onChange={(segment) => setFilters({ ...filters, segment })}
            options={[
              { value: "all", label: "Todos os clientes" },
              {
                value: "Primeira observada",
                label: b2c
                  ? "Novos · primeira compra observada"
                  : "Primeira compra observada",
              },
              { value: "Recorrente", label: "Recorrentes" },
              ...(!b2c
                ? [
                    { value: "Novo confirmado", label: "Novos confirmados" },
                    { value: "Reativado", label: "Reativados" },
                  ]
                : []),
            ]}
          />
          {!b2c && (
            <Choice
              label="Influência de mídia"
              value={filters.media ?? "all"}
              onChange={(media) => setFilters({ ...filters, media })}
              options={[
                { value: "all", label: "Todos" },
                { value: "yes", label: "Influenciados" },
                { value: "no", label: "Sem evidência" },
              ]}
            />
          )}
        </div>
        {["Novo confirmado", "Reativado"].includes(filters.segment ?? "") && (
          <Notice>
            Classificação ainda não confirmada: novos clientes exigem histórico
            completo; reativação depende de policy aprovada.
          </Notice>
        )}
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <Failure retry={() => void q.refetch()} />
        ) : (
          <DataTable
            data={q.data}
            columns={
              b2c
                ? customerColumns
                    .filter(
                      (c) =>
                        !("accessorKey" in c) ||
                        !["paid", "fulfilled"].includes(String(c.accessorKey)),
                    )
                    .map((c) =>
                      "accessorKey" in c && c.accessorKey === "requested"
                        ? { ...c, header: "Faturamento captado" }
                        : c,
                    )
                : customerColumns
            }
            exportColumns={
              b2c
                ? recordColumns(q.data).filter(
                    (c) => !["paid", "fulfilled"].includes(c.header),
                  )
                : undefined
            }
          />
        )}
      </Panel>
    </>
  );
}
function DemoCustomerDetailPage({ id }: { id: string }) {
  const { scope } = useWorkspace();
  const b2c = scope?.operation === "B2C";
  const q = useCustomer(id);
  const [tab, setTab] = useState("journey");
  if (q.isPending) return <Loading />;
  if (q.isError) return <Failure retry={() => void q.refetch()} />;
  const d = q.data;
  if (b2c) return <RetailCustomerDetail data={d} />;
  return (
    <>
      <Link className="back-link" href="/customers">
        <ArrowLeft size={15} /> Voltar para clientes
      </Link>
      <PageHead
        eyebrow="Customer 360"
        title={d.customer.name}
        description={`${d.customer.city} · ${d.customer.state} / Histórico observado`}
        action={<MediaBadge paid={d.customer.paid} />}
      />
      <div className="profile-strip glass">
        <span className="brand-avatar">{d.customer.name.slice(0, 2)}</span>
        <div>
          <h2>{d.customer.name}</h2>
          <p>
            <Building2 size={13} /> Empresa · <MapPin size={13} />
            {d.customer.city}, {d.customer.state} · {d.customer.segment}
          </p>
        </div>
        <div className="profile-dates">
          <small>Primeira compra observada</small>
          <span>{date(d.customer.firstPurchase)}</span>
        </div>
        <div className="profile-dates">
          <small>Última compra</small>
          <span>{date(d.customer.lastPurchase)}</span>
        </div>
      </div>
      <section className="metrics">
        {[
          {
            label: "Pedidos",
            value: String(d.customer.orders),
            format: "number" as const,
            hint: "Compras observadas",
          },
          {
            label: "Receita solicitada",
            value: d.customer.requested,
            format: "currency" as const,
            hint: "Histórico comercial",
          },
          {
            label: "Receita atendida",
            value: d.customer.fulfilled,
            format: "currency" as const,
            hint: "Não representa receita paga",
          },
          {
            label: "Peças Solicitadas",
            value: String(
              d.orders.reduce((s, o) => s + o.requestedQuantity, 0),
            ),
            format: "number" as const,
            hint: "Peças nos pedidos observados",
          },
          {
            label: "Peças Atendidas",
            value: String(
              d.orders.reduce((s, o) => s + o.fulfilledQuantity, 0),
            ),
            format: "number" as const,
            hint: "Peças atendidas",
          },
        ].map((m) => (
          <MetricCard key={m.label} item={m} />
        ))}
      </section>
      <Notice>
        Histórico completo ainda não confirmado. A primeira compra observada não
        comprova que o cliente é novo.
      </Notice>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="glass tab-list">
          <TabsTrigger value="journey">Jornada</TabsTrigger>
          <TabsTrigger value="orders">Pedidos</TabsTrigger>
          <TabsTrigger value="products">Produtos</TabsTrigger>
          <TabsTrigger value="marketing">Mídia e campanhas</TabsTrigger>
        </TabsList>
        <TabsContent value="journey">
          <Panel
            title="Cada interação, uma parte da história"
            subtitle="Eventos em ordem cronológica com evidência"
          >
            <Timeline events={d.timeline} />
          </Panel>
        </TabsContent>
        <TabsContent value="orders">
          <Panel
            title="Histórico de pedidos"
            subtitle="Solicitado e atendido separados"
          >
            <DataTable data={d.orders} columns={orderColumns} />
          </Panel>
        </TabsContent>
        <TabsContent value="products">
          <Panel
            title="Produtos comprados"
            subtitle="Quantidades e receita por produto demonstrativo"
          >
            <DataTable data={d.products} columns={productColumns} />
          </Panel>
        </TabsContent>
        <TabsContent value="marketing">
          <Panel title="Contatos de mídia">
            <dl className="detail-list">
              <div>
                <dt>Primeiro contato observado</dt>
                <dd>
                  {d.customer.paid
                    ? date(d.timeline[0]?.date)
                    : "Sem evidência"}
                </dd>
              </div>
              <div>
                <dt>Último contato pago observado</dt>
                <dd>
                  {d.customer.paid
                    ? date(
                        d.timeline.filter((e) => e.type === "paid_touch").at(-1)
                          ?.date,
                      )
                    : "Sem evidência"}
                </dd>
              </div>
            </dl>
          </Panel>
          <ListExport rows={d.campaigns} name="campanhas-cliente" />
          <div className="workspace-grid">
            {d.campaigns.map((c) => (
              <CampaignCard key={c.id} campaign={c} />
            ))}
            {!d.campaigns.length && (
              <Panel title="Sem evidência de mídia">
                <Radio />
                <p>Nenhuma campanha relacionada neste recorte.</p>
              </Panel>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </>
  );
}

export function CustomersPage() {
  return (
    <B2BReadBoundary real={(metadata) => <RealCustomers metadata={metadata} />}>
      <DemoCustomersPage />
    </B2BReadBoundary>
  );
}

export function CustomerDetailPage({ id }: { id: string }) {
  return (
    <B2BReadBoundary
      real={(metadata) => <RealCustomer metadata={metadata} id={id} />}
    >
      <DemoCustomerDetailPage id={id} />
    </B2BReadBoundary>
  );
}
