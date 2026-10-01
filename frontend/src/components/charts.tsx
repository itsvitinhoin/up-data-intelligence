"use client";
import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  BarChart,
  Bar,
} from "recharts";
import type { Overview } from "@/types/domain";
import { money } from "@/lib/format";
export function RevenueChart({ data }: { data: Overview["series"] }) {
  const id = useId();
  return (
    <div
      className="chart-box"
      role="img"
      aria-label="Receita solicitada e atendida por dia"
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={1}
        minHeight={220}
        initialDimension={{ width: 600, height: 220 }}
      >
        <AreaChart
          data={data}
          margin={{ top: 12, right: 8, left: -12, bottom: 0 }}
        >
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0458FE" stopOpacity={0.5} />
              <stop offset="95%" stopColor="#0458FE" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,.06)" />
          <XAxis
            dataKey="date"
            tick={{ fill: "rgba(222,230,255,.42)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            tickFormatter={(v) => `${v / 1000}k`}
            tick={{ fill: "rgba(222,230,255,.42)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#0b1020",
              border: "1px solid rgba(255,255,255,.16)",
              borderRadius: 12,
            }}
            formatter={(v) => money(Number(v))}
          />
          <Area
            type="monotone"
            dataKey="requested"
            name="Solicitado"
            stroke="#6E9BFF"
            strokeWidth={2}
            fill={`url(#${id})`}
          />
          <Area
            type="monotone"
            dataKey="fulfilled"
            name="Atendido"
            stroke="rgba(255,255,255,.5)"
            strokeDasharray="4 4"
            fill="transparent"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
export function OrdersChart({ data }: { data: Overview["series"] }) {
  return (
    <div
      className="chart-box small"
      role="img"
      aria-label="Pedidos por período"
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        minWidth={1}
        minHeight={220}
        initialDimension={{ width: 600, height: 220 }}
      >
        <BarChart data={data}>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,.06)" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#9299b2", fontSize: 11 }}
            minTickGap={40}
          />
          <Tooltip
            contentStyle={{ background: "#0b1020", borderColor: "#253252" }}
          />
          <Bar
            dataKey="orders"
            name="Pedidos"
            fill="#0458FE"
            radius={[5, 5, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
export function Gauge({
  requested,
  fulfilled,
  rate,
}: {
  requested: number | string | null;
  fulfilled: number | string | null;
  rate?: string | null;
}) {
  const ratio =
    rate !== undefined
      ? rate === null
        ? null
        : Number(rate)
      : requested === null || fulfilled === null || Number(requested) === 0
        ? null
        : Number(fulfilled) / Number(requested);
  const id = useId();
  return (
    <>
      <div className="gauge">
        <svg viewBox="0 0 240 138" aria-hidden="true">
          <defs>
            <linearGradient id={id}>
              <stop stopColor="#0458FE" />
              <stop offset="1" stopColor="#7CA6FF" />
            </linearGradient>
          </defs>
          <path
            d="M24 120 A96 96 0 0 1 216 120"
            fill="none"
            stroke="rgba(255,255,255,.08)"
            strokeWidth="20"
            strokeLinecap="round"
          />
          <path
            d="M24 120 A96 96 0 0 1 216 120"
            fill="none"
            stroke={`url(#${id})`}
            strokeWidth="20"
            strokeLinecap="round"
            pathLength="100"
            strokeDasharray={`${ratio === null ? 0 : Math.max(0, Math.min(100, ratio * 100))} 100`}
          />
        </svg>
        <div className="gauge-center">
          <div className="gauge-pct">
            {ratio === null
              ? "—"
              : `${(ratio * 100).toLocaleString("pt-BR", {
                  minimumFractionDigits: rate === undefined ? 0 : 2,
                  maximumFractionDigits: rate === undefined ? 1 : 2,
                })}%`}
          </div>
          <div className="gauge-cap">do solicitado foi atendido</div>
        </div>
      </div>
      <div className="gauge-rows">
        <div>
          <small>Solicitado</small>
          <span>{money(requested, rate === undefined ? 0 : 2)}</span>
        </div>
        <div>
          <small>Atendido</small>
          <span>{money(fulfilled, rate === undefined ? 0 : 2)}</span>
        </div>
      </div>
    </>
  );
}
export function WeekBars({ data }: { data: Overview["week"] }) {
  const max = Math.max(...data.map((d) => d.orders));
  return (
    <div className="bars num">
      {data.map((d) => (
        <div key={d.day} className={`bar ${d.orders === max ? "is-top" : ""}`}>
          <span className="bar-val">{d.orders}</span>
          <div
            className="bar-fill"
            style={{ height: `${(d.orders / max) * 145}px` }}
          />
          <span className="bar-lbl">{d.day}</span>
        </div>
      ))}
    </div>
  );
}
