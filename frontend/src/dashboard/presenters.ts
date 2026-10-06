import type { Metric } from "@/types/domain";
import type { ReadMetadata, ReadResource } from "@/services/api/http";
import { MetricRegistry } from "./registry";
import { MetricBindings, readPath } from "./bindings";
/** Explicit semantic mapping. Missing values never borrow another commercial state. */
export function managerMetrics(
  ids: string[],
  resource: ReadResource,
  data: unknown,
  metadata?: ReadMetadata,
): Metric[] {
  return ids.map((id) => {
    const definition = MetricRegistry[id],
      binding = MetricBindings[id];
    if (!definition || !binding) throw new Error("Unregistered metric binding");
    const raw =
      binding.resource === resource &&
      binding.path &&
      (!binding.history || metadata?.history_complete === true)
        ? readPath(data, binding.path)
        : null;
    let value =
      typeof raw === "string" && /^-?\d+(?:\.\d+)?$/.test(raw)
        ? raw
        : typeof raw === "number" && Number.isFinite(raw)
          ? String(raw)
          : null;
    if (value !== null && binding.multiplier)
      value = scaleDecimal(value, binding.multiplier);
    return {
      label:
        id === "total_media_spend" && value !== null
          ? "Investimento disponível em Ads (Meta)"
          : definition.label,
      value,
      format: definition.format,
      hint: binding.reason,
    };
  });
}

export function scaleDecimal(value: string, multiplier: number): string {
  const negative = value.startsWith("-");
  const [integer, fraction = ""] = value.replace("-", "").split(".");
  const scaled = BigInt(integer + fraction) * BigInt(multiplier);
  const base = 10n ** BigInt(fraction.length);
  return `${negative ? "-" : ""}${scaled / base}${fraction.length ? "." + (scaled % base).toString().padStart(fraction.length, "0") : ""}`;
}

/** Rational decimal projection; avoids floating-point money conversion. */
export function divideDecimal(
  numerator: string,
  denominator: string,
  multiplier = 1,
): string | null {
  const parse = (v: string) => {
    const [whole, fraction = ""] = v.split(".");
    return {
      value: BigInt(whole + fraction),
      scale: 10n ** BigInt(fraction.length),
    };
  };
  const a = parse(numerator),
    b = parse(denominator);
  if (b.value === 0n) return null;
  const precision = 10n ** 12n;
  const v =
    (a.value * b.scale * BigInt(multiplier) * precision) / (b.value * a.scale);
  const sign = v < 0n ? "-" : "",
    abs = v < 0n ? -v : v;
  return `${sign}${abs / precision}.${(abs % precision).toString().padStart(12, "0")}`;
}
