/** Official all-days platform report. No commercial attribution substitution. */
import { ApiError } from "./access";
import type { ReadMetadata } from "./http";
import type { Campaign } from "@/types/domain";
const money = [
  "spend",
  "frequency",
  "ctr",
  "cpc",
  "cpm",
  "meta_reported_purchases",
  "meta_reported_purchase_value",
  "cpa",
  "roas",
] as const;
const counts = ["impressions", "reach", "clicks", "link_clicks"] as const;
const texts = [
  "campaign_name",
  "adset_name",
  "ad_name",
  "campaign_status",
  "adset_status",
  "ad_status",
  "creative_id",
  "preview_url",
] as const;
export type MetaPeriodRow = Record<(typeof money)[number], string | null> &
  Record<(typeof counts)[number], number | null> &
  Record<(typeof texts)[number], string | null> & {
    level: "account" | "campaign" | "adset" | "ad";
    campaign_id: string | null;
    adset_id: string | null;
    ad_id: string | null;
  };
export type LiveMetaAds = {
  series:
    | {
        date: string;
        spend: string | null;
        meta_reported_purchases: string | null;
        meta_reported_purchase_value: string | null;
        roas: string | null;
      }[]
    | null;
  summary: MetaPeriodRow;
  campaigns: MetaPeriodRow[];
  adsets: MetaPeriodRow[];
  ads: MetaPeriodRow[];
  basis: "official_meta_all_days";
  report_from: string;
  report_to: string;
  purchase_action_type: string;
};
const bad = (): never => {
  throw new ApiError(503, "Contrato do período Meta inválido.");
};
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return bad();
  return v as Record<string, unknown>;
}
function row(v: unknown, level: MetaPeriodRow["level"]): MetaPeriodRow {
  const r = object(v),
    keys = [
      ...money,
      ...counts,
      ...texts,
      "level",
      "campaign_id",
      "adset_id",
      "ad_id",
    ];
  if (
    r.level !== level ||
    Object.keys(r).length !== keys.length ||
    keys.some((k) => !(k in r))
  )
    return bad();
  for (const k of money)
    if (
      r[k] !== null &&
      (typeof r[k] !== "string" ||
        !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(r[k] as string))
    )
      return bad();
  for (const k of counts)
    if (
      r[k] !== null &&
      (typeof r[k] !== "number" ||
        !Number.isSafeInteger(r[k]) ||
        (r[k] as number) < 0)
    )
      return bad();
  const present = { account: 0, campaign: 1, adset: 2, ad: 3 }[level];
  ["campaign_id", "adset_id", "ad_id"].forEach((k, i) => {
    if (
      i < present
        ? typeof r[k] !== "string" || !/^\d+$/.test(r[k] as string)
        : r[k] !== null
    )
      bad();
  });
  for (const k of texts)
    if (
      r[k] !== null &&
      (typeof r[k] !== "string" ||
        (r[k] as string).length > 8192 ||
        /[\u0000-\u001f]/.test(r[k] as string))
    )
      return bad();
  if (r.creative_id !== null && !/^\d+$/.test(r.creative_id as string))
    return bad();
  if (r.preview_url !== null) {
    let u: URL;
    try {
      u = new URL(r.preview_url as string);
    } catch {
      return bad();
    }
    if (
      u.protocol !== "https:" ||
      u.username ||
      u.password ||
      u.hash ||
      (u.port && u.port !== "443") ||
      !["fbcdn.net", "fbsbx.com", "cdninstagram.com"].some(
        (d) => u.hostname === d || u.hostname.endsWith("." + d),
      )
    )
      return bad();
    if (
      [...u.searchParams.keys()].some((k) =>
        ["access_token", "token", "api_key", "secret"].includes(
          k.toLowerCase(),
        ),
      )
    )
      return bad();
  }
  return r as MetaPeriodRow;
}
export function parseMetaAds(v: unknown, metadata: ReadMetadata): LiveMetaAds {
  const r = object(v),
    keys = [
      "series",
      "summary",
      "campaigns",
      "adsets",
      "ads",
      "basis",
      "report_from",
      "report_to",
      "purchase_action_type",
    ];
  if (
    Object.keys(r).length !== keys.length ||
    keys.some((k) => !(k in r)) ||
    r.basis !== "official_meta_all_days" ||
    typeof r.report_from !== "string" ||
    typeof r.report_to !== "string" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(r.report_from) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(r.report_to) ||
    r.report_from < metadata.report_from ||
    r.report_to > metadata.report_to ||
    r.report_from >= r.report_to ||
    typeof r.purchase_action_type !== "string" ||
    !/^[a-zA-Z0-9_.]+$/.test(r.purchase_action_type)
  )
    return bad();
  function list(
    key: "campaigns" | "adsets" | "ads",
    level: MetaPeriodRow["level"],
  ) {
    if (!Array.isArray(r[key]) || r[key].length > 1000) return bad();
    const rows = r[key].map((v) => row(v, level));
    if (
      new Set(rows.map((r) => [r.campaign_id, r.adset_id, r.ad_id].join("/")))
        .size !== rows.length
    )
      return bad();
    return rows;
  }
  let series: LiveMetaAds["series"] = null;
  if (r.series !== null) {
    if (!Array.isArray(r.series) || r.series.length > 1000) return bad();
    const dates = new Set<string>();
    series = r.series.map((value) => {
      const point = object(value);
      const keys = [
        "date",
        "spend",
        "meta_reported_purchases",
        "meta_reported_purchase_value",
        "roas",
      ];
      if (
        Object.keys(point).length !== keys.length ||
        keys.some((k) => !(k in point)) ||
        typeof point.date !== "string" ||
        !/^\d{4}-\d{2}-\d{2}$/.test(point.date) ||
        point.date < (r.report_from as string) ||
        point.date >= (r.report_to as string) ||
        dates.has(point.date)
      )
        return bad();
      dates.add(point.date);
      for (const k of keys.slice(1))
        if (
          point[k] !== null &&
          (typeof point[k] !== "string" ||
            !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(point[k] as string))
        )
          return bad();
      return point as LiveMetaAds["series"] extends (infer P)[] | null
        ? P
        : never;
    });
  }
  return {
    series,
    summary: row(r.summary, "account"),
    campaigns: list("campaigns", "campaign"),
    adsets: list("adsets", "adset"),
    ads: list("ads", "ad"),
    basis: "official_meta_all_days",
    report_from: r.report_from,
    report_to: r.report_to,
    purchase_action_type: r.purchase_action_type,
  };
}
export function metaCampaignView(r: MetaPeriodRow): Campaign {
  if (r.level !== "campaign" || !r.campaign_id) return bad();
  return {
    id: r.campaign_id,
    name: r.campaign_name,
    spend: r.spend,
    requested: null,
    fulfilled: null,
    customers: null,
    newCustomers: null,
    orders: null,
    roasRequested: null,
    roasFulfilled: null,
    cac: null,
  };
}
