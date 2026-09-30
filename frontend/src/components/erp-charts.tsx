"use client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, number } from "@/lib/format";
export function ErpTrend({
  data,
  customers = false,
}: {
  data: { date: string; primary: number; secondary: number }[];
  customers?: boolean;
}) {
  return (
    <div
      className="chart-box"
      role="img"
      aria-label={
        customers ? "Novos e recorrentes ERP" : "Faturamento e pedidos ERP"
      }
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        initialDimension={{ width: 600, height: 240 }}
      >
        <ComposedChart data={data}>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,.06)" />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => v.slice(8) + "/" + v.slice(5, 7)}
            minTickGap={35}
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <YAxis
            yAxisId="primary"
            tickFormatter={(v) =>
              customers ? number(v) : `${number(v / 1000)}k`
            }
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          {!customers && (
            <YAxis
              yAxisId="secondary"
              orientation="right"
              allowDecimals={false}
              tick={{ fill: "#9299b2", fontSize: 11 }}
            />
          )}
          <Tooltip
            contentStyle={{
              background: "#0b1020",
              borderColor: "#253252",
              borderRadius: 12,
            }}
            formatter={(v, n) =>
              !customers && n === "Faturamento"
                ? money(Number(v))
                : number(Number(v))
            }
          />
          <Legend />
          <Line
            yAxisId="primary"
            dataKey="primary"
            name={customers ? "Primeira compra observada" : "Faturamento"}
            stroke="#6E9BFF"
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
          <Line
            yAxisId={customers ? "primary" : "secondary"}
            dataKey="secondary"
            name={customers ? "Recorrentes" : "Pedidos"}
            stroke="#5DD9B0"
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
export function ErpBreakdown({
  data,
  currency = true,
}: {
  data: { label: string; value: number }[];
  currency?: boolean;
}) {
  return (
    <div className="chart-box" role="img" aria-label="Distribuição ERP">
      <ResponsiveContainer
        width="100%"
        height="100%"
        initialDimension={{ width: 400, height: 240 }}
      >
        <BarChart data={data} layout="vertical" margin={{ left: 0, right: 20 }}>
          <XAxis
            type="number"
            tickFormatter={(v) =>
              currency ? `${number(v / 1000)}k` : number(v)
            }
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <YAxis
            dataKey="label"
            type="category"
            width={100}
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{
              background: "#0b1020",
              borderColor: "#253252",
              borderRadius: 12,
            }}
            formatter={(v) => (currency ? money(Number(v)) : number(Number(v)))}
          />
          <Bar
            dataKey="value"
            name={currency ? "Valor" : "Peças"}
            fill="#6E9BFF"
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
