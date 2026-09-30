"use client";
import { Fragment, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDownUp, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ListExport } from "@/components/exports";
import { recordColumns } from "@/lib/list-export";
import type { ExportColumn } from "@/lib/erp-export";
import { Empty } from "@/components/ui-kit";
export function DataTable<T>({
  data,
  columns,
  pageSize = 6,
  renderExpanded,
  exportColumns,
}: {
  exportColumns?: ExportColumn<T>[];
  data: T[];
  columns: ColumnDef<T>[];
  pageSize?: number;
  renderExpanded?: (row: T) => React.ReactNode;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data,
    columns,
    defaultColumn: {
      sortingFn: (a, b, id) => {
        const left = a.getValue<unknown>(id),
          right = b.getValue<unknown>(id);
        const decimal = (v: unknown) =>
          typeof v === "number" ||
          (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v));
        if (decimal(left) && decimal(right))
          return Number(left) - Number(right);
        return String(left ?? "").localeCompare(String(right ?? ""), "pt-BR", {
          numeric: true,
        });
      },
    },
    state: { sorting },
    onSortingChange: setSorting,
    getRowCanExpand: () => !!renderExpanded,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });
  if (!data.length) return <Empty />;
  return (
    <>
      <ListExport
        rows={table.getPrePaginationRowModel().rows.map((r) => r.original)}
        currentRows={table.getRowModel().rows.map((r) => r.original)}
        columns={
          exportColumns ??
          recordColumns(data).map((column) => {
            const definition = columns.find(
              (c) => "accessorKey" in c && c.accessorKey === column.header,
            );
            return {
              ...column,
              header:
                typeof definition?.header === "string"
                  ? definition.header
                  : column.header,
            };
          })
        }
      />
      <div className="table-scroll">
        <Table className="list num">
          <TableHeader>
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((h) => (
                  <TableHead
                    key={h.id}
                    aria-sort={
                      h.column.getIsSorted() === "asc"
                        ? "ascending"
                        : h.column.getIsSorted() === "desc"
                          ? "descending"
                          : "none"
                    }
                  >
                    {h.column.getCanSort() ? (
                      <button
                        className="table-sort"
                        onClick={h.column.getToggleSortingHandler()}
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        <ArrowDownUp size={11} />
                      </button>
                    ) : (
                      flexRender(h.column.columnDef.header, h.getContext())
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody className="screen-table-body">
            {table.getRowModel().rows.map((row) => (
              <Fragment key={row.id}>
                <TableRow>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
                {row.getIsExpanded() && renderExpanded && (
                  <TableRow>
                    <TableCell colSpan={columns.length}>
                      {renderExpanded(row.original)}
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
          <TableBody className="print-table-body">
            {table.getPrePaginationRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="pagination">
        <span>
          {data.length} registros · Página{" "}
          {table.getState().pagination.pageIndex + 1} de {table.getPageCount()}
        </span>
        <div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Página anterior"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <ChevronLeft size={16} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Próxima página"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <ChevronRight size={16} />
          </Button>
        </div>
      </div>
    </>
  );
}
