"use client";
import { Cards, RemoteTable } from "./read-components";
import {
  RealIntelligencePerformance,
  RealCustomerIntelligence,
} from "./intelligence-read-pages";
import { useState, type ReactNode } from "react";
import Link from "next/link";
import BrazilMap from "@svg-maps/brazil";
import { useDashboardRead, usePageSource } from "@/hooks/use-dashboard-read";
import { ApiError } from "@/services/api/access";
import type {
  ReadMetadata,
  LiveOrder,
  ReadEnvelope,
  ReadResourceMap,
} from "@/services/api/http";
import { percentOfRatio, ticket } from "@/services/api/overview-presenter";
import {
  PageHead,
  Panel,
  Notice,
  Loading,
  Failure,
  Choice,
} from "@/components/ui-kit";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { metric, money, date, number } from "@/lib/format";

function ReadView<T>({
  result,
  metadata,
  children,
  track = true,
}: {
  track?: boolean;
  result: {
    isPending: boolean;
    isError: boolean;
    data?: ReadEnvelope<T>;
    refetch: () => unknown;
  };
  metadata: ReadMetadata;
  children: (data: T) => ReactNode;
}) {
  usePageSource(
    result.isPending
      ? "loading-real"
      : result.isError
        ? "error-real"
        : metadata.history_complete
          ? "real"
          : "partial-real",
    metadata,
    !track,
  );
  if (result.isPending) return <Loading />;
  if (result.isError || !result.data)
    return (
      <Failure
        retry={() => void result.refetch()}
        description="Nenhum dado demonstrativo foi usado. Atualize se a publicação mudou."
      />
    );
  return children(result.data.data);
}
function useCursor() {
  const [stack, setStack] = useState<(string | undefined)[]>([undefined]);
  return {
    cursor: stack[stack.length - 1],
    canPrevious: stack.length > 1,
    previous: () => setStack((s) => s.slice(0, -1)),
    next: (cursor: string | null) => {
      if (cursor) setStack((s) => [...s, cursor]);
    },
  };
}
const orderColumns = [
  { label: "Pedido", value: (o: LiveOrder) => o.order_id },
  {
    label: "Cliente",
    value: (o: LiveOrder) =>
      o.customer_id === null ? (
        "—"
      ) : (
        <Link href={`/customers/${encodeURIComponent(o.customer_id)}`}>
          {o.customer_id}
        </Link>
      ),
  },
  { label: "Data", value: (o: LiveOrder) => date(o.created_at) },
  { label: "Status", value: (o: LiveOrder) => o.order_status ?? "—" },
  {
    label: "Pagamento (origem)",
    value: (o: LiveOrder) => o.payment_status ?? "—",
  },
  { label: "Solicitado", value: (o: LiveOrder) => money(o.requested_total, 2) },
  { label: "Atendido", value: (o: LiveOrder) => money(o.fulfilled_total, 2) },
  {
    label: "Peças solicitadas",
    value: (o: LiveOrder) => number(o.requested_items_qty),
  },
  {
    label: "Peças atendidas",
    value: (o: LiveOrder) => number(o.fulfilled_items_qty),
  },
];
function OrderList({
  metadata,
  customerId,
  status,
}: {
  metadata: ReadMetadata;
  customerId?: string;
  status?: string;
}) {
  const cursor = useCursor();
  const result = useDashboardRead(
    customerId ? "customerOrders" : "orders",
    metadata,
    { customerId, status, cursor: cursor.cursor },
  );
  return (
    <ReadView result={result} metadata={metadata} track={!customerId}>
      {(rows) => (
        <RemoteTable
          rows={rows}
          columns={orderColumns}
          rowKey={(o) => o.order_id}
          pagination={result.data!.pagination}
          canPrevious={cursor.canPrevious}
          previous={cursor.previous}
          next={() => cursor.next(result.data!.pagination!.cursor)}
        />
      )}
    </ReadView>
  );
}
export function RealOrders({ metadata }: { metadata: ReadMetadata }) {
  const [status, setStatus] = useState("all");
  return (
    <>
      <PageHead
        eyebrow="B2B · Analytics V1 + CORE"
        title="Pedidos"
        description="Pedidos observados no recorte. Solicitado e atendido permanecem separados."
      />
      <Notice>
        Status de pagamento é informação da origem. Atendido não significa pago.
        CORE reflete o snapshot atual da request, não a geração de
        materialização comercial.
      </Notice>
      <Panel
        title="Pedidos no recorte"
        action={
          <Choice
            label="Status do pedido"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "Todos" },
              ...[
                "RESERVED",
                "CONFIRMED",
                "PROCESSING",
                "INVOICED",
                "SHIPPED",
                "CANCELED",
              ].map((value) => ({ value, label: value })),
            ]}
          />
        }
      >
        <OrderList
          key={status}
          metadata={metadata}
          status={status === "all" ? undefined : status}
        />
      </Panel>
    </>
  );
}
export function RealAcquisition({ metadata }: { metadata: ReadMetadata }) {
  const result = useDashboardRead("acquisition", metadata);
  return (
    <>
      <PageHead
        eyebrow="Aquisição · Analytics V1"
        title="Primeira compra observada"
        description="A primeira compra é resolvida no histórico disponível inteiro e depois selecionada pelo período."
      />
      <ReadView result={result} metadata={metadata}>
        {(v) => (
          <>
            <Cards
              items={[
                ["Compradores observados", v.buyers_observed, "number"],
                [
                  "Primeira compra · clientes observados",
                  v.first_purchase_customers_observed,
                  "number",
                ],
                [
                  "Primeira compra · pedidos observados",
                  v.first_purchase_orders_observed,
                  "number",
                ],
                [
                  "Novos confirmados",
                  v.confirmed_new_customers,
                  "number",
                  "Histórico incompleto; novos clientes definitivos não são confirmados.",
                ],
                [
                  "Solicitado na primeira compra",
                  v.requested_first_purchase_observed,
                  "currency",
                ],
                [
                  "Atendido na primeira compra",
                  v.fulfilled_first_purchase_observed,
                  "currency",
                ],
                [
                  "Ticket primeira compra observado",
                  ticket(
                    v.requested_first_purchase_observed,
                    v.first_purchase_orders_observed,
                  ),
                  "currency",
                ],
              ]}
            />
            <Notice>
              Leads gerados, aprovados, CPA e velocidade aprovação → compra
              ainda não estão no contrato certificado. Nenhuma fixture foi
              usada.
            </Notice>
          </>
        )}
      </ReadView>
    </>
  );
}
export function RealCustomers({ metadata }: { metadata: ReadMetadata }) {
  const cursor = useCursor(),
    result = useDashboardRead("customers", metadata, { cursor: cursor.cursor });
  return (
    <>
      <PageHead
        eyebrow="Clientes · Analytics V1"
        title="Compradores observados"
        description="Clientes com compra qualificante no recorte; métricas individuais sobre todo o histórico observado."
      />
      <Notice>
        Busca global, segmentação e influência ainda não estão disponíveis.
        Dados pessoais sensíveis não são projetados.
      </Notice>
      <Panel title="Clientes no recorte">
        <ReadView result={result} metadata={metadata}>
          {(rows) => (
            <RemoteTable
              rows={rows}
              columns={[
                {
                  label: "Cliente",
                  value: (c) => (
                    <Link
                      href={`/customers/${encodeURIComponent(c.customer_id)}`}
                    >
                      {c.name ?? c.customer_id}
                    </Link>
                  ),
                },
                { label: "Tipo", value: (c) => c.customer_type ?? "—" },
                { label: "Estado", value: (c) => c.state ?? "—" },
                { label: "Cidade", value: (c) => c.city ?? "—" },
                {
                  label: "Compras observadas",
                  value: (c) => number(c.purchases_observed),
                },
                {
                  label: "Primeira compra observada",
                  value: (c) => date(c.first_purchase_at_observed),
                },
                {
                  label: "Solicitado · histórico observado",
                  value: (c) => money(c.requested_lifetime_observed, 2),
                },
                {
                  label: "LTV completo",
                  value: (c) => money(c.ltv_complete, 2),
                },
              ]}
              rowKey={(c) => c.customer_id}
              pagination={result.data!.pagination}
              canPrevious={cursor.canPrevious}
              previous={cursor.previous}
              next={() => cursor.next(result.data!.pagination!.cursor)}
            />
          )}
        </ReadView>
      </Panel>
    </>
  );
}
export function RealCustomer({
  metadata,
  id,
}: {
  metadata: ReadMetadata;
  id: string;
}) {
  const result = useDashboardRead("customer", metadata, { customerId: id });
  usePageSource(
    result.isPending ? "loading-real" : "error-real",
    metadata,
    !result.isPending && !result.isError,
  );
  return (
    <>
      <PageHead
        eyebrow="Customer Summary · Analytics V1"
        title="Resumo do cliente"
        description={`Todo o histórico observado disponível até ${metadata.as_of}. O filtro global não limita este resumo.`}
      />
      <ReadView result={result} metadata={metadata} track={false}>
        {(v) => (
          <>
            <Panel title={v.profile.name ?? v.profile.customer_id}>
              <p>
                {v.profile.customer_type ?? "—"} · {v.profile.city ?? "—"} ·{" "}
                {v.profile.state ?? "—"}
              </p>
              <p>
                Primeira compra observada:{" "}
                {date(v.commercial.first_purchase_at_observed)} · Última:{" "}
                {date(v.commercial.last_purchase_at_observed)}
              </p>
            </Panel>
            <Cards
              items={[
                [
                  "Pedidos qualificantes observados",
                  v.commercial.qualifying_orders_observed,
                  "number",
                ],
                [
                  "Receita solicitada observada",
                  v.commercial.requested_revenue_observed,
                  "currency",
                ],
                [
                  "Receita atendida observada",
                  v.commercial.fulfilled_revenue_observed,
                  "currency",
                ],
                ["LTV completo", v.commercial.ltv_complete, "currency"],
              ]}
            />
            <RealCustomerIntelligence metadata={metadata} id={id} />
            <Panel
              title="Pedidos observados do cliente"
              subtitle="Inclui cancelados. Histórico disponível até as_of; atendido não confirma pagamento."
            >
              <OrderList metadata={metadata} customerId={id} />
            </Panel>
          </>
        )}
      </ReadView>
    </>
  );
}
export function RealProducts({ metadata }: { metadata: ReadMetadata }) {
  const cursor = useCursor(),
    result = useDashboardRead("products", metadata, { cursor: cursor.cursor });
  return (
    <>
      <PageHead
        eyebrow="Produtos · Analytics V1"
        title="Desempenho comercial"
        description="Produtos e SKUs resolvidos, sem inferência de identidade por nome."
      />
      <Notice>
        Estoque, grade, cores, tamanhos, ABC, views e compradores únicos ainda
        não são certificados. Nenhum estoque demonstrativo é combinado com estes
        produtos.
      </Notice>
      <Panel title="Produtos no recorte">
        <ReadView result={result} metadata={metadata}>
          {(rows) => (
            <RemoteTable
              rows={rows}
              columns={[
                {
                  label: "Produto",
                  value: (p) => p.name ?? p.sku ?? "Produto não identificado",
                },
                { label: "ID canônico", value: (p) => p.product_id ?? "—" },
                { label: "SKU", value: (p) => p.sku ?? "—" },
                {
                  label: "Solicitado",
                  value: (p) => money(p.requested_revenue, 2),
                },
                {
                  label: "Atendido",
                  value: (p) => money(p.fulfilled_revenue, 2),
                },
                {
                  label: "Unidades solicitadas",
                  value: (p) => metric(p.units_requested, "decimal"),
                },
                {
                  label: "Unidades atendidas",
                  value: (p) => metric(p.units_fulfilled, "decimal"),
                },
                {
                  label: "Pedidos observados",
                  value: (p) => number(p.orders_observed),
                },
                {
                  label: "Compradores únicos",
                  value: (p) => number(p.buyers_unique),
                },
              ]}
              rowKey={(p) => p.product_key}
              pagination={result.data!.pagination}
              canPrevious={cursor.canPrevious}
              previous={cursor.previous}
              next={() => cursor.next(result.data!.pagination!.cursor)}
            />
          )}
        </ReadView>
      </Panel>
    </>
  );
}
export function RealRetention({ metadata }: { metadata: ReadMetadata }) {
  const result = useDashboardRead("retention", metadata);
  return (
    <>
      <PageHead
        eyebrow="Retenção · Analytics V1"
        title="Recompra observada"
        description="Indicadores observados; histórico parcial não confirma retenção desde a origem da marca."
      />
      <ReadView result={result} metadata={metadata}>
        {(v) => (
          <>
            <Cards
              items={[
                ["Compradores", v.buyers_observed, "number"],
                [
                  "Compradores Recorrentes",
                  v.recurring_buyers_observed,
                  "number",
                ],
                [
                  "% de Retenção observada",
                  percentOfRatio(v.retention_observed),
                  "percent",
                ],
                [
                  "Ticket Médio de Retenção observado",
                  v.retention_ticket_observed,
                  "currency",
                ],
                ["Frequência observada", v.frequency_observed, "decimal"],
              ]}
            />
            <Panel
              title="Progressão de compras"
              subtitle="Histórico inteiro da publicação, independente do recorte dos cards."
            >
              <div
                className="purchase-progression"
                style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}
              >
                {v.progression.map((step) => (
                  <div className="purchase-stage" key={step.from_purchase}>
                    <span>
                      Compra {step.from_purchase} → {step.to_purchase}
                    </span>
                    <h3>{number(step.customers_reached_observed)}</h3>
                    <p>
                      {metric(
                        percentOfRatio(step.continuation_observed),
                        "percent",
                        2,
                      )}{" "}
                      seguem
                    </p>
                    <p>
                      Média:{" "}
                      {metric(
                        step.mean_days_observed === null
                          ? null
                          : String(step.mean_days_observed),
                        "days",
                      )}
                    </p>
                    <p>
                      Mediana:{" "}
                      {metric(
                        step.median_days_observed === null
                          ? null
                          : String(step.median_days_observed),
                        "days",
                      )}
                    </p>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel
              title="Retenção por janela"
              subtitle="Cohorts da publicação. Traço indica período sem maturidade certificada."
            >
              <CohortMatrix cohorts={v.cohorts} />
            </Panel>
            <Notice>
              Série diária de retenção não está disponível neste contrato.
            </Notice>
          </>
        )}
      </ReadView>
    </>
  );
}
function CohortMatrix({
  cohorts,
}: {
  cohorts: ReadResourceMap["retention"]["cohorts"];
}) {
  const months = [...new Set(cohorts.map((c) => c.month))]
      .filter((n): n is number => n !== null)
      .sort((a, b) => a - b),
    groups = [...new Set(cohorts.map((c) => c.cohort_month))].sort();
  return (
    <Table className="retention-matrix">
      <TableHeader>
        <TableRow>
          <TableHead>Primeira compra observada</TableHead>
          {months.map((m) => (
            <TableHead key={m}>Mês {m}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map((group) => (
          <TableRow key={group}>
            <TableCell>{date(group)}</TableCell>
            {months.map((m) => {
              const cell = cohorts.find(
                (c) => c.cohort_month === group && c.month === m,
              );
              const rate = cell?.period_complete ? cell.observed_rate : null;
              return (
                <TableCell key={m}>
                  <div
                    className={
                      rate === null || rate === undefined
                        ? "cohort-unknown"
                        : m === 0
                          ? "cohort-base"
                          : "cohort-rate"
                    }
                    style={
                      rate !== null && rate !== undefined && m > 0
                        ? {
                            backgroundColor: `hsl(${Math.min(Number(rate) / 0.3, 1) * 155} 42% 24%)`,
                          }
                        : undefined
                    }
                  >
                    {rate === undefined
                      ? "—"
                      : metric(percentOfRatio(rate), "percent", 1)}
                  </div>
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
export function RealGeography({ metadata }: { metadata: ReadMetadata }) {
  const result = useDashboardRead("geography", metadata);
  const blocked =
    result.error instanceof ApiError && result.error.status === 424;
  usePageSource(
    result.isPending
      ? "loading-real"
      : blocked
        ? "unavailable-real"
        : "error-real",
    metadata,
  );
  const map = BrazilMap as {
    viewBox: string;
    locations: { id: string; name: string; path: string }[];
  };
  return (
    <>
      <PageHead
        eyebrow="Inteligência geográfica"
        title="Seu negócio, em todo o Brasil."
        description="Mapa preservado; nenhuma localização foi inferida."
      />
      <Panel title="Distribuição por estado">
        <div className="geo-layout">
          <svg
            className="brazil-map"
            viewBox={map.viewBox}
            aria-label="Mapa do Brasil sem cobertura certificada"
          >
            {map.locations.map((s) => (
              <path
                key={s.id}
                d={s.path}
                fill="var(--surface-2)"
                stroke="var(--line-hi)"
              >
                <title>{s.name} · Sem cobertura</title>
              </path>
            ))}
          </svg>
          <div>
            {result.isPending ? (
              <Loading />
            ) : blocked ? (
              <Notice>
                Cobertura geográfica ainda não certificada para esta publicação.
              </Notice>
            ) : (
              <Failure retry={() => void result.refetch()} />
            )}
          </div>
        </div>
      </Panel>
    </>
  );
}
export function RealPerformance({ metadata }: { metadata: ReadMetadata }) {
  return <RealIntelligencePerformance metadata={metadata} />;
}
export function RealFunnel({ metadata }: { metadata: ReadMetadata }) {
  const result = useDashboardRead("funnel", metadata);
  return (
    <>
      <PageHead
        eyebrow="Funil · Analytics V1"
        title="Conversão observada"
        description="Eventos de navegação não representam pedidos financeiros."
      />
      <ReadView result={result} metadata={metadata}>
        {(v) => (
          <>
            <Cards
              items={Object.entries(v.totals).map(([key, value]) => [
                key,
                value,
                "number",
              ])}
            />
            <Cards
              items={[
                [
                  "Sessão → Carrinho",
                  percentOfRatio(v.session_to_cart_rate),
                  "percent",
                ],
                [
                  "Carrinho → Checkout",
                  percentOfRatio(v.cart_to_checkout_rate),
                  "percent",
                ],
                [
                  "Checkout → Purchase",
                  percentOfRatio(v.checkout_to_purchase_rate),
                  "percent",
                ],
              ]}
            />
          </>
        )}
      </ReadView>
    </>
  );
}
