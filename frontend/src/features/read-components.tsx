"use client";
import { useState, type ReactNode } from "react";
import { MetricCard, Notice, Empty } from "@/components/ui-kit";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { exportErp } from "@/lib/erp-export";
import { recordColumns } from "@/lib/list-export";
import type { Metric } from "@/types/domain";
import type { ReadPagination } from "@/services/api/http";
export function Cards({
  items,
}: {
  items: [string, string | number | null, Metric["format"], string?][];
}) {
  return (
    <div className="metrics">
      {items.map(([label, value, format, hint]) => (
        <MetricCard
          key={label}
          item={{
            label,
            value: value === null ? null : String(value),
            format,
            hint:
              hint ??
              "Indicador observado no histórico disponível; não confirma histórico completo.",
            displayDigits:
              format === "currency" || format === "percent" ? 2 : undefined,
          }}
        />
      ))}
    </div>
  );
}
export function RemoteTable<T>({
  rows,
  columns,
  pagination,
  previous,
  next,
  canPrevious,
  rowKey,
}: {
  rows: T[];
  columns: { label: string; value: (row: T) => ReactNode }[];
  pagination: ReadPagination | null;
  previous: () => void;
  next: () => void;
  canPrevious: boolean;
  rowKey: (row: T) => string;
}) {
  const [exportError, setExportError] = useState(false);
  return (
    <>
      <div className="no-print flex gap-2 justify-end">
        <Button
          variant="ghost"
          disabled={!rows.length}
          onClick={() =>
            void exportErp(
              "pagina-observada.xlsx",
              rows,
              recordColumns(rows),
              false,
            ).catch(() => setExportError(true))
          }
        >
          Exportar página · Excel
        </Button>
        <Button
          variant="ghost"
          disabled={!rows.length}
          onClick={() =>
            void exportErp(
              "pagina-observada.csv",
              rows,
              recordColumns(rows),
              true,
            ).catch(() => setExportError(true))
          }
        >
          Exportar página · CSV
        </Button>
      </div>
      {exportError && (
        <Notice>Exportação indisponível. Tente novamente.</Notice>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((c) => (
              <TableHead key={c.label}>{c.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map((c) => (
                <TableCell key={c.label}>{c.value(row)}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {!rows.length && <Empty />}
      <div className="table-pagination no-print flex gap-3 items-center">
        <Button variant="ghost" disabled={!canPrevious} onClick={previous}>
          Anterior
        </Button>
        <span>Até {pagination?.page_size} registros por página</span>
        <Button
          variant="ghost"
          disabled={!pagination?.has_more || !pagination.cursor}
          onClick={next}
        >
          Próxima
        </Button>
      </div>
      <p className="note">
        Exportação limitada à página carregada. Não representa a totalidade da
        base.
      </p>
    </>
  );
}
