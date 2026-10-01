"use client";
import {
  ArrowUpRight,
  ArrowDownRight,
  Info,
  RefreshCw,
  SearchX,
} from "lucide-react";
import { Tooltip } from "radix-ui";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { metric } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Metric } from "@/types/domain";
export function Panel({
  title,
  subtitle,
  action,
  children,
  className,
}: {
  title: React.ReactNode;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("glass card", className)}>
      <div className="card-head">
        <div>
          <h2 className="card-title">{title}</h2>
          {subtitle && <p className="card-sub">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}
export function PageHead({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: React.ReactNode;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <div className="eyebrow">
          <span className="dot" />
          {eyebrow}
        </div>
        <h1>{title}</h1>
        <p className="lede">{description}</p>
      </div>
      {action}
    </header>
  );
}
export function Choice({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger aria-label={label} className="select">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
export function MetricCard({
  item,
  index = 0,
}: {
  item: Metric;
  index?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.035, 0.25) }}
    >
      <Card className="glass metric">
        <div className="metric-top">
          <span className="metric-label">{item.label}</span>
          <Tooltip.Provider delayDuration={150}>
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <button
                  type="button"
                  className="metric-info"
                  aria-label={`Sobre ${item.label}`}
                >
                  <Info size={15} />
                </button>
              </Tooltip.Trigger>
              <Tooltip.Portal>
                <Tooltip.Content
                  className="metric-tooltip glass"
                  sideOffset={8}
                >
                  {item.hint}
                  {item.secondary?.hint && (
                    <p className="mt-2">
                      {item.secondary.label}: {item.secondary.hint}
                    </p>
                  )}
                  <Tooltip.Arrow />
                </Tooltip.Content>
              </Tooltip.Portal>
            </Tooltip.Root>
          </Tooltip.Provider>
        </div>
        <div className="metric-value num">
          {metric(item.value, item.format, item.displayDigits)}
        </div>
        <div className="metric-row">
          {item.delta !== undefined ? (
            <span
              className={cn(
                "delta",
                item.delta >= 0 ? "delta--good" : "delta--bad",
              )}
            >
              {item.delta >= 0 ? (
                <ArrowUpRight size={13} />
              ) : (
                <ArrowDownRight size={13} />
              )}{" "}
              {Math.abs(item.delta).toLocaleString("pt-BR")}%
            </span>
          ) : (
            <span className="metric-hint">
              {item.value === null ? "Não confirmado" : "Base observada"}
            </span>
          )}
          {item.delta !== undefined && (
            <span className="metric-hint">vs. período anterior</span>
          )}
        </div>
        {item.secondary && (
          <div className="metric-secondary" title={item.secondary.hint}>
            <span>{item.secondary.label}</span>
            <strong className="num">
              {metric(item.secondary.value, "currency")}
            </strong>
            {item.secondary.value === null && <small>Não confirmado</small>}
          </div>
        )}
        <svg className="spark" viewBox="0 0 220 38" aria-hidden="true">
          <path
            d={
              index % 2
                ? "M0 33 L20 31 L40 34 L60 20 L80 25 L100 15 L120 19 L140 8 L160 12 L180 5 L220 0"
                : "M0 30 L20 28 L40 30 L60 18 L80 22 L100 14 L120 18 L140 6 L160 10 L180 5 L220 0"
            }
            fill="none"
            stroke={item.value === null ? "var(--line-hi)" : "var(--up-hi)"}
            strokeWidth="1.5"
          />
        </svg>
      </Card>
    </motion.div>
  );
}
export function Notice({
  children,
  kind = "info",
}: {
  children: React.ReactNode;
  kind?: "info" | "warn";
}) {
  return (
    <div className={`alert alert--${kind}`}>
      <span className="alert-ic">
        <Info />
      </span>
      <div className="alert-body">{children}</div>
    </div>
  );
}
export function Loading() {
  return (
    <div className="metrics" role="status" aria-label="Carregando dados">
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-44 rounded-[20px] bg-white/5" />
      ))}
    </div>
  );
}
export function Empty({
  title = "Nenhum resultado neste recorte",
  description = "Experimente ajustar os filtros para encontrar outros registros.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      <SearchX size={30} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function Failure({
  retry,
  description,
}: {
  retry: () => void;
  description?: string;
}) {
  return (
    <div role="alert" className="empty-state">
      <h2>Não foi possível carregar os dados.</h2>
      <p>
        {description ?? "Tente novamente. A seleção de empresa foi preservada."}
      </p>
      <Button className="btn" onClick={retry}>
        <RefreshCw size={15} />
        Tentar novamente
      </Button>
    </div>
  );
}
