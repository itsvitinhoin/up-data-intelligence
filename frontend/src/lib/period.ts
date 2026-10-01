import type { Filters } from "@/types/domain";
export const DEMO_TODAY = "2026-09-30";
const DAY = 86400000;
export const periodPresets = [
  ["month", "Este mês"],
  ["7", "Últimos 7 dias"],
  ["30", "Últimos 30 dias"],
  ["90", "Últimos 90 dias"],
  ["year", "Este ano"],
  ["last-month", "Mês passado"],
  ["week", "Esta semana"],
  ["custom", "Personalizado"],
] as const;
export function isoDay(time: number) {
  return new Date(time).toISOString().slice(0, 10);
}
export function validDate(value: string) {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) &&
    isoDay(Date.parse(value)) === value
  );
}
export function shiftIsoDay(value: string, days: number) {
  if (!validDate(value) || !Number.isSafeInteger(days))
    throw new Error("Invalid calendar day");
  return isoDay(Date.parse(value) + days * DAY);
}
export function inclusiveToExclusive(value: string) {
  return shiftIsoDay(value, 1);
}
export function exclusiveToInclusive(value: string) {
  return shiftIsoDay(value, -1);
}
export function periodError(from: string, to: string) {
  if (!validDate(from) || !validDate(to))
    return "Selecione uma data de início e uma data de fim válidas.";
  if (from > to)
    return "A data de início deve ser anterior ou igual à data de fim.";
  return null;
}
export function presetRange(preset: string, today = DEMO_TODAY) {
  const end = Date.parse(today),
    date = new Date(end);
  let from = today,
    to = today;
  if (["7", "30", "90"].includes(preset))
    from = isoDay(end - (Number(preset) - 1) * DAY);
  if (preset === "month") from = today.slice(0, 7) + "-01";
  if (preset === "year") from = today.slice(0, 4) + "-01-01";
  if (preset === "week")
    from = isoDay(end - ((date.getUTCDay() + 6) % 7) * DAY);
  if (preset === "last-month") {
    from = isoDay(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() - 1, 1));
    to = isoDay(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 0));
  }
  return { from, to };
}
export function dateRange(filters: Filters) {
  const range =
    filters.from && filters.to
      ? { from: filters.from, to: filters.to }
      : presetRange(String(filters.days));
  const error = periodError(range.from, range.to);
  if (error) throw new Error(error);
  return {
    ...range,
    days: Math.round((Date.parse(range.to) - Date.parse(range.from)) / DAY) + 1,
  };
}
export function periodDays(filters: Filters) {
  const range = dateRange(filters);
  return Array.from({ length: range.days }, (_, i) =>
    isoDay(Date.parse(range.from) + i * DAY),
  );
}
export function inPeriod(day: string, filters: Filters) {
  const { from, to } = dateRange(filters);
  return day >= from && day <= to;
}
export function displayRange(from: string, to: string) {
  const display = (value: string) => value.split("-").reverse().join("/");
  return `${display(from)} – ${display(to)}`;
}
