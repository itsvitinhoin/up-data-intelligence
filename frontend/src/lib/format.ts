export function money(value: string | number | null, digits = 0) {
  return value === null
    ? "—"
    : new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(Number(value));
}
export function number(value: string | number | null) {
  return value === null
    ? "—"
    : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(
        Number(value),
      );
}
export function date(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("pt-BR", {
        timeZone: "America/Sao_Paulo",
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(new Date(value.length === 10 ? value + "T12:00:00Z" : value))
    : "Não disponível";
}
export function metric(
  value: string | null,
  format: string,
  displayDigits?: number,
) {
  if (value === null) return "—";
  if (format === "currency") return money(value, displayDigits);
  if (format === "percent" || format === "ratio")
    return (
      new Intl.NumberFormat("pt-BR", {
        maximumFractionDigits: displayDigits ?? 1,
      }).format(Number(value)) + (format === "percent" ? "%" : "x")
    );
  if (format === "decimal" || format === "days")
    return (
      new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(
        Number(value),
      ) + (format === "days" ? " dias" : "")
    );
  return number(value);
}
