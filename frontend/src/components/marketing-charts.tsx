"use client";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Marketing } from "@/types/domain";
import { money, number } from "@/lib/format";
import { ratio } from "@/lib/marketing";
export function MarketingChart({
  series,
  kind,
  b2c,
  linesOnly = false,
}: {
  series: Marketing["series"];
  kind: "results" | "roas" | "revenue";
  b2c: boolean;
  linesOnly?: boolean;
}) {
  const platform = series.some((row) => row.source === "real");
  const data = series.map((row) => ({
    ...row,
    spend: row.spend === null ? null : Number(row.spend),
    revenue: row.revenue === null ? null : Number(row.revenue),
    date: row.date.slice(8) + "/" + row.date.slice(5, 7),
    results: b2c || platform ? row.purchases : row.leads,
    roas:
      row.source === "real"
        ? row.roas === null || row.roas === undefined
          ? null
          : Number(row.roas)
        : ratio(
            row.revenue === null ? null : Number(row.revenue),
            row.spend === null ? null : Number(row.spend),
          ),
  }));
  return (
    <div
      className="chart-box"
      role="img"
      aria-label={
        kind === "results"
          ? `Investimento e ${b2c || platform ? "compras Meta" : "leads"}`
          : kind === "roas"
            ? "ROAS ao longo do período"
            : platform
              ? "Investimento e valor de compras reportado pelo Meta"
              : "Investimento e receita influenciada"
      }
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={1}
        initialDimension={{ width: 600, height: 240 }}
      >
        <ComposedChart
          data={data}
          margin={{ top: 12, right: 0, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,.06)" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#9299b2", fontSize: 11 }}
            minTickGap={35}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="money"
            tick={{ fill: "#9299b2", fontSize: 11 }}
            tickFormatter={(v) =>
              kind === "roas"
                ? `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}x`
                : `${number(v / 1000)}k`
            }
            axisLine={false}
            tickLine={false}
            width={45}
          />
          {kind === "results" && (
            <YAxis
              yAxisId="results"
              orientation="right"
              tick={{ fill: "#9299b2", fontSize: 11 }}
              allowDecimals={false}
              width={35}
              axisLine={false}
              tickLine={false}
            />
          )}
          <Tooltip
            contentStyle={{
              background: "#0b1020",
              borderColor: "#253252",
              borderRadius: 12,
            }}
            formatter={(value, name) =>
              name === "ROAS"
                ? `${Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}x`
                : name === "Leads" || name === "Compras Meta"
                  ? number(Number(value))
                  : money(Number(value))
            }
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 16 }} />
          {kind !== "roas" &&
            (linesOnly ? (
              <Line
                isAnimationActive={false}
                yAxisId="money"
                dataKey="spend"
                name="Investimento"
                stroke="#6E9BFF"
                strokeWidth={2}
                dot={false}
                connectNulls={false}
              />
            ) : (
              <Bar
                isAnimationActive={false}
                yAxisId="money"
                dataKey="spend"
                name="Investimento"
                fill="#6E9BFF"
                radius={[3, 3, 0, 0]}
              />
            ))}
          <Line
            isAnimationActive={false}
            yAxisId={kind === "results" ? "results" : "money"}
            dataKey={
              kind === "results"
                ? "results"
                : kind === "roas"
                  ? "roas"
                  : "revenue"
            }
            name={
              kind === "results"
                ? b2c || platform
                  ? "Compras Meta"
                  : "Leads"
                : kind === "roas"
                  ? "ROAS"
                  : platform
                    ? "Valor de compras Meta"
                    : "Receita influenciada"
            }
            stroke="#5DD9B0"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
