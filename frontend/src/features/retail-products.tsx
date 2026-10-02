"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import type { ColumnDef } from "@tanstack/react-table";
import { useResource } from "@/hooks/use-resource";
import { FiltersBar } from "@/components/shell";
import {
  PageHead,
  Panel,
  MetricCard,
  Choice,
  Loading,
  Failure,
  Notice,
} from "@/components/ui-kit";
import { DataTable } from "@/components/data-table";
import { ListExport } from "@/components/exports";
import { ProductDrawer, Sizes } from "@/components/business";
import {
  groupedSales,
  brokenGrade,
  atRisk,
  promising,
  stockPower,
  turnoverPercent,
  conversionRate,
} from "@/lib/product-analysis";
import { money, number } from "@/lib/format";
import type { Product, Metric } from "@/types/domain";
const Bars = dynamic(
  () => import("@/components/erp-charts").then((m) => m.ErpBreakdown),
  { ssr: false },
);
function m(
  label: string,
  value: number | null,
  format: Metric["format"],
  hint: string,
): Metric {
  return { label, value: value == null ? null : String(value), format, hint };
}
function Distribution({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: number }[];
}) {
  return (
    <Panel
      title={title}
      action={
        <ListExport
          rows={rows}
          name={title.toLowerCase().replaceAll(" ", "-")}
        />
      }
    >
      <Bars data={rows} currency={false} />
    </Panel>
  );
}
function ColorDots({ product }: { product: Product }) {
  const variants = product.variants ?? [];
  const colors = [
    ...new Map(variants.map((v) => [v.color, v.hex ?? null])).entries(),
  ];
  return (
    <div className="product-colors">
      {colors.map(([color, hex]) => (
        <span
          key={color}
          className="color-dot"
          title={`${color}${hex ? ` · ${hex}` : " · HEX indisponível"}`}
          aria-label={`${color}${hex ? ` ${hex}` : ""}`}
          style={
            hex && /^#[0-9a-fA-F]{6}$/.test(hex)
              ? { backgroundColor: hex }
              : undefined
          }
        />
      ))}
    </div>
  );
}
const inventoryColumns: ColumnDef<Product>[] = [
  {
    accessorKey: "name",
    header: "Produto",
    cell: (c) => <ProductDrawer product={c.row.original} />,
  },
  {
    accessorKey: "stock",
    header: "Estoque",
    cell: (c) => number(c.getValue<number>()),
  },
  {
    id: "sold",
    header: "% vendida",
    accessorFn: (p) => turnoverPercent(p.units, p.stock),
    cell: (c) =>
      c.getValue<number | null>() == null
        ? "—"
        : `${number(c.getValue<number>())}%`,
  },
  {
    accessorKey: "coverage",
    header: "Cobertura em dias",
    cell: (c) => `${c.getValue<number>()} dias`,
  },
  {
    id: "colors",
    header: "Cores",
    cell: (c) => <ColorDots product={c.row.original} />,
  },
  {
    id: "sizes",
    header: "Tamanhos",
    cell: (c) => <Sizes product={c.row.original} />,
  },
  {
    accessorKey: "active",
    header: "Situação",
    cell: (c) =>
      c.getValue<boolean | null>() === true
        ? "Ativo"
        : c.getValue<boolean | null>() === false
          ? "Inativo"
          : "Não informado",
  },
];
export function retailProductMetrics(
  rows: Product[],
  inventory: boolean,
): Metric[] {
  const active = rows.filter((p) => p.active === true);
  const stock = active.reduce((sum, p) => sum + p.stock, 0),
    sold = active.reduce((sum, p) => sum + p.units, 0);
  const power = stockPower(rows);
  const observedMonthlyRevenue = active.reduce(
    (sum, p) => sum + Number(p.requested),
    0,
  );
  const metrics: Metric[] = inventory
    ? [
        m(
          "Produtos Ativos",
          active.length,
          "number",
          "Produtos com situação ativa explícita no catálogo demonstrativo.",
        ),
        m(
          "Peças em Estoque",
          stock,
          "number",
          "Soma do estoque atual dos produtos ativos; snapshot demonstrativo.",
        ),
        m(
          "Poder de Venda",
          power,
          "currency",
          "Peças em estoque × preço atual de venda dos produtos ativos. Sem preço, resultado desconhecido.",
        ),
        m(
          "% de Giro Mensal",
          power && power > 0 ? (observedMonthlyRevenue / power) * 100 : null,
          "percent",
          "Faturamento captado no único mês observado (setembro/2026) / poder de venda do estoque ativo atual × 100. Pode ultrapassar 100%; não há média histórica confirmada.",
        ),
      ]
    : [
        m(
          "Peças Vendidas",
          rows.reduce((sum, p) => sum + p.units, 0),
          "number",
          "Peças vendidas no recorte selecionado; cenário demonstrativo.",
        ),
        m(
          "% de Giro",
          turnoverPercent(sold, stock),
          "percent",
          "Peças vendidas dos produtos ativos / peças em estoque ativo atual × 100. Pode ultrapassar 100%.",
        ),
        m(
          "Produtos em Risco",
          active.filter(atRisk).length,
          "number",
          "Conversão de pedidos / views >= 1,5% e ao menos uma variante sem estoque ou stockout; regra demonstrativa.",
        ),
        m(
          "% de Grade Quebrada",
          active.length
            ? (active.filter(brokenGrade).length / active.length) * 100
            : null,
          "percent",
          "Produtos ativos com ao menos um tamanho sem estoque / produtos ativos × 100.",
        ),
      ];

  return metrics.map((item) =>
    inventory || ["% de Grade Quebrada", "% de Giro"].includes(item.label)
      ? { ...item, comparisonBasis: "snapshot" }
      : item,
  );
}
export function RetailProductsPage({
  inventory = false,
}: {
  inventory?: boolean;
}) {
  const q = useResource(inventory ? "inventory_products" : "products");
  const [curve, setCurve] = useState("all"),
    [activity, setActivity] = useState("all");
  const rows = q.data ?? [];
  const visible = inventory
    ? rows.filter(
        (p) =>
          activity === "all" ||
          (activity === "active" && p.active === true) ||
          (activity === "inactive" && p.active === false),
      )
    : rows.filter(
        (p) =>
          curve === "all" ||
          p.abc === curve ||
          (curve === "promising" && promising(p, rows)),
      );
  const metrics = q.compare((rows) => retailProductMetrics(rows, inventory));
  const rankingColumns: ColumnDef<Product>[] = [
    {
      accessorKey: "name",
      header: "Produto",
      cell: (c) => (
        <div className="product-ranking-name">
          <span
            className={`curve-dot ${promising(c.row.original, rows) ? "curve-dot--promising" : `curve-dot--${c.row.original.abc.toLowerCase()}`}`}
            title={
              promising(c.row.original, rows)
                ? "Promissor"
                : `Curva ${c.row.original.abc}`
            }
          />
          <ProductDrawer product={c.row.original} />
        </div>
      ),
    },
    { accessorKey: "category", header: "Categoria" },
    {
      accessorKey: "units",
      header: "Peças vendidas",
      cell: (c) => number(c.getValue<number>()),
    },
    {
      accessorKey: "requested",
      header: "Faturamento captado",
      cell: (c) => money(c.getValue<string>()),
    },
    {
      id: "conversion",
      header: "Conversão",
      accessorFn: (p) => conversionRate(p),
      cell: (c) =>
        c.getValue<number | null>() == null
          ? "—"
          : `${number(c.getValue<number>())}%`,
    },
    { accessorKey: "abc", header: "Curva ABC" },
    {
      id: "grade",
      header: "Grade",
      accessorFn: (p) => (brokenGrade(p) ? "Quebrada" : "Completa"),
      cell: (c) => (
        <span
          className={`grade-tag ${c.getValue<string>() === "Quebrada" ? "grade-tag--broken" : "grade-tag--complete"}`}
        >
          {c.getValue<string>()}
        </span>
      ),
    },
  ];
  return (
    <>
      <PageHead
        eyebrow={inventory ? "B2C · Estoque" : "B2C · Análise de Produtos"}
        title={
          inventory ? (
            <>
              Estoque e <em className="hl hl--up">grade.</em>
            </>
          ) : (
            <>
              O catálogo em <em className="hl hl--up">movimento.</em>
            </>
          )
        }
        description={
          inventory
            ? "Disponibilidade atual do catálogo, sem filtro temporal."
            : "Vendas, conversão, curva ABC e saúde da grade no período."
        }
      />
      {!inventory && <FiltersBar />}
      {inventory && (
        <Notice>
          O estoque é um snapshot demonstrativo. Vendas por variante no detalhe
          mostram o histórico observado de setembro de 2026; não dependem do
          período selecionado no topo.
        </Notice>
      )}
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <>
          <section
            className="metrics"
            aria-label={
              inventory
                ? "Indicadores de estoque B2C"
                : "Indicadores de análise de produtos B2C"
            }
          >
            {metrics.map((item) => (
              <MetricCard key={item.label} item={item} />
            ))}
          </section>
          {!inventory && (
            <div className="product-distributions">
              <Distribution
                title="Vendas por categoria"
                rows={groupedSales(rows, "category")}
              />
              <Distribution
                title="Vendas por tamanho"
                rows={groupedSales(rows, "size")}
              />
              <Distribution
                title="Vendas por cor"
                rows={groupedSales(rows, "color")}
              />
            </div>
          )}
          <Panel
            title={inventory ? "Estoque e grade" : "Ranking de produtos"}
            subtitle={
              inventory
                ? "Todos os produtos da operação · estoque atual e vendas históricas observadas"
                : "Curva ABC e oportunidades de conversão no recorte"
            }
            action={
              inventory ? (
                <Choice
                  label="Situação do produto"
                  value={activity}
                  onChange={setActivity}
                  options={[
                    { value: "all", label: "Todos" },
                    { value: "active", label: "Ativos" },
                    { value: "inactive", label: "Inativos" },
                  ]}
                />
              ) : (
                <Choice
                  label="Curva ABC"
                  value={curve}
                  onChange={setCurve}
                  options={[
                    { value: "all", label: "Todas as curvas" },
                    { value: "A", label: "Curva A" },
                    { value: "B", label: "Curva B" },
                    { value: "C", label: "Curva C" },
                    { value: "promising", label: "Promissores" },
                  ]}
                />
              )
            }
          >
            <DataTable
              data={visible}
              columns={inventory ? inventoryColumns : rankingColumns}
            />
          </Panel>
        </>
      )}
    </>
  );
}
