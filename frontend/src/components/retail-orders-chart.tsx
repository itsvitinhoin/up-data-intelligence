"use client";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { money } from "@/lib/format";
export function RetailOrdersChart({
  data,
}: {
  data: { date: string; orders: number; revenue: number }[];
}) {
  return (
    <div
      className="chart-box"
      role="img"
      aria-label="Quantidade de pedidos e faturamento por período"
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={1}
        initialDimension={{ width: 700, height: 260 }}
      >
        <ComposedChart data={data}>
          <CartesianGrid vertical={false} stroke="#253252" />
          <XAxis
            dataKey="date"
            tickFormatter={(d) => d.slice(5).split("-").reverse().join("/")}
            tick={{ fill: "#9299b2", fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            yAxisId="revenue"
            tickFormatter={(v) => `${v / 1000}k`}
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <YAxis
            yAxisId="orders"
            orientation="right"
            allowDecimals={false}
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{ background: "#0b1020", borderColor: "#253252" }}
            formatter={(v, n) =>
              n === "Faturamento"
                ? money(Number(v))
                : Number(v).toLocaleString("pt-BR")
            }
          />
          <Legend />
          <Line
            yAxisId="revenue"
            dataKey="revenue"
            name="Faturamento"
            stroke="#6E9BFF"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            yAxisId="orders"
            dataKey="orders"
            name="Pedidos"
            stroke="#5DD9B0"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
