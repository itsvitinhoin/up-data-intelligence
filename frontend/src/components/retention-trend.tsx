"use client";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RetentionSummary } from "@/types/domain";
export function RetentionTrend({ data }: { data: RetentionSummary["series"] }) {
  return (
    <div
      className="chart-box"
      role="img"
      aria-label="Percentual de retenção por período"
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        initialDimension={{ width: 600, height: 240 }}
      >
        <LineChart data={data}>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,.06)" />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => v.slice(8) + "/" + v.slice(5, 7)}
            minTickGap={35}
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <YAxis
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{
              background: "#0b1020",
              borderColor: "#253252",
              borderRadius: 12,
            }}
            formatter={(v) =>
              `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
            }
          />
          <Line
            dataKey="rate"
            name="Retenção"
            stroke="#6E9BFF"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
