"use client";
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useDashboardRead, usePageSource } from "@/hooks/use-dashboard-read";
import type {
  ReadMetadata,
  ReadResourceMap,
  ReadPagination,
} from "@/services/api/http";
import type {
  IntelligenceResource,
  IntelligenceRow,
} from "@/services/api/intelligence";
import { ApiError } from "@/services/api/access";
import { Cards, RemoteTable } from "./read-components";
import { PageHead, Panel, Notice, Loading, Failure } from "@/components/ui-kit";
import { money, date } from "@/lib/format";
import type { Metric } from "@/types/domain";
const participation =
  "Participação na jornada, sem atribuição exclusiva. Não some receita entre campanhas. Atendido não confirma pagamento.";
const text = (r: IntelligenceRow, k: string) =>
  typeof r[k] === "string"
    ? String(r[k])
    : typeof r[k] === "number"
      ? String(r[k])
      : "—";
const value = (r: IntelligenceRow, k: string) =>
  typeof r[k] === "string" || typeof r[k] === "number"
    ? (r[k] as string | number)
    : null;
const flag = (r: IntelligenceRow, k: string) =>
  r[k] === null || r[k] === undefined
    ? "Indisponível"
    : r[k] === true
      ? "Sim, observado"
      : "Não observado";
function Read<K extends IntelligenceResource>({
  resource,
  metadata,
  entity,
  cursor,
  track = true,
  children,
}: {
  resource: K;
  metadata: ReadMetadata;
  entity?: string;
  cursor?: string;
  track?: boolean;
  children: (
    data: ReadResourceMap[K],
    metadata: ReadMetadata,
    pagination: ReadPagination | null,
  ) => ReactNode;
}) {
  const result = useDashboardRead(resource, metadata, {
    customerId: entity,
    cursor,
  });
  const current = result.data?.metadata ?? metadata;
  const source = result.isPending
    ? "loading-real"
    : result.error instanceof ApiError && result.error.status === 424
      ? "unavailable-real"
      : result.isError
        ? "error-real"
        : !current.history_complete ||
            current.influence_complete === false ||
            current.meta_complete === false
          ? "partial-real"
          : "real";
  // Nested lists share the parent's generation; only the page root owns source state.
  return (
    <ReadState source={source} metadata={current} track={track}>
      {result.isPending ? (
        <Loading />
      ) : result.error instanceof ApiError && result.error.status === 424 ? (
        <Notice>
          Performance e influência aguardam materialização das camadas de mídia.
        </Notice>
      ) : result.isError || !result.data ? (
        <Failure retry={() => void result.refetch()} />
      ) : (
        children(result.data.data, current, result.data.pagination)
      )}
    </ReadState>
  );
}
function ReadState({
  source,
  metadata,
  track,
  children,
}: {
  source:
    | "loading-real"
    | "unavailable-real"
    | "error-real"
    | "partial-real"
    | "real";
  metadata: ReadMetadata;
  track: boolean;
  children: ReactNode;
}) {
  return track ? (
    <PageSource source={source} metadata={metadata}>
      {children}
    </PageSource>
  ) : (
    children
  );
}
function PageSource({
  source,
  metadata,
  children,
}: {
  source:
    | "loading-real"
    | "unavailable-real"
    | "error-real"
    | "partial-real"
    | "real";
  metadata: ReadMetadata;
  children: ReactNode;
}) {
  usePageSource(source, metadata);
  return children;
}
const performanceCards: [string, string, Metric["format"]][] = [
  ["Investimento Meta", "meta_spend", "currency"],
  ["Clientes influenciados", "influenced_customers", "number"],
  ["Pedidos influenciados", "influenced_orders", "number"],
  [
    "Receita Solicitada Influenciada",
    "requested_revenue_influenced",
    "currency",
  ],
  ["Receita Atendida Influenciada", "fulfilled_revenue_influenced", "currency"],
  ["ROAS Solicitado Influenciado", "roas_requested", "ratio"],
  ["ROAS Atendido Influenciado", "roas_fulfilled", "ratio"],
  ["Novos Confirmados Influenciados", "new_customers_influenced", "number"],
  ["CAC", "cac_new_customer", "currency"],
];
const campaignCards: [string, string, Metric["format"]][] = [
  ["Investimento", "spend", "currency"],
  ["Impressões", "impressions", "number"],
  ["Cliques", "clicks", "number"],
  ["CTR", "ctr", "percent"],
  ["CPC", "cpc", "currency"],
  ["CPM", "cpm", "currency"],
  ["Clientes influenciados", "influenced_customers", "number"],
  ["Pedidos influenciados", "influenced_orders", "number"],
  ["Solicitado influenciado", "requested_revenue_influenced", "currency"],
  ["Atendido influenciado", "fulfilled_revenue_influenced", "currency"],
  ["ROAS solicitado", "roas_requested", "ratio"],
  ["ROAS atendido", "roas_fulfilled", "ratio"],
];
export function RealIntelligencePerformance({
  metadata,
}: {
  metadata: ReadMetadata;
}) {
  return (
    <>
      <PageHead
        eyebrow="Performance"
        title="Mídia e influência"
        description={participation}
      />
      <Link href="/media" className="back-link">
        Clientes, pedidos e campanhas participantes
      </Link>
      <Panel title="Performance e influência">
        <Read resource="performance" metadata={metadata}>
          {(r, m) => (
            <>
              <Cards
                items={performanceCards.map(([label, key, format]) => [
                  label,
                  value(r, key),
                  format,
                  participation,
                ])}
              />
              <Notice>
                Spend observado:{" "}
                {money(
                  typeof r.observed_meta_spend === "string"
                    ? r.observed_meta_spend
                    : null,
                  2,
                )}
                . Histórico parcial mantém CAC e novos confirmados
                indisponíveis.
              </Notice>
              <RealIntelligenceList
                key={`${m.publication_id}/customers`}
                resource="influencedCustomers"
                metadata={m}
                title="Clientes influenciados"
              />
              <RealIntelligenceList
                key={`${m.publication_id}/orders`}
                resource="influencedOrders"
                metadata={m}
                title="Pedidos influenciados"
              />
              <RealIntelligenceList
                key={`${m.publication_id}/campaigns`}
                resource="campaigns"
                metadata={m}
                title="Campanhas participantes"
              />
            </>
          )}
        </Read>
      </Panel>
    </>
  );
}
export function RealCustomerIntelligence({
  metadata,
  id,
}: {
  metadata: ReadMetadata;
  id: string;
}) {
  return (
    <Read resource="customer360" metadata={metadata} entity={id}>
      {(r, m) => (
        <>
          <Panel title="Customer 360">
            <Cards
              items={[
                [
                  "Compras observadas",
                  value(r.profile, "purchase_count"),
                  "number",
                ],
                [
                  "Frequência observada",
                  value(r.profile, "purchase_count"),
                  "number",
                ],
                ["LTV observado", value(r.profile, "ltv_observed"), "currency"],
                ["LTV completo", r.ltv_complete, "currency"],
              ]}
            />
            <p>
              Recompra: {flag(r.profile, "has_repurchase")} · Última compra
              observada:{" "}
              {date(
                typeof r.profile.last_purchase_at === "string"
                  ? r.profile.last_purchase_at
                  : null,
              )}
            </p>
            <Notice>
              Health score e segmentação: NOT_DEFINED. Nenhum pagamento é
              inferido.
            </Notice>
          </Panel>
          <Panel title="Marketing Influence" subtitle={participation}>
            <div className="metrics">
              {r.marketing.map((row) => (
                <Panel
                  key={text(row, "influence_scope")}
                  title={text(row, "influence_scope")}
                >
                  <p>Influenciado: {flag(row, "paid_media_influenced")}</p>
                  <p>Campanhas participantes: {text(row, "campaign_count")}</p>
                  <p>
                    Primeira campanha:{" "}
                    {typeof row.first_campaign_id === "string" ? (
                      <Link
                        href={`/campaigns/${encodeURIComponent(row.first_campaign_id)}`}
                      >
                        {row.first_campaign_id}
                      </Link>
                    ) : (
                      "Indisponível"
                    )}{" "}
                    · Última campanha:{" "}
                    {typeof row.last_campaign_id === "string" ? (
                      <Link
                        href={`/campaigns/${encodeURIComponent(row.last_campaign_id)}`}
                      >
                        {row.last_campaign_id}
                      </Link>
                    ) : (
                      "Indisponível"
                    )}
                  </p>
                  <p>Contatos comprovados: {text(row, "paid_touch_count")}</p>
                  <p>
                    Primeiro: {text(row, "first_paid_touch_at")} · Último:{" "}
                    {text(row, "last_paid_touch_at")}
                  </p>
                </Panel>
              ))}
            </div>
          </Panel>
          <RealIntelligenceList
            resource="customerProducts"
            metadata={m}
            entity={id}
            title="Produtos do cliente"
          />
          <RealIntelligenceList
            resource="timeline"
            metadata={m}
            entity={id}
            title="Timeline do cliente"
          />
        </>
      )}
    </Read>
  );
}
export function RealCampaigns({
  metadata,
  id,
}: {
  metadata: ReadMetadata;
  id?: string;
}) {
  return (
    <>
      <PageHead
        eyebrow="Meta Ads · materializado"
        title={id ? "Campanha participante" : "Campanhas Meta"}
        description={participation}
      />
      {id ? (
        <Read resource="campaign" metadata={metadata} entity={id}>
          {(rows, m) => (
            <>
              <Panel
                title={rows[0] ? text(rows[0], "campaign_name") : "Campanha"}
              >
                <p>
                  Status: {rows[0] ? text(rows[0], "campaign_status") : "—"}
                </p>
                {rows[0] && (
                  <Cards
                    items={campaignCards.map(([label, key, format]) => [
                      label,
                      value(rows[0], key),
                      format,
                      participation,
                    ])}
                  />
                )}
              </Panel>
              <RealIntelligenceList
                resource="campaignCustomers"
                metadata={m}
                entity={id}
                title="Clientes participantes"
              />
              <RealIntelligenceList
                resource="campaignOrders"
                metadata={m}
                entity={id}
                title="Pedidos participantes"
              />
            </>
          )}
        </Read>
      ) : (
        <RealIntelligenceList
          resource="campaigns"
          metadata={metadata}
          title="Campanhas no recorte"
          track
        />
      )}
    </>
  );
}
export function RealIntelligenceList({
  resource,
  metadata,
  entity,
  title,
  track = false,
}: {
  resource: Exclude<IntelligenceResource, "performance" | "customer360">;
  metadata: ReadMetadata;
  entity?: string;
  title: string;
  track?: boolean;
}) {
  const [stack, setStack] = useState<(string | undefined)[]>([undefined]);
  const columns =
    resource === "timeline"
      ? [
          "event_name",
          "occurred_at",
          "record_type",
          "campaign_id",
          "order_id",
          "value",
        ]
      : resource === "customerProducts"
        ? [
            "product_key",
            "product_id",
            "sku",
            "orders_count",
            "requested_quantity",
            "fulfilled_quantity",
            "requested_revenue",
            "fulfilled_revenue",
          ]
        : resource === "campaigns" || resource === "campaign"
          ? [
              "campaign_name",
              "campaign_status",
              "spend",
              "impressions",
              "clicks",
              "ctr",
              "cpc",
              "cpm",
              "influenced_customers",
              "influenced_orders",
              "requested_revenue_influenced",
              "fulfilled_revenue_influenced",
              "roas_requested",
              "roas_fulfilled",
            ]
          : resource === "influencedCustomers"
            ? [
                "customer_id",
                "influence_scope",
                "paid_touch_count",
                "campaign_count",
                "first_paid_touch_at",
                "last_paid_touch_at",
              ]
            : resource === "campaignCustomers"
              ? [
                  "customer_id",
                  "orders_influenced",
                  "requested_revenue",
                  "fulfilled_revenue",
                ]
              : [
                  "order_id",
                  "customer_id",
                  "order_status",
                  "requested_total",
                  "fulfilled_total",
                  "requested_items_qty",
                  "fulfilled_items_qty",
                  "campaign_count",
                ];
  return (
    <Panel title={title} subtitle={participation}>
      <Read
        resource={resource}
        metadata={metadata}
        entity={entity}
        cursor={stack.at(-1)}
        track={track}
      >
        {(rows, _m, pagination) => (
          <RemoteTable
            rows={rows}
            columns={columns.map((k) => ({
              label: k.replaceAll("_", " "),
              value: (r: IntelligenceRow) =>
                k === "customer_id" && typeof r.customer_id === "string" ? (
                  <Link
                    href={`/customers/${encodeURIComponent(r.customer_id)}`}
                  >
                    {r.customer_id}
                  </Link>
                ) : k === "campaign_name" &&
                  typeof r.campaign_id === "string" ? (
                  <Link
                    href={`/campaigns/${encodeURIComponent(r.campaign_id)}`}
                  >
                    {text(r, k)}
                  </Link>
                ) : (
                  text(r, k)
                ),
            }))}
            pagination={pagination}
            previous={() => setStack((s) => s.slice(0, -1))}
            next={() => {
              if (pagination?.cursor)
                setStack((s) => [...s, pagination.cursor!]);
            }}
            canPrevious={stack.length > 1}
            rowKey={(r) =>
              typeof r.record_key === "string"
                ? r.record_key
                : JSON.stringify([
                    r.customer_id,
                    r.order_id,
                    r.campaign_id,
                    r.product_key,
                    r.occurred_at,
                    r.event_name,
                  ])
            }
          />
        )}
      </Read>
    </Panel>
  );
}
