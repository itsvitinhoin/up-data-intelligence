export type ExportCell = string | number | boolean | null | undefined;
export interface ExportColumn<T> {
  header: string;
  value: (row: T) => ExportCell;
}
export function csvContent<T>(rows: T[], columns: ExportColumn<T>[]) {
  const cell = (v: ExportCell) =>
    `"${String(typeof v === "string" && /^[\s]*[=+@-]/.test(v) ? `'${v}` : (v ?? "")).replaceAll('"', '""')}"`;
  return (
    "\ufeff" +
    [
      columns.map((c) => cell(c.header)).join(";"),
      ...rows.map((row) => columns.map((c) => cell(c.value(row))).join(";")),
    ].join("\r\n")
  );
}
export async function workbookBytes<T>(rows: T[], columns: ExportColumn<T>[]) {
  const { default: ExcelJS } = await import("exceljs");
  const book = new ExcelJS.Workbook();
  const sheet = book.addWorksheet("Dados");
  sheet.addRow(columns.map((c) => c.header));
  rows.forEach((row) => sheet.addRow(columns.map((c) => c.value(row) ?? null)));
  sheet.getRow(1).font = { bold: true };
  sheet.columns.forEach((c) => (c.width = 24));
  sheet.views = [{ state: "frozen", ySplit: 1 }];
  return new Uint8Array(await book.xlsx.writeBuffer());
}
export async function exportErp<T>(
  filename: string,
  rows: T[],
  columns: ExportColumn<T>[],
  csv = false,
) {
  const blob = csv
    ? new Blob([csvContent(rows, columns)], { type: "text/csv;charset=utf-8" })
    : new Blob([await workbookBytes(rows, columns)], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
