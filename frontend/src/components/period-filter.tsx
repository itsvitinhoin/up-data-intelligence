"use client";
import { useInstallation } from "@/hooks/use-installation";
import { useState } from "react";
import { usePathname } from "next/navigation";
import { activePageState, isB2BReadPage } from "@/lib/dashboard-source";
import { CalendarDays } from "lucide-react";
import { useWorkspace } from "@/features/providers";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  dateRange,
  displayRange,
  periodError,
  periodPresets,
  presetRange,
  exclusiveToInclusive,
} from "@/lib/period";
export function PeriodFilter() {
  const { filters, setFilters, dataMode, scope, dashboardPageState } =
    useWorkspace();
  const path = usePathname();
  const previewRoute =
    isB2BReadPage(path) && scope?.operation === "B2B" && dataMode !== "demo";
  const current = activePageState(path, dataMode, scope, dashboardPageState);
  const installation = useInstallation();
  const available = installation.data?.data.available_window;
  const coverage =
    current?.metadata ??
    (available
      ? {
          report_from: available.from,
          report_to: available.to,
          reporting_timezone: installation.data!.metadata.reporting_timezone,
        }
      : undefined);
  const pendingCoverage =
    previewRoute && current?.source !== "demo" && !coverage;
  const lastClosed = coverage ? exclusiveToInclusive(coverage.report_to) : null;
  const range =
    coverage && !filters.from && !filters.to
      ? { from: coverage.report_from, to: lastClosed!, days: 0 }
      : dateRange(filters);
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);
  const [preset, setPreset] = useState(filters.period ?? "30");
  const error =
    periodError(from, to) ??
    (coverage && (from < coverage.report_from || to > lastClosed!)
      ? installation.data
        ? "Histórico deste período ainda está sendo processado."
        : "Período fora da cobertura publicada."
      : null);
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (value) {
          setFrom(range.from);
          setTo(range.to);
          setPreset(filters.period ?? "30");
        }
        setOpen(value);
      }}
    >
      <DialogTrigger asChild>
        <button
          className="range glass period-trigger"
          disabled={pendingCoverage}
          aria-label={
            pendingCoverage
              ? "Aguardando cobertura publicada"
              : `Filtrar período: ${displayRange(range.from, range.to)}`
          }
        >
          <CalendarDays />
          <span>
            <small>Período</small>
            {pendingCoverage
              ? "Aguardando cobertura"
              : displayRange(range.from, range.to)}
          </span>
        </button>
      </DialogTrigger>
      <DialogContent className="glass period-dialog">
        <DialogTitle>Filtrar período</DialogTitle>
        <DialogDescription>
          {coverage
            ? `Datas inclusivas · ${coverage.reporting_timezone}. Cobertura: ${displayRange(coverage.report_from, lastClosed!)}.`
            : "Datas inclusivas · America/Sao_Paulo. Referência demonstrativa: 30/09/2026."}
        </DialogDescription>
        <div className="period-presets">
          {periodPresets.map(([key, label]) => (
            <button
              key={key}
              className="chip"
              aria-pressed={preset === key}
              onClick={() => {
                setPreset(key);
                if (key !== "custom") {
                  const next = presetRange(key, lastClosed ?? undefined);
                  setFrom(next.from);
                  setTo(next.to);
                }
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="period-inputs">
          <label>
            Data de início
            <Input
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => {
                setPreset("custom");
                setFrom(e.target.value);
              }}
            />
          </label>
          <label>
            Data de fim
            <Input
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => {
                setPreset("custom");
                setTo(e.target.value);
              }}
            />
          </label>
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-300">
            {error}
          </p>
        )}
        <Button
          className="btn"
          disabled={!!error}
          onClick={() => {
            if (error) return;
            const days = dateRange({ ...filters, from, to }).days;
            setFilters({ ...filters, from, to, days, period: preset });
            setOpen(false);
          }}
        >
          Aplicar período
        </Button>
      </DialogContent>
    </Dialog>
  );
}
