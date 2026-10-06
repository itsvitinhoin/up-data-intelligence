"use client";
import { useState, useRef, useEffect } from "react";
import { useWorkspace } from "@/features/providers";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  parseCustomerContact,
  type CustomerContact,
} from "@/services/api/contact-contract";
export function CustomerContactDialog({
  id,
  orderId,
}: {
  id: string;
  orderId?: string;
}) {
  const { scope, dataMode } = useWorkspace();
  if (dataMode !== "live" || !scope) return null;
  return (
    <PrivateContact
      key={JSON.stringify([
        id,
        scope.tenant_id,
        scope.workspace_operation_id,
        scope.store_id,
        scope.operation,
      ])}
      id={id}
      orderId={orderId}
    />
  );
}
function PrivateContact({ id, orderId }: { id: string; orderId?: string }) {
  const { scope, dataMode } = useWorkspace(),
    [open, setOpen] = useState(false),
    [contact, setContact] = useState<CustomerContact | null>(null),
    [error, setError] = useState(false),
    [loading, setLoading] = useState(false),
    abort = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      abort.current?.abort();
    },
    [],
  );
  if (dataMode !== "live" || !scope) return null;
  async function change(value: boolean) {
    abort.current?.abort();
    setOpen(value);
    setContact(null);
    setError(false);
    setLoading(false);
    if (!value || !scope) return;
    const controller = new AbortController();
    abort.current = controller;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        tenant_id: scope.tenant_id,
        workspace_operation_id: scope.workspace_operation_id ?? scope.store_id,
        operation: scope.operation,
      });
      if (orderId) params.set("order_id", orderId);
      const res = await fetch(
        `/api/dashboard/customers/${encodeURIComponent(id)}/contact?${params}`,
        { cache: "no-store", signal: controller.signal },
      );
      if (!res.ok) throw new Error("contact_unavailable");
      const result: unknown = await res.json();
      if (!result || typeof result !== "object" || !("data" in result))
        throw new Error("contact_invalid");
      const parsed = parseCustomerContact(result.data);
      if (!controller.signal.aborted) setContact(parsed);
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={(value) => void change(value)}>
      <DialogTrigger asChild>
        <Button variant="outline">
          {orderId ? "Dados do pedido" : "Cadastro atual"}
        </Button>
      </DialogTrigger>
      <DialogContent className="no-print" data-html2canvas-ignore="true">
        <DialogTitle>Contato do cliente</DialogTitle>
        <DialogDescription>
          {orderId
            ? "Contato capturado no pedido; não representa o cadastro atual."
            : "Perfil CORE atual observado; não representa o contato histórico do pedido."}{" "}
          Disponível apenas neste detalhe autorizado.
        </DialogDescription>
        {loading ? (
          <p>Carregando contato…</p>
        ) : error ? (
          <p role="alert">Contato indisponível.</p>
        ) : contact ? (
          <dl className="detail-list">
            {(
              [
                ["CNPJ", contact.cnpj],
                ["CPF", contact.cpf],
                ["E-mail", contact.email],
                ["Telefone", contact.phone],
                ["Estado", contact.state],
                ["Cidade", contact.city],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ?? "—"}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
