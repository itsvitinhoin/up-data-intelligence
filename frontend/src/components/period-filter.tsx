"use client";
import { useState } from "react";
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
} from "@/lib/period";
export function PeriodFilter() {
  const { filters, setFilters } = useWorkspace();
  const range = dateRange(filters);
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);
  const [preset, setPreset] = useState(filters.period ?? "30");
  const error = periodError(from, to);
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
          aria-label={`Filtrar período: ${displayRange(range.from, range.to)}`}
        >
          <CalendarDays />
          <span>
            <small>Período</small>
            {displayRange(range.from, range.to)}
          </span>
        </button>
      </DialogTrigger>
      <DialogContent className="glass period-dialog">
        <DialogTitle>Filtrar período</DialogTitle>
        <DialogDescription>
          Datas inclusivas · America/Sao_Paulo. Referência demonstrativa:
          30/09/2026.
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
                  const next = presetRange(key);
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
