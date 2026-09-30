"use client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Overview } from "@/types/domain";
import { money, number } from "@/lib/format";
type Kind = "revenue" | "customers" | "media";
const series = {
  revenue: [
    { key: "requested", name: "Solicitado", color: "#6E9BFF" },
    { key: "fulfilled", name: "Atendido", color: "#5DD9B0" },
  ],
  customers: [
    { key: "newCustomers", name: "Novos", color: "#6E9BFF" },
    { key: "recurringCustomers", name: "Recorrentes", color: "#5DD9B0" },
  ],
  media: [
    { key: "mediaRevenue", name: "Faturamento atribuído", color: "#6E9BFF" },
    { key: "spend", name: "Investimento", color: "#D5AEFF" },
  ],
};
export function OverviewChart({
  data,
  kind,
}: {
  data: NonNullable<Overview["b2b"]>["series"];
  kind: Kind;
}) {
  const shared = (
    <>
      <CartesianGrid vertical={false} stroke="rgba(255,255,255,.06)" />
      <XAxis
        dataKey="date"
        tick={{ fill: "#9299b2", fontSize: 11 }}
        minTickGap={40}
        axisLine={false}
        tickLine={false}
      />
      <YAxis
        tick={{ fill: "#9299b2", fontSize: 11 }}
        tickFormatter={(v) =>
          kind === "customers" ? number(v) : `${v / 1000}k`
        }
        axisLine={false}
        tickLine={false}
        allowDecimals={kind !== "customers"}
      />
      <Tooltip
        contentStyle={{
          background: "#0b1020",
          borderColor: "#253252",
          borderRadius: 12,
        }}
        formatter={(v) =>
          v == null
            ? "Não confirmado"
            : kind === "customers"
              ? number(Number(v))
              : money(Number(v))
        }
      />
      <Legend wrapperStyle={{ fontSize: 12, paddingTop: 16 }} />
    </>
  );
  return (
    <div
      className="chart-box"
      role="img"
      aria-label={
        kind === "customers"
          ? "Novos e recorrentes por período"
          : kind === "media"
            ? "Faturamento e investimento por período"
            : "Solicitado e atendido por período"
      }
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={1}
        minHeight={220}
        initialDimension={{ width: 600, height: 220 }}
      >
        {kind === "customers" ? (
          <BarChart data={data}>
            {shared}
            {series[kind].map((s) => (
              <Bar
                isAnimationActive={false}
                key={s.key}
                dataKey={s.key}
                name={s.name}
                fill={s.color}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        ) : (
          <LineChart
            data={data}
            margin={{ top: 12, right: 8, left: -12, bottom: 0 }}
          >
            {shared}
            {series[kind].map((s) => (
              <Line
                isAnimationActive={false}
                key={s.key}
                dataKey={s.key}
                name={s.name}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
