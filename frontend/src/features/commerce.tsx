"use client";
import { RetailProductsPage } from "@/features/retail-products";
import { ListExport } from "@/components/exports";
import { RetentionDashboard } from "@/features/lifecycle";
import { useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { useResource } from "@/hooks/use-resource";
import { useWorkspace } from "@/features/providers";
import {
  PageHead,
  Panel,
  Loading,
  Failure,
  Notice,
  MetricCard,
  Choice,
} from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
import { DataTable } from "@/components/data-table";
import {
  campaignColumns,
  productColumns,
  orderColumns,
  ProductDrawer,
  Sizes,
} from "@/components/business";
import type { Product } from "@/types/domain";
import { money, number } from "@/lib/format";
export function PerformancePage() {
  const q = useResource("performance");
  return (
    <>
      <PageHead
        eyebrow="Performance intelligence"
        title={
          <>
            Mídia que conecta <em className="hl hl--up">jornadas.</em>
          </>
        }
        description="Investimento, participação e resultado comercial no mesmo recorte."
      />
      <FiltersBar />
      <Link className="btn btn--glass w-fit" href="/media">
        Clientes e pedidos influenciados →
      </Link>
      <Notice>
        Influência não é atribuição exclusiva. Uma compra pode participar de
        mais de uma campanha; não some suas receitas. CAC de novos clientes
        exige histórico completo.
      </Notice>
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <Panel
          title="Performance por campanha"
          subtitle="Dados sintéticos · clique em uma campanha para explorar"
        >
          <DataTable data={q.data} columns={campaignColumns} />
        </Panel>
      )}
    </>
  );
}
const inventoryColumns: ColumnDef<Product>[] = [
  {
    accessorKey: "name",
    header: "Produto",
    cell: ({ row }) => <ProductDrawer product={row.original} />,
  },
  { accessorKey: "stock", header: "Estoque" },
  {
    accessorKey: "sellThrough",
    header: "Sell through",
    cell: (i) => `${i.getValue()}%`,
  },
  { accessorKey: "turnover", header: "Giro", cell: (i) => `${i.getValue()}x` },
  {
    accessorKey: "coverage",
    header: "Cobertura",
    cell: (i) => `${i.getValue()} dias`,
  },
  { accessorKey: "color", header: "Cor" },
  {
    id: "grade",
    header: "Grade",
    cell: ({ row }) => (
      <>
        <Sizes product={row.original} />
        <small className="muted">
          {Object.values(row.original.sizes).every(Boolean)
            ? "Completa"
            : "Quebrada"}{" "}
          ·{" "}
          {Math.round(
            (Object.values(row.original.sizes).filter(Boolean).length /
              Object.keys(row.original.sizes).length) *
              100,
          )}
          % disponível
        </small>
      </>
    ),
  },
];
const retailColumns: ColumnDef<Product>[] = [
  productColumns[0],
  {
    accessorKey: "requested",
    header: "Receita captada",
    cell: (i) => money(i.getValue<string>()),
  },
  { accessorKey: "units", header: "Unidades" },
  { accessorKey: "views", header: "Views" },
  { accessorKey: "cart", header: "Carrinho" },
  { accessorKey: "checkout", header: "Checkout" },
  { accessorKey: "orders", header: "Compras" },
  {
    id: "conversion",
    header: "View → Compra",
    cell: ({ row }) =>
      row.original.views
        ? `${((row.original.orders / row.original.views) * 100).toFixed(1)}%`
        : "—",
  },
  { accessorKey: "abc", header: "ABC" },
];
export function ProductsPage({ inventory = false }: { inventory?: boolean }) {
  const { scope } = useWorkspace();
  return scope?.operation === "B2C" ? (
    <RetailProductsPage inventory={inventory} />
  ) : (
    <LegacyProductsPage inventory={inventory} />
  );
}
function LegacyProductsPage({ inventory = false }: { inventory?: boolean }) {
  const q = useResource("products");
  const { scope } = useWorkspace();
  return (
    <>
      <PageHead
        eyebrow={
          inventory ? "Disponibilidade & demanda" : "Inteligência de produto"
        }
        title={
          inventory ? (
            <>
              Cada tamanho <em className="hl hl--up">importa.</em>
            </>
          ) : (
            <>
              Os produtos que movem <em className="hl hl--up">seu negócio.</em>
            </>
          )
        }
        description={
          inventory
            ? "Estoque, giro e cobertura por produto."
            : "Performance comercial, curva ABC e oportunidades na grade."
        }
      />
      <FiltersBar />
      {inventory && (
        <Notice>
          Estoque e disponibilidade são demonstrativos. A integração de
          inventário ainda não está conectada.
        </Notice>
      )}
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <>
          <div className="metrics">
            {[
              {
                label: "Produtos no recorte",
                value: String(q.data.length),
                format: "number" as const,
                hint: "Catálogo demonstrativo",
              },
              {
                label: "Peças em estoque",
                value: String(q.data.reduce((s, p) => s + p.stock, 0)),
                format: "number" as const,
                hint: "Disponibilidade sintética",
              },
              {
                label: "Grades completas",
                value: String(
                  q.data.filter((p) => Object.values(p.sizes).every(Boolean))
                    .length,
                ),
                format: "number" as const,
                hint: "Todos os tamanhos disponíveis",
              },
              {
                label: "Grades quebradas",
                value: String(
                  q.data.filter((p) => !Object.values(p.sizes).every(Boolean))
                    .length,
                ),
                format: "number" as const,
                hint: "Ao menos um tamanho indisponível",
              },
            ].map((m, i) => (
              <MetricCard key={m.label} item={m} index={i} />
            ))}
          </div>
          <Panel
            title={inventory ? "Estoque e grade" : "Ranking de produtos"}
            subtitle="Explore um produto para abrir seus detalhes"
          >
            <DataTable
              data={q.data}
              columns={
                inventory
                  ? inventoryColumns
                  : scope?.operation === "B2C"
                    ? retailColumns
                    : productColumns
              }
            />
          </Panel>
        </>
      )}
    </>
  );
}
export function RetentionPage() {
  return <RetentionDashboard />;
}
export function OrdersPage() {
  const q = useResource("orders");
  const [status, setStatus] = useState("all");
  return (
    <>
      <PageHead
        eyebrow="Receita & pedidos"
        title={
          <>
            Do pedido ao <em className="hl hl--up">resultado.</em>
          </>
        }
        description="Visibilidade comercial e estrutura preparada para a confirmação financeira."
      />
      <FiltersBar />
      <Notice>
        Pago, pendente de pagamento e tempo até pagamento exigem fonte
        financeira. Status comercial não comprova liquidação.
      </Notice>
      <div className="metrics">
        {[
          "Tempo pedido → pagamento",
          "Pagamento no mesmo dia",
          "Pagamento até 24h",
          "Pagamento até 3 dias",
        ].map((label) => (
          <MetricCard
            key={label}
            item={{
              label,
              value: null,
              format: "number",
              hint: "Fonte de pagamentos não conectada",
            }}
          />
        ))}
      </div>
      <Panel
        title="Pedidos"
        action={
          <Choice
            label="Status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "Todos" },
              { value: "PAID", label: "Pago · sem fonte" },
              { value: "PENDING_PAYMENT", label: "Pendente · sem fonte" },
              { value: "CANCELED", label: "Cancelado" },
              { value: "SHIPPED", label: "Enviado" },
              { value: "DELIVERED", label: "Entregue" },
              { value: "CONFIRMED", label: "Confirmado" },
              { value: "INVOICED", label: "Faturado" },
            ]}
          />
        }
      >
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <Failure retry={() => void q.refetch()} />
        ) : (
          <DataTable
            data={q.data.filter((o) => status === "all" || o.status === status)}
            columns={orderColumns}
          />
        )}
      </Panel>
    </>
  );
}
export function FunnelPage() {
  const q = useResource("funnel");
  return (
    <>
      <PageHead
        eyebrow="Ecommerce intelligence"
        title={
          <>
            Cada etapa. Uma <em className="hl hl--up">oportunidade.</em>
          </>
        }
        description="Navegação, intenção e compras observadas em uma visão do funil."
      />
      <FiltersBar />
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <>
          <Panel
            title="Funil de conversão"
            action={<ListExport rows={q.data} name="funil" />}
            subtitle="Volumes demonstrativos · etapas não comprovam identidade individual"
          >
            <div className="funnel">
              {q.data.map((r, i) => (
                <div className="funnel-row" key={r.label}>
                  <span>{r.label}</span>
                  <div>
                    <i
                      style={{
                        width: `${Math.max(3, (r.value / q.data[0].value) * 100)}%`,
                        opacity: 1 - i * 0.09,
                      }}
                    />
                  </div>
                  <strong>{number(r.value)}</strong>
                </div>
              ))}
            </div>
          </Panel>
          <div className="metrics">
            {[
              [0, 3, "Sessão → Carrinho"],
              [3, 4, "Carrinho → Checkout"],
              [4, 5, "Checkout → Compra"],
            ].map(([from, to, label]) => {
              const base = q.data[Number(from)].value;
              return (
                <MetricCard
                  key={String(label)}
                  item={{
                    label: String(label),
                    value: base
                      ? String((q.data[Number(to)].value / base) * 100)
                      : null,
                    format: "percent",
                    hint: "Razão entre volumes das etapas",
                  }}
                />
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
