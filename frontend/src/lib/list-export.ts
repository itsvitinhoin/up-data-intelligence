import type { ExportColumn, ExportCell } from "./erp-export";
// Export only supplied, authorized records. Exclude binary media and credentials.
const excluded = /logo|password|token|secret|credential/i;
export function recordColumns<T>(rows: T[]): ExportColumn<T>[] {
  const keys = [
    ...new Set(rows.flatMap((row) => Object.keys(Object(row)))),
  ].filter(
    (key) =>
      !excluded.test(key) &&
      rows.every((row) => {
        const value = (row as Record<string, unknown>)[key];
        return (
          value == null ||
          ["string", "number", "boolean"].includes(typeof value)
        );
      }),
  );
  return keys.map((key) => ({
    header: key,
    value: (row: T): ExportCell => {
      const value = (row as Record<string, unknown>)[key];
      if (value == null) return null;
      if (["string", "number", "boolean"].includes(typeof value))
        return value as ExportCell;
      // Nested objects require an explicit export contract; never dump arbitrary payloads.
      return null;
    },
  }));
}
