export function money(value: string | number | null, digits = 0) {
  if (value === null) return "—";
  if (typeof value === "string" && /^-?\d+(?:\.\d+)?$/.test(value)) {
    const negative = value.startsWith("-");
    const [integer, fraction = ""] = (negative ? value.slice(1) : value).split(
      ".",
    );
    const scale = 10n ** BigInt(digits);
    let scaled =
      BigInt(integer) * scale +
      BigInt((fraction + "0".repeat(digits)).slice(0, digits) || "0");
    if ((fraction[digits] ?? "0") >= "5") scaled += 1n;
    const whole = (scaled / scale).toLocaleString("pt-BR");
    return `${negative ? "-" : ""}R$ ${whole}${digits ? "," + String(scaled % scale).padStart(digits, "0") : ""}`;
  }
  return new Intl.NumberFormat("pt-BR", {
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
