"use client";
import { B2BReadBoundary } from "@/hooks/use-dashboard-read";

import { MetricComparisonLine } from "@/components/metric-comparison";
import type { Metric } from "@/types/domain";
import { ListExport } from "@/components/exports";
import { useState } from "react";
import Link from "next/link";
import { useWorkspace } from "@/features/providers";
import BrazilMap from "@svg-maps/brazil";
const Brazil = BrazilMap as {
  viewBox: string;
  locations: { id: string; name: string; path: string }[];
};
import { useResource } from "@/hooks/use-resource";
import {
  PageHead,
  Panel,
  Loading,
  Failure,
  Choice,
  Notice,
} from "@/components/ui-kit";
import { FiltersBar } from "@/components/shell";
import { money, number, metric as formatMetric } from "@/lib/format";
type GeoMetric =
  | "requested"
  | "fulfilled"
  | "customers"
  | "orders"
  | "newCustomers"
  | "influencedCustomers";
function DemoGeographyPage() {
  const q = useResource("geography");
  const { filters, setFilters, dataMode } = useWorkspace();
  const live = dataMode !== "demo";
  const [metric, setMetric] = useState<GeoMetric>("requested");
  const [selected, setSelected] = useState("SP");
  const [points, setPoints] = useState(false);
  const values = q.data ?? [];
  const max = Math.max(1, ...values.map((r) => Number(r[metric] ?? 0)));
  const current = values.find((r) => r.uf === selected);
  const format = (n: number | string | null | undefined) =>
    n == null
      ? "Sem cobertura"
      : ["requested", "fulfilled"].includes(metric)
        ? money(n)
        : number(n);
  return (
    <>
      <PageHead
        eyebrow="Inteligência geográfica"
        title={
          <>
            Seu negócio, <em className="hl hl--up">em todo o Brasil.</em>
          </>
        }
        description="Concentração comercial pelo endereço de entrega dos pedidos no período, sem inferir localização ausente."
      />
      <FiltersBar />
      <Panel
        title="Distribuição por estado"
        action={
          <Choice
            label="Métrica do mapa"
            value={metric}
            onChange={(v) => setMetric(v as GeoMetric)}
            options={[
              { value: "requested", label: "Receita Solicitada" },
              { value: "fulfilled", label: "Receita Atendida" },
              {
                value: "influencedCustomers",
                label: live
                  ? "Clientes influenciados · não certificado"
                  : "Clientes influenciados por mídia",
                disabled: live,
              },
              { value: "customers", label: "Clientes" },
              { value: "orders", label: "Pedidos" },
              {
                value: "newCustomers",
                label: live
                  ? "Novos clientes · sem histórico integral"
                  : "Novos clientes",
                disabled: live,
              },
            ]}
          />
        }
      >
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <Failure retry={() => void q.refetch()} />
        ) : (
          <div className="geo-layout">
            <div>
              <label className="map-toggle">
                <input
                  type="checkbox"
                  checked={points}
                  onChange={(e) => setPoints(e.target.checked)}
                />
                Pontos de concentração estadual
              </label>
              <svg
                viewBox={Brazil.viewBox}
                className="brazil-map"
                aria-label="Mapa do Brasil. Selecione um estado."
              >
                {Brazil.locations.map((location) => {
                  const record = values.find(
                    (r) => r.uf === location.id.toUpperCase(),
                  );
                  const v = record?.[metric];
                  return (
                    <path
                      key={location.id}
                      d={location.path}
                      role="button"
                      tabIndex={0}
                      aria-label={`${location.name}: ${format(v)}`}
                      aria-pressed={selected === location.id.toUpperCase()}
                      onClick={() => setSelected(location.id.toUpperCase())}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelected(location.id.toUpperCase());
                        }
                      }}
                      fill={
                        v == null
                          ? "rgba(255,255,255,.04)"
                          : `rgba(4,88,254,${0.18 + (0.72 * Number(v)) / max})`
                      }
                      stroke={
                        selected === location.id.toUpperCase()
                          ? "#B9D2FF"
                          : "#24304F"
                      }
                      strokeWidth={
                        selected === location.id.toUpperCase() ? 2.2 : 1
                      }
                    >
                      <title>
                        {location.name} · {format(v)}
                      </title>
                    </path>
                  );
                })}
                {points &&
                  values
                    .filter((v) => v[metric] != null)
                    .map((v) => {
                      const centers: Record<string, [number, number]> = {
                        SP: [380, 485],
                        RJ: [447, 470],
                        MG: [445, 420],
                        PR: [330, 511],
                        SC: [347, 549],
                        RS: [310, 583],
                        GO: [357, 386],
                        BA: [494, 330],
                      };
                      const center = centers[v.uf];
                      return center ? (
                        <circle
                          key={v.uf}
                          cx={center[0]}
                          cy={center[1]}
                          r={3 + Math.sqrt(Number(v[metric] ?? 0) / max) * 10}
                          fill="#B5CEFF"
                          opacity=".75"
                          pointerEvents="none"
                        />
                      ) : null;
                    })}
              </svg>
              <div className="map-legend">
                <span>Menor</span>
                <i />
                <span>Maior concentração</span>
              </div>
              <p className="metric-hint">
                Pontos representam estados, não endereços de clientes. Mapa:{" "}
                <a
                  href="https://mapsvg.com/maps/brazil"
                  target="_blank"
                  rel="noreferrer"
                >
                  MapSVG
                </a>{" "}
                / @svg-maps,{" "}
                <a
                  href="https://creativecommons.org/licenses/by/4.0/"
                  target="_blank"
                  rel="noreferrer"
                >
                  CC BY 4.0
                </a>
                . Cores e marcadores adaptados.
              </p>
            </div>
            <div>
              <div className="selected-state">
                <span className="eyebrow">{selected}</span>
                <h3>
                  {current?.name ??
                    Brazil.locations.find(
                      (l) => l.id === selected.toLowerCase(),
                    )?.name}
                </h3>
                <strong className="metric-value">
                  {format(current?.[metric])}
                </strong>
              </div>
              <dl className="detail-list" aria-label="Resumo do estado">
                {q
                  .compare((rows) => {
                    const state = rows.find((r) => r.uf === selected);
                    return (
                      [
                        ["Clientes", state?.customers, "number"],
                        ["Receita Solicitada", state?.requested, "currency"],
                        ["Receita Atendida", state?.fulfilled, "currency"],
                        ["Pedidos", state?.orders, "number"],
                        [
                          "Ticket médio solicitado",
                          state?.averageTicket,
                          "currency",
                        ],
                        [
                          "Cadastros Aprovados (Sem Compra)",
                          state?.approvedWithoutPurchase,
                          "number",
                        ],
                        ["% de Conversão", state?.conversionRate, "percent"],
                      ] as [
                        string,
                        string | number | null | undefined,
                        Metric["format"],
                      ][]
                    ).map(([label, value, format]) => ({
                      label,
                      value: value == null ? null : String(value),
                      format,
                      hint: "Mesmo estado e mesmos filtros no período anterior.",
                    }));
                  })
                  .map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>
                        {formatMetric(item.value, item.format)}
                        <MetricComparisonLine item={item} />
                      </dd>
                    </div>
                  ))}
              </dl>
              <p className="metric-hint mb-4">
                {live
                  ? "Geografia de entrega dos pedidos observados no período. Cadastros aprovados e conversão por estado ainda não certificados. O filtro de clientes usa o endereço atual do cadastro."
                  : "Cadastros da marca no período, aprovados até o fim do recorte. Conversão: aprovados com compra qualificante após aprovação / aprovados do mesmo estado. Todas as origens; sem filtro de coleção. Base demonstrativa."}
              </p>
              {current && (
                <Link
                  className="btn btn--glass mb-4"
                  href="/b2b/customers"
                  onClick={() =>
                    setFilters({
                      ...filters,
                      state: selected,
                      search: "",
                      segment: "all",
                      media: "all",
                    })
                  }
                >
                  Ver clientes de {selected}
                </Link>
              )}
              <h3 className="card-title">Principais cidades</h3>
              <ListExport
                rows={current?.cities ?? []}
                name={`cidades-${selected}`}
              />
              <div className="geo-ranking">
                {current?.cities
                  .toSorted(
                    (a, b) =>
                      Number(b.requested ?? -1) - Number(a.requested ?? -1),
                  )
                  .map((city) => (
                    <div className="py-3 text-xs" key={city.name}>
                      <strong>{city.name}</strong>
                      <p className="muted">
                        {number(city.customers)} clientes ·{" "}
                        {number(city.orders)} pedidos · {money(city.requested)}
                      </p>
                    </div>
                  ))}
                {!current && (
                  <p className="muted">Sem cobertura neste estado.</p>
                )}
              </div>
              <h3 className="card-title">Maior concentração</h3>
              <ListExport
                rows={values.toSorted(
                  (a, b) => Number(b[metric] ?? -1) - Number(a[metric] ?? -1),
                )}
                name="estados"
              />
              <div className="geo-ranking">
                {values
                  .toSorted(
                    (a, b) => Number(b[metric] ?? -1) - Number(a[metric] ?? -1),
                  )
                  .map((r, i) => (
                    <button
                      key={r.uf}
                      onClick={() => setSelected(r.uf)}
                      aria-pressed={selected === r.uf}
                    >
                      <span className="muted">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span>
                        {r.name}
                        <small>{r.uf}</small>
                      </span>
                      <strong>{format(r[metric])}</strong>
                    </button>
                  ))}
              </div>
            </div>
          </div>
        )}
      </Panel>
      {metric === "newCustomers" && (
        <Notice>
          Novos clientes não confirmados: o histórico comercial completo ainda
          não foi demonstrado.
        </Notice>
      )}
    </>
  );
}

export function GeographyPage() {
  return (
    <B2BReadBoundary>
      <DemoGeographyPage />
    </B2BReadBoundary>
  );
}
