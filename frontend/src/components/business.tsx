"use client";
import { compareJourney } from "@/lib/journey";
import { useState } from "react";
import { useProduct } from "@/hooks/use-resource";
import { useWorkspace } from "@/features/providers";
import { ProductSales } from "@/components/product-sales";
import { ListExport } from "@/components/exports";
import { OrderDialog } from "@/components/order-dialog";
import { StockMatrix } from "@/components/stock-matrix";
import Link from "next/link";
import {
  ArrowUpRight,
  Package,
  Radio,
  ShoppingBag,
  UserCheck,
  MousePointer2,
  RotateCcw,
} from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Panel, Loading, Failure } from "@/components/ui-kit";
import { money, date, number } from "@/lib/format";
import type {
  Customer,
  Product,
  Order,
  Campaign,
  TimelineEvent,
} from "@/types/domain";
export function MediaBadge({ paid }: { paid: boolean | null }) {
  return (
    <span className={`pill ${paid ? "media-pill" : "muted"}`}>
      {paid === null
        ? "Indisponível"
        : paid
          ? "Sim · influenciado"
          : "Não · sem evidência observada"}
    </span>
  );
}
export function Sizes({ product }: { product: Product }) {
  if (product.sizes === null)
    return <span className="muted">Indisponível</span>;
  return (
    <div className="sizes">
      {Object.entries(product.sizes).map(([size, available]) => (
        <span
          key={size}
          className={`size ${available ? "" : "size--out"}`}
          title={available ? "Disponível" : "Indisponível"}
        >
          {size}
        </span>
      ))}
    </div>
  );
}
export function ProductDrawer({
  product: initialProduct,
}: {
  product: Product;
}) {
  const { scope, dataMode } = useWorkspace();
  const [open, setOpen] = useState(false);
  const detail = useProduct(initialProduct.id, open && dataMode !== "demo");
  const product = detail.data ?? initialProduct;
  const b2c = scope?.operation === "B2C";
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button className="prod text-left">
          <span className="prod-thumb">
            <Package size={17} />
          </span>
          <span>
            <span className="prod-name">
              {product.name ?? product.sku ?? "Identificação indisponível"}
            </span>
            <span className="prod-sku block">
              {product.sku ?? product.reference}
            </span>
          </span>
        </button>
      </SheetTrigger>
      <SheetContent className="detail-sheet">
        <SheetTitle>
          {product.name ?? product.sku ?? "Identificação indisponível"}
        </SheetTitle>
        <SheetDescription>
          {product.sku ?? product.reference ?? "SKU indisponível"} · Curva{" "}
          {product.abc ?? "indisponível"}
        </SheetDescription>
        <Panel title="Desempenho comercial">
          {dataMode !== "demo" && detail.isPending ? (
            <Loading />
          ) : dataMode !== "demo" && detail.isError ? (
            <Failure retry={() => void detail.refetch()} />
          ) : (
            <dl className="detail-list">
              <div>
                <dt>{b2c ? "Faturamento captado" : "Solicitado"}</dt>
                <dd>{money(product.requested)}</dd>
              </div>
              {!b2c && (
                <div>
                  <dt>Atendido</dt>
                  <dd>{money(product.fulfilled)}</dd>
                </div>
              )}
              <div>
                <dt>Pedidos</dt>
                <dd>{number(product.orders)}</dd>
              </div>
              <div>
                <dt>Clientes compradores</dt>
                <dd>{number(product.customers)}</dd>
              </div>
            </dl>
          )}
        </Panel>
        <Panel title="Estoque e grade">
          <StockMatrix product={product} />
          <p>
            {number(product.stock)} peças · {number(product.coverage)} dias de
            cobertura
          </p>
          <span className="metric-hint">
            {product.catalog
              ? "Estoque atual certificado; métricas comerciais acima pertencem ao SKU selecionado. Atributos atuais não reconstituem o catálogo histórico."
              : "Disponibilidade não certificada na fonte atual; traço indica dado indisponível."}
          </span>
        </Panel>
        <ProductSales product={product} />
      </SheetContent>
    </Sheet>
  );
}
export const customerColumns: ColumnDef<Customer>[] = [
  {
    accessorKey: "name",
    header: "Cliente",
    cell: ({ row }) => (
      <Link className="customer-link" href={`/customers/${row.original.id}`}>
        <span className="avatar">
          {row.original.name?.slice(0, 2).toUpperCase() ?? "—"}
        </span>
        <span>
          {row.original.name ?? "Nome indisponível"}
          <small>
            {row.original.city} · {row.original.state}
          </small>
        </span>
      </Link>
    ),
  },
  { accessorKey: "city", header: "Cidade" },
  { accessorKey: "state", header: "UF" },
  { accessorKey: "orders", header: "Pedidos" },
  {
    accessorKey: "requested",
    header: "Solicitado",
    cell: (i) => money(i.getValue<string>()),
  },
  {
    accessorKey: "fulfilled",
    header: "Atendido",
    cell: (i) => money(i.getValue<string>()),
  },
  {
    accessorKey: "lastPurchase",
    header: "Última compra",
    cell: (i) => date(i.getValue<string>()),
  },
  {
    accessorKey: "segment",
    header: "Segmento",
    cell: (i) => <span className="badge">{i.getValue<string>()}</span>,
  },
  {
    accessorKey: "paid",
    header: "Mídia",
    cell: (i) => <MediaBadge paid={i.getValue<boolean>()} />,
  },
];
export const orderColumns: ColumnDef<Order>[] = [
  {
    accessorKey: "id",
    header: "Pedido",
    cell: (i) => <OrderDialog id={i.getValue<string>()} />,
  },
  {
    accessorKey: "date",
    header: "Data",
    cell: (i) => date(i.getValue<string>()),
  },
  {
    accessorKey: "requested",
    header: "Solicitado",
    cell: (i) => money(i.getValue<string>()),
  },
  {
    accessorKey: "fulfilled",
    header: "Atendido",
    cell: (i) => money(i.getValue<string>()),
  },
  { accessorKey: "requestedQuantity", header: "Qtd. solicitada" },
  { accessorKey: "fulfilledQuantity", header: "Qtd. atendida" },
  {
    accessorKey: "status",
    header: "Status",
    cell: (i) => (
      <span className="badge">
        {(
          {
            CONFIRMED: "Confirmado",
            SHIPPED: "Enviado",
            INVOICED: "Faturado",
          } as Record<string, string>
        )[i.getValue<string>()] ?? i.getValue<string>()}
      </span>
    ),
  },
];
export const productColumns: ColumnDef<Product>[] = [
  {
    accessorKey: "name",
    header: "Produto",
    cell: ({ row }) => <ProductDrawer product={row.original} />,
  },
  {
    accessorKey: "units",
    header: "Peças",
    cell: (i) => number(i.getValue<number>()),
  },
  {
    accessorKey: "requested",
    header: "Solicitado",
    cell: (i) => money(i.getValue<string>()),
  },
  {
    accessorKey: "fulfilled",
    header: "Atendido",
    cell: (i) => money(i.getValue<string>()),
  },
  { accessorKey: "customers", header: "Compradores" },
  { accessorKey: "orders", header: "Pedidos" },
  {
    accessorKey: "share",
    header: "Participação",
    cell: (i) => (
      <div className="share">
        <span className="share-track">
          <i style={{ width: `${i.getValue<number>()}%` }} />
        </span>
        <span className="share-pct">
          {i.getValue<number | null>() === null
            ? "—"
            : `${i.getValue<number>()}%`}
        </span>
      </div>
    ),
  },
  { accessorKey: "abc", header: "ABC" },
  {
    id: "sizes",
    header: "Grade",
    cell: ({ row }) => <Sizes product={row.original} />,
  },
];
export function CampaignCard({ campaign }: { campaign: Campaign }) {
  return (
    <Panel
      title={campaign.name}
      subtitle="Campanha participou da jornada."
      action={
        <Link className="btn btn--glass" href={`/campaigns/${campaign.id}`}>
          Abrir campanha
        </Link>
      }
    >
      <dl className="detail-list">
        <div>
          <dt>Investimento</dt>
          <dd>{money(campaign.spend)}</dd>
        </div>
        <div>
          <dt>Solicitado influenciado</dt>
          <dd>{money(campaign.requested)}</dd>
        </div>
        <div>
          <dt>Atendido influenciado</dt>
          <dd>{money(campaign.fulfilled)}</dd>
        </div>
        <div>
          <dt>Novos confirmados</dt>
          <dd>{campaign.newCustomers ?? "Não confirmado"}</dd>
        </div>
      </dl>
      <p className="metric-hint">
        Participação não equivale a atribuição exclusiva. Receitas de campanhas
        não são somáveis.
      </p>
    </Panel>
  );
}
export const campaignColumns: ColumnDef<Campaign>[] = [
  {
    accessorKey: "name",
    header: "Campanha",
    cell: ({ row }) => (
      <Link className="table-link" href={`/campaigns/${row.original.id}`}>
        {row.original.name ?? "Nome indisponível"}
        <ArrowUpRight size={13} />
      </Link>
    ),
  },
  {
    accessorKey: "spend",
    header: "Spend",
    cell: (i) => money(i.getValue<string>()),
  },
  { accessorKey: "customers", header: "Clientes influenciados" },
  {
    accessorKey: "newCustomers",
    header: "Novos clientes influenciados",
    cell: (i) => i.getValue() ?? "—",
  },
  { accessorKey: "orders", header: "Pedidos influenciados" },
  {
    accessorKey: "requested",
    header: "Solicitado",
    cell: (i) => money(i.getValue<string>()),
  },
  {
    accessorKey: "fulfilled",
    header: "Atendido",
    cell: (i) => money(i.getValue<string>()),
  },
  {
    accessorKey: "roasRequested",
    header: "ROAS solicitado",
    cell: (i) => `${Number(i.getValue<string>()).toLocaleString("pt-BR")}x`,
  },
  {
    accessorKey: "roasFulfilled",
    header: "ROAS atendido",
    cell: (i) => `${Number(i.getValue<string>()).toLocaleString("pt-BR")}x`,
  },
  {
    accessorKey: "cac",
    header: "CAC novo cliente",
    cell: (i) => money(i.getValue<string | null>()),
  },
];
const eventIcons: Record<string, typeof Radio> = {
  paid_touch: Radio,
  register_submitted: UserCheck,
  register_approved: UserCheck,
  product_view: MousePointer2,
  cart_created: ShoppingBag,
  checkout_started: ShoppingBag,
  order_created: ShoppingBag,
  repeat_purchase: RotateCcw,
};
export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <>
      <ListExport rows={events.toSorted(compareJourney)} name="jornada" />
      <ol className="timeline">
        {events.toSorted(compareJourney).map((event) => {
          const Icon = eventIcons[event.type] ?? Radio;
          return (
            <li key={event.id}>
              <span className="timeline-icon">
                <Icon size={17} />
              </span>
              <div>
                <div className="timeline-head">
                  <strong>{event.title}</strong>
                  <span className="badge">{event.evidence}</span>
                </div>
                <p>{event.detail}</p>
                {event.items?.length ? (
                  <details>
                    <summary>
                      {event.items.length} itens observados neste pedido
                    </summary>
                    <ul>
                      {event.items.map((item) => (
                        <li key={item.id}>
                          {item.title}
                          {item.productId ? ` · Produto ${item.productId}` : ""}
                          {item.variantId
                            ? ` · Variante ${item.variantId}`
                            : ""}
                          {item.detail ? ` · ${item.detail}` : ""}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                <time dateTime={event.date}>
                  {date(event.date)} ·{" "}
                  {new Date(event.date).toLocaleTimeString("pt-BR", {
                    hour: "2-digit",
                    minute: "2-digit",
                    timeZone: "America/Sao_Paulo",
                  })}
                </time>
              </div>
            </li>
          );
        })}
      </ol>
    </>
  );
}
