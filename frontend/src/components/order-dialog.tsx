"use client";
import { CustomerContactDialog } from "@/components/customer-contact";
import { useWorkspace } from "@/features/providers";
import type { ExportColumn } from "@/lib/erp-export";
import type { OrderDetail } from "@/types/domain";
import { ListExport } from "@/components/exports";
import { useState } from "react";
import Link from "next/link";
import { useOrder } from "@/hooks/use-resource";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Loading, Failure } from "@/components/ui-kit";
import { money, date } from "@/lib/format";
export function OrderDialog({
  id,
  allOrigins = false,
}: {
  id: string;
  allOrigins?: boolean;
}) {
  const { scope, dataMode } = useWorkspace();
  const b2c = scope?.operation === "B2C";
  const [open, setOpen] = useState(false);
  const q = useOrder(id, open, allOrigins);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="order-link mono" aria-label={`Ver pedido ${id}`}>
          #{id} ↗
        </button>
      </DialogTrigger>
      <DialogContent className="glass order-dialog">
        <DialogTitle>Pedido #{id}</DialogTitle>
        <DialogDescription>
          {b2c
            ? "Itens comprados e valor captado deste pedido."
            : dataMode === "demo"
              ? "Produtos e cliente deste pedido · dados de contato fictícios no ambiente demonstrativo."
              : "Itens atuais do pedido. Valores solicitados e atendidos separados; contatos não certificados ficam indisponíveis."}
        </DialogDescription>
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <Failure retry={() => void q.refetch()} />
        ) : (
          <>
            {!b2c && (
              <div className="order-summary">
                <span>
                  {date(q.data.order.date)} · {q.data.order.status}
                </span>
                <strong>{money(q.data.order.fulfilled)} atendidos</strong>
              </div>
            )}
            {!b2c && (
              <section aria-label="Cliente do pedido">
                <h3 className="card-title">Cliente</h3>
                {q.data.customer ? (
                  <Link
                    href={`/customers/${q.data.customer?.id ?? ""}`}
                    className="customer-link"
                  >
                    {q.data.customer?.name ?? "Cliente indisponível"} ↗
                  </Link>
                ) : (
                  <p className="muted">Cliente indisponível</p>
                )}
                {dataMode === "live" && q.data.order.customer_id && (
                  <div className="flex gap-2">
                    <CustomerContactDialog
                      id={q.data.order.customer_id}
                      orderId={id}
                    />
                    <CustomerContactDialog id={q.data.order.customer_id} />
                  </div>
                )}
                {dataMode === "demo" && (
                  <dl className="detail-list">
                    {[
                      ["CNPJ", q.data.customer?.cnpj],
                      ["E-mail", q.data.customer?.email],
                      ["Telefone", q.data.customer?.phone],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value ?? "Não informado"}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </section>
            )}
            <section aria-label="Produtos do pedido">
              <h3 className="card-title mb-3">Produtos do pedido</h3>
              <ListExport
                rows={q.data.items}
                name={`produtos-pedido-${id}`}
                columns={
                  b2c
                    ? ([
                        { header: "Produto", value: (r) => r.name },
                        { header: "Cor", value: (r) => r.color },
                        { header: "Tamanho", value: (r) => r.size },
                        {
                          header: "Peças compradas",
                          value: (r) => r.requestedQuantity,
                        },
                        { header: "Valor", value: (r) => r.requested },
                      ] satisfies ExportColumn<OrderDetail["items"][number]>[])
                    : undefined
                }
              />
              <div className="table-scroll">
                <table className="list num">
                  <thead>
                    <tr>
                      {[
                        "Produto",
                        "Cor",
                        "Tamanho",
                        ...(b2c
                          ? ["Peças compradas", "Valor"]
                          : [
                              "Qtd. solicitada",
                              "Qtd. atendida",
                              "Solicitado",
                              "Atendido",
                            ]),
                      ].map((label) => (
                        <th key={label}>{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.items.map((item, i) => (
                      <tr key={`${item.product_id}:${i}`}>
                        <td>
                          {item.name ??
                            item.sku ??
                            "Identificação indisponível"}
                          {!b2c && (
                            <small className="block muted">
                              {item.reference
                                ? `Ref. ${item.reference} · `
                                : ""}
                              {item.sku ? `SKU ${item.sku}` : ""}
                            </small>
                          )}
                        </td>
                        <td>{item.color ?? "—"}</td>
                        <td>{item.size ?? "—"}</td>
                        <td>{item.requestedQuantity ?? "—"}</td>
                        {b2c ? (
                          <td>{money(item.requested)}</td>
                        ) : (
                          <>
                            <td>{item.fulfilledQuantity ?? "—"}</td>
                            <td>{money(item.requested)}</td>
                            <td>{money(item.fulfilled)}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            {q.data.reconciliation && (
              <p className="metric-hint">
                Valores dos itens: quantidade × preço unitário atual, antes dos
                ajustes do pedido. Ajuste solicitado:{" "}
                {money(q.data.reconciliation.requestedOrderAdjustment, 2)};
                ajuste atendido:{" "}
                {money(q.data.reconciliation.fulfilledOrderAdjustment, 2)}.
              </p>
            )}
            <div className="order-summary">
              {b2c ? (
                <span>Valor do pedido: {money(q.data.order.requested)}</span>
              ) : (
                <>
                  <span>Total solicitado: {money(q.data.order.requested)}</span>
                  <span>Total atendido: {money(q.data.order.fulfilled)}</span>
                </>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
