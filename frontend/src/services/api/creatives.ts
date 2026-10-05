/** Independent ad/day source coverage. Monetary transport remains decimal strings. */
import { ApiError } from "./access";
import { validDate } from "@/lib/period";
import type { MarketingCreative } from "@/types/domain";
export type LiveCreative = {
  store_id: string;
  ad_id: string;
  campaign_id: string;
  adset_id: string;
  name: string | null;
  status: string | null;
  creative_id: string | null;
  video_id: string | null;
  preview_url: string | null;
  preview_observed_at: string | null;
  spend: string | null;
  impressions: number | null;
  clicks: number | null;
  link_clicks: number | null;
  ctr: string | null;
  cpa: string | null;
  meta_reported_purchases: string | null;
  meta_reported_purchase_value: string | null;
  reach: null;
  frequency: null;
  basis: "meta_reported_ad_day";
  report_from: string;
  report_to: string;
  evidence_hash: string;
  reporting_definition: {
    level: "ad";
    time_increment: 1;
    action_report_time: "impression" | "conversion" | "mixed";
    action_attribution_windows: string[];
    purchase_action_type: string | null;
    breakdowns: [];
  };
};
const bad = () => new ApiError(503, "Contrato de criativos inválido.");
const obj = (v: unknown): Record<string, unknown> => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw bad();
  return v as Record<string, unknown>;
};
const text = (v: unknown): string | null => {
  if (v === null) return null;
  if (typeof v !== "string" || v.length > 8192 || /[\r\n]/.test(v)) throw bad();
  return v;
};
const identifier = (v: unknown): string => {
  if (typeof v !== "string" || !/^\d{1,200}$/.test(v)) throw bad();
  return v;
};
const money = (v: unknown): string | null => {
  if (v === null) return null;
  if (typeof v !== "string" || !/^\d{1,38}(\.\d{1,38})?$/.test(v)) throw bad();
  return v;
};
const count = (v: unknown): number | null => {
  if (v === null) return null;
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < 0) throw bad();
  return v;
};
export function safeCreativeUrl(v: unknown): string | null {
  if (v === null) return null;
  const value = text(v);
  if (!value) throw bad();
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw bad();
  }
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.hash ||
    (url.port && url.port !== "443") ||
    !["fbcdn.net", "fbsbx.com", "cdninstagram.com"].some(
      (d) => url.hostname === d || url.hostname.endsWith(`.${d}`),
    ) ||
    [...url.searchParams.keys()].some((k) =>
      ["access_token", "token", "api_key", "secret"].includes(k.toLowerCase()),
    ) ||
    value.includes("[REDACTED]")
  )
    throw bad();
  return value;
}
export function parseCreatives(
  value: unknown,
  scope: { store_id: string; report_from: string; report_to: string },
): LiveCreative[] {
  if (!Array.isArray(value) || value.length > 9) throw bad();
  const seen = new Set<string>();
  return value.map((item) => {
    const r = obj(item),
      d = obj(r.reporting_definition);
    if (
      Object.keys(r).some(
        (k) =>
          ![
            "store_id",
            "ad_id",
            "campaign_id",
            "adset_id",
            "name",
            "status",
            "creative_id",
            "video_id",
            "preview_url",
            "preview_observed_at",
            "spend",
            "impressions",
            "clicks",
            "link_clicks",
            "ctr",
            "cpa",
            "meta_reported_purchases",
            "meta_reported_purchase_value",
            "reach",
            "frequency",
            "basis",
            "report_from",
            "report_to",
            "evidence_hash",
            "reporting_definition",
          ].includes(k),
      ) ||
      r.store_id !== scope.store_id ||
      r.basis !== "meta_reported_ad_day" ||
      r.reach !== null ||
      r.frequency !== null ||
      typeof r.report_from !== "string" ||
      typeof r.report_to !== "string" ||
      !validDate(r.report_from) ||
      !validDate(r.report_to) ||
      r.report_from >= r.report_to ||
      r.report_from < scope.report_from ||
      r.report_to > scope.report_to ||
      typeof r.evidence_hash !== "string" ||
      !/^[a-f0-9]{64}$/.test(r.evidence_hash)
    )
      throw bad();
    if (
      Object.keys(d).some(
        (k) =>
          ![
            "level",
            "time_increment",
            "action_report_time",
            "action_attribution_windows",
            "purchase_action_type",
            "breakdowns",
          ].includes(k),
      ) ||
      d.level !== "ad" ||
      d.time_increment !== 1 ||
      !["impression", "conversion", "mixed"].includes(
        String(d.action_report_time),
      ) ||
      !Array.isArray(d.action_attribution_windows) ||
      d.action_attribution_windows.length === 0 ||
      new Set(d.action_attribution_windows).size !==
        d.action_attribution_windows.length ||
      d.action_attribution_windows.some(
        (w) =>
          ![
            "1d_click",
            "7d_click",
            "28d_click",
            "1d_view",
            "7d_view",
            "28d_view",
          ].includes(w),
      ) ||
      !Array.isArray(d.breakdowns) ||
      d.breakdowns.length !== 0 ||
      (d.purchase_action_type !== null &&
        (typeof d.purchase_action_type !== "string" ||
          !/^[a-zA-Z0-9_.]+$/.test(d.purchase_action_type)))
    )
      throw bad();
    const ad_id = identifier(r.ad_id);
    if (seen.has(ad_id)) throw bad();
    seen.add(ad_id);
    const observed = text(r.preview_observed_at);
    if (
      observed !== null &&
      (!/^\d{4}-\d{2}-\d{2}T/.test(observed) ||
        !/(Z|[+]00:00)$/.test(observed) ||
        !Number.isFinite(Date.parse(observed)))
    )
      throw bad();
    if (r.preview_url !== null && observed === null) throw bad();
    const purchases = money(r.meta_reported_purchases),
      cpa = money(r.cpa),
      purchaseValue = money(r.meta_reported_purchase_value);
    if (
      d.purchase_action_type === null &&
      (purchases !== null || cpa !== null || purchaseValue !== null)
    )
      throw bad();
    return {
      store_id: scope.store_id,
      ad_id,
      campaign_id: identifier(r.campaign_id),
      adset_id: identifier(r.adset_id),
      name: text(r.name),
      status: text(r.status),
      creative_id: r.creative_id === null ? null : identifier(r.creative_id),
      video_id: r.video_id === null ? null : identifier(r.video_id),
      preview_url: safeCreativeUrl(r.preview_url),
      preview_observed_at: observed,
      spend: money(r.spend),
      impressions: count(r.impressions),
      clicks: count(r.clicks),
      link_clicks: count(r.link_clicks),
      ctr: money(r.ctr),
      cpa,
      meta_reported_purchases: purchases,
      meta_reported_purchase_value: purchaseValue,
      reach: null,
      frequency: null,
      basis: "meta_reported_ad_day",
      report_from: r.report_from,
      report_to: r.report_to,
      evidence_hash: r.evidence_hash,
      reporting_definition: {
        level: "ad",
        time_increment: 1,
        action_report_time:
          d.action_report_time as LiveCreative["reporting_definition"]["action_report_time"],
        action_attribution_windows: d.action_attribution_windows as string[],
        purchase_action_type: d.purchase_action_type as string | null,
        breakdowns: [],
      },
    };
  });
}
export function creativeView(r: LiveCreative): MarketingCreative {
  const n = (v: string | null) => (v === null ? null : Number(v));
  return {
    id: r.ad_id,
    campaign_id: r.campaign_id,
    campaign_name: `Campanha ${r.campaign_id}`,
    name: r.name ?? `Anúncio ${r.ad_id}`,
    platform: "Meta Ads",
    placement: "Posicionamento indisponível",
    status: r.status,
    preview: r.preview_url,
    format: r.video_id ? "Vídeo" : "Prévia",
    spend: n(r.spend),
    impressions: r.impressions,
    clicks: r.clicks,
    leads: null,
    approved: null,
    purchases: n(r.meta_reported_purchases),
    source: "real",
    previewObservedAt: r.preview_observed_at,
    evidenceHash: r.evidence_hash,
  };
}
