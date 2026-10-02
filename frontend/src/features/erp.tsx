"use client";
import { ListExport } from "@/components/exports";
import { useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import type { Metric } from "@/types/domain";
import type {
  ErpData,
  ErpOrderRow,
  ErpCustomerRow,
  ErpProductRow,
  ErpProductVariant,
  Breakdown,
} from "@/types/erp";
import { useResource, useRequestContext } from "@/hooks/use-resource";
import {
  Panel,
  PageHead,
  MetricCard,
  Loading,
  Failure,
  Notice,
  Choice,
} from "@/components/ui-kit";
import { DataTable } from "@/components/data-table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { money, number, date, metric } from "@/lib/format";
import { dateRange } from "@/lib/period";
import { filterProducts } from "@/lib/erp";
import type { ExportColumn } from "@/lib/erp-export";
const ErpTrend = dynamic(
  () => import("@/components/erp-charts").then((m) => m.ErpTrend),
  { ssr: false },
);
const ErpBreakdown = dynamic(
  () => import("@/components/erp-charts").then((m) => m.ErpBreakdown),
  { ssr: false },
);
const pct = (n: number | null) =>
  metric(n === null ? null : String(n), "percent");
const m = (
  label: string,
  value: number | null,
  format: Metric["format"] = "number",
  hint = "Base demonstrativa do ERP no período selecionado",
): Metric => ({
  label,
  value: value === null ? null : String(value),
  format,
  hint,
});
const col = <T,>(
  accessorKey: keyof T,
  header: string,
  format?: (value: never) => string,
): ColumnDef<T> => ({
  accessorKey: accessorKey as string,
  header,
  ...(format ? { cell: (c) => format(c.getValue() as never) } : {}),
});
function Metrics({ items }: { items: Metric[] }) {
  return (
    <section className="metrics" aria-label="Indicadores ERP">
      {items.map((item) => (
        <MetricCard key={item.label} item={item} />
      ))}
    </section>
  );
}
function Export<T>({
  name,
  rows,
  columns,
  csv = false,
}: {
  name: string;
  rows: T[];
  columns: ExportColumn<T>[];
  csv?: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(false);
  const context = useRequestContext();
  return (
    <div>
      <Button
        className="btn btn--glass"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(false);
          try {
            const { exportErp } = await import("@/lib/erp-export");
            const { from, to } = dateRange(context.filters);
            await exportErp(
              `${name}-${context.scope.store_id}-${from}-${to}.${csv ? "csv" : "xlsx"}`,
              rows,
              columns,
              csv,
            );
          } catch {
            setError(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Exportando…" : `Exportar ${csv ? "CSV" : "XLSX"}`}
      </Button>
      {error && <p role="alert">Não foi possível exportar. Tente novamente.</p>}
    </div>
  );
}
function BreakdownPanel({
  title,
  rows,
  currency = true,
}: {
  title: string;
  rows: { label: string; value: number }[];
  currency?: boolean;
}) {
  return (
    <Panel title={title} action={<ListExport rows={rows} name="ranking-erp" />}>
      {rows.length ? (
        <ErpBreakdown data={rows} currency={currency} />
      ) : (
        <p className="muted">Sem registros no período.</p>
      )}
    </Panel>
  );
}
const orderExports: ExportColumn<ErpOrderRow>[] = [
  ...(
    [
      ["id", "Pedido"],
      ["createdAt", "Data"],
      ["customerName", "Cliente"],
      ["document", "Documento"],
      ["store", "Loja"],
      ["seller", "Vendedor"],
      ["status", "Status"],
      ["paymentMethod", "Pagamento"],
      ["channel", "Canal"],
      ["requestedQuantity", "Quantidade"],
      ["grossAmount", "Bruto"],
      ["discountAmount", "Desconto"],
      ["returnAmount", "Devolução"],
      ["netAmount", "Líquido"],
      ["utmSource", "Origem"],
      ["utmCampaign", "Campanha"],
    ] as const
  ).map(([key, header]) => ({ header, value: (r: ErpOrderRow) => r[key] })),
];
const orderColumns: ColumnDef<ErpOrderRow>[] = [
  {
    id: "details",
    header: "Pedido",
    cell: ({ row }) => (
      <button
        className="text-blue-300"
        aria-label={`Itens do pedido ${row.original.id}`}
        aria-expanded={row.getIsExpanded()}
        onClick={row.getToggleExpandedHandler()}
      >
        {row.getIsExpanded() ? "−" : "+"} {row.original.id}
      </button>
    ),
  },
  col("createdAt", "Data", date),
  col("customerName", "Cliente"),
  col("document", "Documento"),
  col("store", "Loja"),
  col("seller", "Vendedor"),
  col("status", "Status"),
  col("paymentMethod", "Pagamento"),
  col("channel", "Canal"),
  {
    id: "origin",
    header: "Origem",
    cell: ({ row }) =>
      row.original.attributed
        ? "Meta · influência demonstrativa"
        : "Direto / não identificado",
  },
  col("requestedQuantity", "Peças", number),
  col("grossAmount", "Bruto", money),
  col("netAmount", "Líquido", money),
];
function OrderItems({ order }: { order: ErpOrderRow }) {
  return (
    <section aria-label={`Itens ${order.id}`} className="p-4">
      <p className="metric-hint mb-3">
        Descontos {money(order.discountAmount)} · Devolução{" "}
        {money(order.returnAmount)} ({order.returnedQuantity} peças) · Frete{" "}
        {money(order.freightAmount)}. Itens líquidos antes da devolução do
        pedido.
      </p>
      <DataTable<ErpOrderRow["items"][number]>
        data={order.items}
        pageSize={20}
        columns={[
          col("sku", "SKU"),
          col("name", "Produto"),
          col("category", "Categoria"),
          col("color", "Cor"),
          col("size", "Tamanho"),
          col("quantity", "Quantidade", number),
          col("unitPrice", "Preço", money),
          col("costPrice", "Custo", money),
          col("discountAmount", "Desconto", money),
          col("netAmount", "Líquido", money),
        ]}
      />
    </section>
  );
}
type CompareErp = (select: (data: ErpData) => Metric[]) => Metric[];
function Overview({ data, compare }: { data: ErpData; compare: CompareErp }) {
  const b = data.dashboard.breakdowns;
  return (
    <>
      <Metrics
        items={compare((data) => {
          const k = data.dashboard.kpis;
          return [
            m(
              "Faturamento líquido",
              k.netRevenue,
              "currency",
              `Bruto: ${money(k.grossRevenue)}`,
            ),
            m(
              "Pedidos",
              k.orders,
              "number",
              `Ticket médio: ${money(k.avgTicket)}`,
            ),
            m(
              "Compradores",
              k.uniqueCustomers,
              "number",
              `Recorrentes: ${k.returningCustomers}`,
            ),
            m(
              "Retenção",
              k.retentionPct,
              "percent",
              "Recorrentes observados / compradores. Novos históricos não confirmados.",
            ),
            m(
              "Peças vendidas",
              k.totalQuantity,
              "number",
              `Média por pedido: ${k.avgItemsPerOrder.toFixed(1)}`,
            ),
            m(
              "Descontos",
              k.discountAmount,
              "currency",
              `${pct(k.discountRatePct)} do bruto`,
            ),
            m(
              "Devoluções",
              k.returnAmount,
              "currency",
              `${pct(k.returnRatePct)} do bruto · ${k.returnedQuantity} peças`,
            ),
            m(
              "Cancelamentos",
              k.cancelledOrders,
              "number",
              `Valor: ${money(k.cancelledAmount)}`,
            ),
          ];
        })}
      />
      <div className="erp-two">
        <Panel
          title="Faturamento e pedidos"
          subtitle="Evolução diária do ERP no período"
        >
          <ErpTrend
            data={data.dashboard.revenueOverTime.map((p, i) => ({
              date: p.date,
              primary: p.value,
              secondary: data.dashboard.ordersOverTime[i].value,
            }))}
          />
        </Panel>
        <Panel
          title="Novos vs. recorrentes"
          subtitle="Primeira compra observada; aquisição histórica não confirmada"
        >
          <ErpTrend
            customers
            data={data.dashboard.newCustomersOverTime.map((p, i) => ({
              date: p.date,
              primary: p.value,
              secondary: data.dashboard.returningCustomersOverTime[i].value,
            }))}
          />
        </Panel>
      </div>
      <div className="erp-three">
        {(
          [
            ["Formas de pagamento", b.payments],
            ["Ranking de vendedores", b.sellers],
            ["Geografia de compradores", b.states],
          ] as const
        ).map(([title, rows]) => (
          <BreakdownPanel
            key={title}
            title={title}
            rows={rows.map((r) => ({ label: r.label, value: r.revenue }))}
          />
        ))}
      </div>
      <Panel
        title="Participação de mídia"
        subtitle="Sinal demonstrativo de influência; não atribuição exclusiva"
      >
        <dl className="erp-stats">
          <div>
            Clientes influenciados
            <strong>{data.dashboard.attribution.attributedCustomers}</strong>
          </div>
          <div>
            Sem influência identificada
            <strong>{data.dashboard.attribution.unattributedCustomers}</strong>
          </div>
          <div>
            Receita influenciada
            <strong>
              {money(data.dashboard.attribution.attributedRevenue)}
            </strong>
          </div>
          <div>
            Receita sem influência identificada
            <strong>
              {money(data.dashboard.attribution.unattributedRevenue)}
            </strong>
          </div>
        </dl>
      </Panel>
      <Panel title="Produtos com maior faturamento">
        <DataTable
          data={data.products.rows.slice(0, 8)}
          columns={productColumns(true)}
          pageSize={8}
        />
      </Panel>
    </>
  );
}
function Orders({ data, compare }: { data: ErpData; compare: CompareErp }) {
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState("all");
  const rows = data.orders.filter(
    (o) =>
      (status === "all" || o.status === status) &&
      `${o.id} ${o.customerName} ${o.document}`
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
  );
  return (
    <>
      <Metrics
        items={compare((data) => {
          const k = data.dashboard.kpis;
          return [
            m(
              "Faturamento bruto",
              k.grossRevenue,
              "currency",
              `Líquido: ${money(k.netRevenue)}`,
            ),
            m(
              "Pedidos únicos",
              data.orders.length,
              "number",
              `Ticket médio: ${money(k.avgTicket)}`,
            ),
            m(
              "Peças vendidas",
              k.totalQuantity,
              "number",
              `Devolvidas: ${k.returnedQuantity}`,
            ),
            m(
              "Cancelamentos",
              k.cancelledOrders,
              "number",
              `Valor: ${money(k.cancelledAmount)}`,
            ),
          ];
        })}
      />
      <Panel
        title="Pedidos do ERP"
        action={
          <Export name="pedidos-erp" rows={rows} columns={orderExports} />
        }
      >
        <div className="erp-filters">
          <Input
            aria-label="Buscar pedido ERP"
            placeholder="Buscar pedido, cliente ou documento"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Choice
            label="Status ERP"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "Todos os status" },
              ...Array.from(new Set(data.orders.map((o) => o.status!))).map(
                (value) => ({ value, label: value }),
              ),
            ]}
          />
        </div>
        <DataTable
          key={`${search}-${status}`}
          data={rows}
          columns={orderColumns}
          pageSize={20}
          renderExpanded={(order) => <OrderItems order={order} />}
        />
      </Panel>
    </>
  );
}
function Customers({ data, compare }: { data: ErpData; compare: CompareErp }) {
  const [search, setSearch] = useState(""),
    [type, setType] = useState("all"),
    [selected, setSelected] = useState<ErpCustomerRow | null>(null);
  const rows = data.customers.filter(
    (c) =>
      (type === "all" || c.buyerType === type) &&
      `${c.name} ${c.document} ${c.email}`
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
  );
  const exports: ExportColumn<ErpCustomerRow>[] = (
    [
      "name",
      "document",
      "email",
      "phone",
      "city",
      "state",
      "seller",
      "buyerType",
      "segment",
      "orders",
      "totalSpent",
      "historicalOrders",
      "lifetimeValue",
      "observedLifetimeValue",
      "lastOrderAt",
    ] as const
  ).map((key, i) => ({
    header: [
      "Cliente",
      "Documento",
      "E-mail",
      "Telefone",
      "Cidade",
      "UF",
      "Vendedor",
      "Tipo observado",
      "Segmento",
      "Pedidos no período",
      "Comprado no período",
      "Pedidos históricos observados",
      "LTV confirmado",
      "Valor histórico observado",
      "Último pedido",
    ][i],
    value: (r) => r[key],
  }));
  return (
    <>
      <Metrics
        items={compare((data) => {
          const k = data.dashboard.kpis;
          return [
            m("Compradores", k.uniqueCustomers),
            m(
              "Novos compradores",
              null,
              "number",
              "Histórico completo não confirmado",
            ),
            m("Recorrentes", k.returningCustomers),
            m("Retenção", k.retentionPct, "percent"),
          ];
        })}
      />
      <Panel
        title="Base de compradores"
        action={<Export name="clientes-erp" rows={rows} columns={exports} />}
      >
        <div className="erp-filters">
          <Input
            aria-label="Buscar cliente ERP"
            placeholder="Buscar cliente, documento ou e-mail"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Choice
            label="Tipo de comprador ERP"
            value={type}
            onChange={setType}
            options={[
              { value: "all", label: "Todos os compradores" },
              { value: "NEW", label: "Primeira compra observada" },
              { value: "RETURNING", label: "Recorrentes" },
            ]}
          />
        </div>
        <DataTable<ErpCustomerRow>
          key={`${search}-${type}`}
          data={rows}
          pageSize={20}
          columns={[
            {
              id: "customer",
              header: "Cliente",
              cell: ({ row }) => (
                <button
                  className="text-blue-300"
                  onClick={() => setSelected(row.original)}
                >
                  {row.original.name}
                </button>
              ),
            },
            col("document", "Documento"),
            col("city", "Cidade"),
            col("state", "UF"),
            {
              accessorKey: "buyerType",
              header: "Tipo",
              cell: (c) =>
                c.getValue() === "NEW" ? "Primeira observada" : "Recorrente",
            },
            col("segment", "Segmento"),
            col("seller", "Vendedor"),
            col("orders", "Pedidos período", number),
            col("totalSpent", "Valor período", money),
            col("historicalOrders", "Pedidos históricos", number),
            col("lifetimeValue", "LTV", money),
            col("observedLifetimeValue", "Valor observado", money),
            col("lastOrderAt", "Última compra", date),
            col("utmSource", "Origem"),
          ]}
        />
      </Panel>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
      >
        <DialogContent className="glass erp-dialog">
          <DialogTitle>Histórico de pedidos</DialogTitle>
          <DialogDescription>
            {selected?.name} · {selected?.document} · Todo o histórico observado
            até o fim do período
          </DialogDescription>
          {selected && (
            <>
              <dl className="erp-stats">
                <div>
                  Pedidos históricos<strong>{selected.historicalOrders}</strong>
                </div>
                <div>
                  Valor observado
                  <strong>{money(selected.observedLifetimeValue)}</strong>
                </div>
                <div>
                  Ticket histórico
                  <strong>
                    {money(
                      selected.observedLifetimeValue /
                        selected.historicalOrders,
                    )}
                  </strong>
                </div>
              </dl>
              <p className="metric-hint">
                LTV definitivo não confirmado. Contatos fictícios:{" "}
                {selected.email} · {selected.phone}.
              </p>
              <DataTable
                data={data.history.filter((o) => o.customerId === selected.id)}
                columns={orderColumns}
                pageSize={20}
                renderExpanded={(order) => <OrderItems order={order} />}
              />
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
function Coverage({ value }: { value: number | null }) {
  return (
    <span
      className={`badge ${value === null ? "" : value <= 15 ? "text-red-300" : value <= 60 ? "text-emerald-300" : "text-amber-300"}`}
    >
      {value === null ? "Sem vendas" : `${Math.round(value)} dias`}
    </span>
  );
}
function productColumns(
  stock: boolean,
  expand = false,
): ColumnDef<ErpProductRow>[] {
  return [
    expand
      ? {
          id: "name",
          header: "Produto",
          cell: ({ row }) => (
            <button
              className="text-blue-300"
              aria-label={`Variantes de ${row.original.name}`}
              aria-expanded={row.getIsExpanded()}
              onClick={row.getToggleExpandedHandler()}
            >
              {row.getIsExpanded() ? "−" : "+"} {row.original.name}
            </button>
          ),
        }
      : col("name", "Produto"),
    col("category", "Categoria"),
    col("variantCount", "SKUs", number),
    col("units", "Vendidas", number),
    col("revenue", "Faturamento", money),
    stock
      ? col("grossMarginPct", "Margem", pct)
      : {
          accessorKey: "coverageDays",
          header: "Dias restantes",
          cell: (c) => <Coverage value={c.getValue<number | null>()} />,
        },
    col("turnoverPct", "Giro", pct),
    ...(stock
      ? [
          {
            accessorKey: "coverageDays",
            header: "Cobertura",
            cell: (c) => <Coverage value={c.getValue<number | null>()} />,
          } satisfies ColumnDef<ErpProductRow>,
        ]
      : []),
    col("stock", "Estoque", number),
    col("salesPower", "Poder de venda", money),
  ];
}
function Variants({ product }: { product: ErpProductRow }) {
  return (
    <section className="p-4" aria-label={`Grade ${product.name}`}>
      <DataTable<ErpProductVariant>
        data={product.variants}
        pageSize={20}
        columns={[
          col("sku", "SKU"),
          col("color", "Cor"),
          col("size", "Tamanho"),
          col("units", "Vendidas", number),
          col("revenue", "Receita", money),
          col("averagePrice", "Preço médio", money),
          col("grossMarginPct", "Margem", pct),
          col("turnoverPct", "Giro", pct),
          {
            accessorKey: "coverageDays",
            header: "Cobertura",
            cell: (c) => <Coverage value={c.getValue<number | null>()} />,
          },
          col("stock", "Estoque", number),
          col("salesPower", "Poder de venda", money),
        ]}
      />
    </section>
  );
}
function Products({
  data,
  stock = false,
  compare,
}: {
  data: ErpData;
  stock?: boolean;
  compare: CompareErp;
}) {
  const [search, setSearch] = useState(""),
    [category, setCategory] = useState("all"),
    [inventory, setInventory] = useState(stock ? "in_stock" : "all"),
    [sort, setSort] = useState(stock ? "sales_power" : "revenue");
  const d = data.products;
  const rows = filterProducts(d.rows, search, category, inventory, sort);
  const variants = rows.flatMap((p) =>
    p.variants.map((v) => ({ ...v, product: p.name, category: p.category })),
  );
  const exports: ExportColumn<
    ErpProductVariant & { product: string | null; category: string | null }
  >[] = (
    [
      "product",
      "category",
      "sku",
      "color",
      "size",
      "units",
      "revenue",
      "averagePrice",
      "catalogPrice",
      "costAmount",
      "grossProfit",
      "grossMarginPct",
      "turnoverPct",
      "coverageDays",
      "stock",
      "salesPower",
    ] as const
  ).map((key, i) => ({
    header: [
      "Produto",
      "Categoria",
      "SKU",
      "Cor",
      "Tamanho",
      "Vendidas",
      "Receita",
      "Preço médio",
      "Preço catálogo",
      "Custo",
      "Lucro bruto",
      "Margem %",
      "Giro %",
      "Cobertura dias",
      "Estoque",
      "Poder de venda",
    ][i],
    value: (r) => r[key],
  }));
  return (
    <>
      <Metrics
        items={compare((data) => {
          const d = data.products;
          return (
            stock
              ? [
                  m(
                    "Estoque atual",
                    d.totalStock,
                    "number",
                    `${d.totalSkus} SKUs · ${d.total} produtos`,
                  ),
                  m(
                    "Poder de venda",
                    d.salesPower,
                    "currency",
                    "Estoque positivo × preço de catálogo",
                  ),
                  m(
                    "Cobertura",
                    d.coverageDays,
                    "days",
                    `Giro: ${pct(d.turnoverPct)}`,
                  ),
                  m(
                    "SKUs sem estoque",
                    d.outOfStockCount,
                    "number",
                    `Negativos: ${d.negativeStockCount}`,
                  ),
                ]
              : [
                  m(
                    "Faturamento",
                    d.totalRevenue,
                    "currency",
                    `${d.totalUnits} peças`,
                  ),
                  m(
                    "Lucro bruto",
                    d.grossProfit,
                    "currency",
                    `Margem: ${pct(d.grossMarginPct)}`,
                  ),
                  m(
                    "% de giro",
                    d.turnoverPct,
                    "percent",
                    `Cobertura: ${d.coverageDays === null ? "Sem vendas" : Math.round(d.coverageDays) + " dias"}`,
                  ),
                  m(
                    "Poder de venda",
                    d.salesPower,
                    "currency",
                    `Estoque: ${d.totalStock}`,
                  ),
                ]
          ).map((item) =>
            stock || ["Poder de venda", "% de giro"].includes(item.label)
              ? { ...item, comparisonBasis: "snapshot" as const }
              : item,
          );
        })}
      />
      <div className="erp-three">
        <BreakdownPanel
          title="Categorias"
          rows={d.breakdowns.categories.map((r) => ({
            label: r.label,
            value: stock ? (r.salesPower ?? 0) : r.revenue,
          }))}
        />
        <BreakdownPanel
          title="Cores"
          currency={false}
          rows={d.breakdowns.colors.map((r) => ({
            label: r.label,
            value: r.units,
          }))}
        />
        <BreakdownPanel
          title="Tamanhos"
          currency={false}
          rows={d.breakdowns.sizes.map((r) => ({
            label: r.label,
            value: r.units,
          }))}
        />
      </div>
      <Panel
        title={stock ? "Inteligência de estoque" : "Desempenho do catálogo"}
        subtitle="Expanda produtos para ver SKU, cor e tamanho. Cobertura: até 15 dias em vermelho, 16–60 em verde, acima de 60 em âmbar. Estoque é snapshot demonstrativo atual."
        action={
          <Export
            name={stock ? "estoque-erp" : "produtos-erp"}
            rows={variants}
            columns={exports}
          />
        }
      >
        <div className="erp-filters erp-filters-wide">
          <Input
            aria-label="Buscar produto ERP"
            placeholder="Buscar produto, SKU ou categoria"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Choice
            label="Categoria ERP"
            value={category}
            onChange={setCategory}
            options={[
              { value: "all", label: "Todas as categorias" },
              ...Array.from(
                new Set(d.rows.map((p) => p.category ?? "Sem categoria")),
              ).map((value) => ({ value, label: value })),
            ]}
          />
          <Choice
            label="Estoque ERP"
            value={inventory}
            onChange={setInventory}
            options={[
              { value: "all", label: "Todo estoque" },
              { value: "in_stock", label: "Com estoque" },
              { value: "out_of_stock", label: "Sem estoque" },
              { value: "negative", label: "Estoque negativo" },
            ]}
          />
          <Choice
            label="Ordenação ERP"
            value={sort}
            onChange={setSort}
            options={[
              { value: "revenue", label: "Maior faturamento" },
              { value: "units", label: "Mais vendidos" },
              { value: "stock", label: "Maior estoque" },
              { value: "turnover", label: "Maior giro" },
              { value: "sales_power", label: "Maior poder de venda" },
              { value: "margin", label: "Maior margem" },
              { value: "coverage", label: "Mais dias restantes" },
            ]}
          />
        </div>
        <DataTable
          key={`${search}-${category}-${inventory}-${sort}`}
          data={rows}
          columns={productColumns(stock, true)}
          pageSize={20}
          renderExpanded={(p) => <Variants product={p} />}
        />
      </Panel>
    </>
  );
}
function Sellers({ data, compare }: { data: ErpData; compare: CompareErp }) {
  const sellers = data.dashboard.breakdowns.sellers,
    stores = data.dashboard.breakdowns.stores;
  const revenue = sellers.reduce((s, r) => s + r.revenue, 0);
  const rows = sellers.map((r) => ({
    ...r,
    ticket: r.orders ? r.revenue / r.orders : 0,
    share: revenue ? (r.revenue / revenue) * 100 : 0,
  }));
  const columns: ExportColumn<Breakdown>[] = [
    { header: "Vendedor", value: (r) => r.label },
    { header: "Pedidos", value: (r) => r.orders },
    { header: "Clientes", value: (r) => r.customers },
    { header: "Faturamento", value: (r) => r.revenue },
    {
      header: "Ticket médio",
      value: (r) => (r.orders ? r.revenue / r.orders : 0),
    },
  ];
  return (
    <>
      <Metrics
        items={compare((data) => {
          const sellers = data.dashboard.breakdowns.sellers,
            stores = data.dashboard.breakdowns.stores;
          const revenue = sellers.reduce((s, r) => s + r.revenue, 0),
            orders = sellers.reduce((s, r) => s + r.orders, 0);
          return [
            m(
              "Vendedores ativos",
              sellers.length,
              "number",
              `${stores.length} lojas`,
            ),
            m("Faturamento", revenue, "currency", `${orders} pedidos`),
            m("Ticket médio", orders ? revenue / orders : null, "currency"),
            m(
              "Clientes atendidos",
              sellers.reduce((s, r) => s + (r.customers ?? 0), 0),
              "number",
              "Soma por vendedor; um cliente pode ser atendido por mais de uma equipe",
            ),
          ];
        })}
      />
      <div className="erp-two">
        <BreakdownPanel
          title="Ranking de vendedores"
          rows={sellers.map((r) => ({ label: r.label, value: r.revenue }))}
        />
        <BreakdownPanel
          title="Desempenho por loja"
          rows={stores.map((r) => ({ label: r.label, value: r.revenue }))}
        />
      </div>
      <Panel
        title="Produtividade comercial"
        action={
          <Export name="vendedores-erp" rows={sellers} columns={columns} csv />
        }
      >
        <DataTable<(typeof rows)[number]>
          data={rows}
          columns={[
            col("label", "Vendedor"),
            col("orders", "Pedidos", number),
            col("customers", "Clientes", number),
            col("revenue", "Faturamento", money),
            col("ticket", "Ticket médio", money),
            col("share", "Participação", pct),
          ]}
        />
      </Panel>
    </>
  );
}
export const erpViews = {
  overview: "Overview",
  pedidos: "Pedidos",
  clientes: "Clientes",
  produtos: "Produtos",
  estoque: "Estoque",
  vendedores: "Vendedores",
} as const;
export function ErpPage({
  view = "overview",
}: {
  view?: keyof typeof erpViews;
}) {
  const q = useResource("erp");
  const c = useRequestContext();
  return (
    <>
      <PageHead
        eyebrow={`${c.scope.operation} · ERP`}
        title={
          <>
            ERP · <em className="hl hl--up">{erpViews[view]}</em>
          </>
        }
        description="Visão integrada de vendas, compradores, catálogo, estoque e equipes."
      />
      <nav className="erp-tabs glass" aria-label="Áreas do ERP">
        {Object.entries(erpViews).map(([key, label]) => (
          <Link
            key={key}
            aria-current={view === key ? "page" : undefined}
            href={key === "overview" ? "/erp" : `/erp/${key}`}
          >
            {label}
          </Link>
        ))}
      </nav>
      <Notice>
        ERP demonstrativo: dados sintéticos e independentes do ledger UP Zero.
        Nenhum ERP conectado. Período global aplicado às vendas; estoque é
        snapshot atual. Histórico parcial, LTV e aquisição histórica não
        confirmados.
      </Notice>
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <div
          className="erp-content"
          key={`${c.scope.store_id}-${JSON.stringify(c.filters)}-${view}`}
        >
          {view === "overview" ? (
            <Overview data={q.data} compare={q.compare} />
          ) : view === "pedidos" ? (
            <Orders data={q.data} compare={q.compare} />
          ) : view === "clientes" ? (
            <Customers data={q.data} compare={q.compare} />
          ) : view === "vendedores" ? (
            <Sellers data={q.data} compare={q.compare} />
          ) : (
            <Products
              data={q.data}
              stock={view === "estoque"}
              compare={q.compare}
            />
          )}
        </div>
      )}
    </>
  );
}
