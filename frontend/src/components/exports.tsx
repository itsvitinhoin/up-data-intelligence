"use client";
import { useWorkspace } from "@/features/providers";
import { usePathname } from "next/navigation";
import { dateRange, displayRange } from "@/lib/period";
import { useState } from "react";
import { Download, FileDown } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { Button } from "@/components/ui/button";
import { exportErp, type ExportColumn } from "@/lib/erp-export";
import { recordColumns } from "@/lib/list-export";

export function ListExport<T>({
  rows,
  currentRows = rows,
  columns,
  name = "lista",
}: {
  rows: T[];
  currentRows?: T[];
  columns?: ExportColumn<T>[];
  name?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download(all: boolean, csv: boolean) {
    setBusy(true);
    setError("");
    try {
      await exportErp(
        `${name}-${all ? "todos" : "pagina"}.${csv ? "csv" : "xlsx"}`,
        all ? rows : currentRows,
        columns ?? recordColumns(rows),
        csv,
      );
    } catch {
      setError("Não foi possível exportar. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="list-export no-print">
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy || !rows.length}
            aria-label={`Exportar lista: ${name}`}
          >
            <Download size={14} />
            {busy ? "Exportando…" : "Exportar lista"}
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="export-menu glass"
            align="end"
            sideOffset={6}
          >
            <DropdownMenu.Label>
              Registros do recorte selecionado
            </DropdownMenu.Label>
            {[false, true].flatMap((all) =>
              [false, true].map((csv) => (
                <DropdownMenu.Item
                  key={`${all}-${csv}`}
                  onSelect={() => void download(all, csv)}
                >
                  {all
                    ? `Todos (${rows.length})`
                    : `Página atual (${currentRows.length})`}{" "}
                  · {csv ? "CSV" : "Excel (.xlsx)"}
                </DropdownMenu.Item>
              )),
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
export function PageExport() {
  return (
    <Button
      variant="ghost"
      className="no-print"
      onClick={() => window.print()}
      title="Salvar como PDF · A4 vertical · conteúdo da página e filtros atuais"
    >
      <FileDown size={16} />
      Exportar PDF
    </Button>
  );
}

export function PrintContext() {
  const { filters } = useWorkspace();
  const admin = usePathname().startsWith("/admin");
  const range = dateRange(filters);
  return (
    <div className="print-context">
      <strong>UP Data Intelligence</strong>
      <p>
        {admin
          ? "Administração UP"
          : `${displayRange(range.from, range.to)} · America/Sao_Paulo · datas inclusivas`}{" "}
        · Ambiente demonstrativo
      </p>
    </div>
  );
}
