"use client";
import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { metric } from "@/lib/format";
import { displayRange } from "@/lib/period";
import type { Metric } from "@/types/domain";

export function MetricComparisonLine({ item }: { item: Metric }) {
  const comparison = item.comparison;
  const range = comparison ? displayRange(comparison.from, comparison.to) : "";
  if (
    !comparison ||
    comparison.state === "unavailable" ||
    comparison.state === "loading"
  )
    return (
      <div
        className="metric-comparison"
        title={
          comparison?.reason ??
          "Sem dados comparáveis do período anterior para esta métrica."
        }
      >
        <span className="metric-hint">
          {comparison?.state === "loading"
            ? "Comparando períodos…"
            : "Comparação indisponível"}
        </span>
        {range && <span className="metric-hint">Anterior: {range}</span>}
      </div>
    );
  const lowerIsBetter =
    item.comparisonDirection === "lower" ||
    /^(CAC|CPC|CPM|CPA|CPL|Custo|Gap|Receita Cancelada|Pedidos Cancelados|Dias para|Dias médios|Mediana até|Cancelamentos|Produtos em Risco|Grades quebradas|% de Grade Quebrada)/i.test(
      item.label,
    );
  const neutral =
    item.comparisonDirection === "neutral" ||
    /^(Investimento|Spend|Estoque|Peças em Estoque)/i.test(item.label);
  const good = lowerIsBetter
    ? comparison.direction === "down"
    : comparison.direction === "up";
  const Icon =
    comparison.direction === "up"
      ? ArrowUpRight
      : comparison.direction === "down"
        ? ArrowDownRight
        : Minus;
  return (
    <div
      className="metric-comparison"
      title={`${range}. ${comparison.reason ?? "Período imediatamente anterior, com a mesma duração e os mesmos filtros."}`}
    >
      <div className="metric-row">
        <span
          className={cn(
            "delta",
            comparison.direction === "flat" ||
              neutral ||
              comparison.state === "no-baseline"
              ? "delta--neutral"
              : good
                ? "delta--good"
                : "delta--bad",
          )}
        >
          <Icon size={13} aria-hidden="true" />
          {comparison.state === "no-baseline"
            ? "Sem base percentual"
            : `${Number(comparison.change).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2, signDisplay: "exceptZero" })} ${comparison.unit}`}
        </span>
        <span className="metric-hint">vs. período anterior</span>
      </div>
      <span className="metric-hint">
        Anterior:{" "}
        <span className="num">
          {metric(comparison.previous, item.format, item.displayDigits)}
        </span>
      </span>
    </div>
  );
}
