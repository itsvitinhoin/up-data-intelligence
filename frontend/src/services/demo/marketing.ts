import { periodDays } from "@/lib/period";
import type {
  Marketing,
  MarketingCreative,
  RequestContext,
} from "@/services/demo/types";
import {
  campaignsFor,
  factor,
  hasDemoData,
  influenceFor,
  total,
} from "./business";

const creativeNames = [
  "Essenciais da estação",
  "Alfaiataria em movimento",
  "Sua próxima coleção",
  "Novas combinações",
  "Detalhes que vendem",
  "Seleção da semana",
];
/** Synthetic Meta-like ad grain. Never connects to Meta or uses client media. */
export function marketingFor(c: RequestContext): Marketing {
  if (!hasDemoData(c) || !["all", "meta"].includes(c.filters.channel))
    return { creatives: [], campaigns: [], series: [] };
  const coveredDays = periodDays(c.filters).filter(
    (day) => day >= "2026-09-01" && day <= "2026-09-30",
  );
  if (!coveredDays.length) return { creatives: [], campaigns: [], series: [] };
  const campaigns = campaignsFor(c);
  const influence = influenceFor(c);
  const weight = (factor(c) * coveredDays.length) / 30;
  const creatives: MarketingCreative[] = campaigns.flatMap((campaign, ci) =>
    [0, 1].map((ai) => {
      const i = ci * 2 + ai;
      const impressions = Math.round((96000 + i * 21300) * weight);
      const clicks = Math.round(impressions * (0.011 + i * 0.003));
      const leads = Math.floor(clicks / (9 + i * 2));
      const approved = Math.floor(leads * (0.48 + i * 0.035));
      const purchases = Math.floor(approved * 0.4);
      const firstCents = Math.round(Number(campaign.spend) * 100 * 0.6);
      return {
        id: `${c.scope.store_id}:creative-${i}`,
        campaign_id: campaign.id,
        campaign_name: campaign.name,
        name: creativeNames[i],
        platform: "Meta Ads" as const,
        placement: ai === 0 ? "Instagram" : "Facebook",
        status: i === 5 ? ("PAUSED" as const) : ("ACTIVE" as const),
        preview: `/demo-creatives/editorial-${i % 3}.svg`,
        format: ai === 0 ? "Imagem" : "Carrossel",
        spend:
          (ai === 0
            ? firstCents
            : Math.round(Number(campaign.spend) * 100) - firstCents) / 100,
        impressions,
        clicks,
        leads,
        approved,
        purchases,
      };
    }),
  );
  const sums = (
    key:
      "spend" | "leads" | "approved" | "purchases" | "impressions" | "clicks",
  ) => creatives.reduce((sum, row) => sum + row[key], 0);
  const distribute = (value: number, day: number, scale = 1) =>
    (Math.round((value * scale * (day + 1)) / coveredDays.length) -
      Math.round((value * scale * day) / coveredDays.length)) /
    scale;
  return {
    creatives,
    campaigns: campaigns.map((campaign) => {
      const ads = creatives.filter((ad) => ad.campaign_id === campaign.id);
      return {
        ...campaign,
        impressions: ads.reduce((s, a) => s + a.impressions, 0),
        clicks: ads.reduce((s, a) => s + a.clicks, 0),
        leads: ads.reduce((s, a) => s + a.leads, 0),
        approved: ads.reduce((s, a) => s + a.approved, 0),
        purchases: ads.reduce((s, a) => s + a.purchases, 0),
        platform: "Meta Ads",
        status: ads.some((a) => a.status === "ACTIVE") ? "ACTIVE" : "PAUSED",
      };
    }),
    series: periodDays(c.filters).map((date) => {
      const i = coveredDays.indexOf(date);
      return {
        date,
        spend: i < 0 ? 0 : distribute(sums("spend"), i, 100),
        leads: i < 0 ? 0 : distribute(sums("leads"), i),
        purchases: i < 0 ? 0 : distribute(sums("purchases"), i),
        revenue: Number(
          total(
            influence.orders.filter((o) => o.date === date),
            "fulfilled",
          ),
        ),
      };
    }),
  };
}
