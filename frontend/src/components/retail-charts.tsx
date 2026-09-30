"use client";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { RetailSummary } from "@/services/demo/retail";
import { money } from "@/lib/format";
export function RetailRevenueChart({
  data,
}: {
  data: RetailSummary["series"];
}) {
  return (
    <div
      className="chart-box"
      role="img"
      aria-label="Faturamento captado e aprovado por período"
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={1}
        initialDimension={{ width: 600, height: 260 }}
      >
        <LineChart data={data} margin={{ left: 0, right: 10, top: 10 }}>
          <CartesianGrid vertical={false} stroke="#253252" />
          <XAxis
            dataKey="date"
            tickFormatter={(d) => d.slice(5).split("-").reverse().join("/")}
            tick={{ fill: "#9299b2", fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            tickFormatter={(v) => `${v / 1000}k`}
            tick={{ fill: "#9299b2", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{ background: "#0b1020", borderColor: "#253252" }}
            formatter={(v) => money(Number(v))}
          />
          <Legend />
          <Line
            dataKey="captured"
            name="Captado"
            stroke="#6E9BFF"
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
          <Line
            dataKey="approved"
            name="Aprovado"
            stroke="#5DD9B0"
            dot={false}
            strokeWidth={2}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
export function PaidGauge({ rate }: { rate: number | null }) {
  return (
    <div className="gauge" role="img" aria-label="Porcentagem de vendas pagas">
      <svg viewBox="0 0 240 138" aria-hidden="true">
        <path
          d="M24 120 A96 96 0 0 1 216 120"
          fill="none"
          stroke="var(--line-hi)"
          strokeWidth="20"
          strokeLinecap="round"
        />
        {rate !== null && (
          <path
            d="M24 120 A96 96 0 0 1 216 120"
            fill="none"
            stroke="#6E9BFF"
            strokeWidth="20"
            strokeLinecap="round"
            pathLength="100"
            strokeDasharray={`${rate} 100`}
          />
        )}
      </svg>
      <div className="gauge-center">
        <div className="gauge-pct">
          {rate === null ? "—" : `${rate.toLocaleString("pt-BR")}%`}
        </div>
        <div className="gauge-cap">
          {rate === null
            ? "Pagamento não confirmado"
            : "dos pedidos foram pagos"}
        </div>
      </div>
    </div>
  );
}
