/** Forms describe capabilities only; credential values are never definitions. */
export type ProviderDefinition = {
  id: string;
  category: "Commerce" | "Mídia" | "ERP" | "Analytics";
  label: string;
  implemented: boolean;
  credentialStrategy: "pinned-upzero" | "global-meta" | null;
};
export const integrationProviders: readonly ProviderDefinition[] = [
  {
    id: "upzero",
    category: "Commerce",
    label: "UP Zero",
    implemented: true,
    credentialStrategy: "pinned-upzero",
  },
  {
    id: "nuvemshop",
    category: "Commerce",
    label: "Nuvemshop",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "shopify",
    category: "Commerce",
    label: "Shopify",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "braavo",
    category: "Commerce",
    label: "Braavo",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "meta",
    category: "Mídia",
    label: "Meta Ads",
    implemented: true,
    credentialStrategy: "global-meta",
  },
  {
    id: "google",
    category: "Mídia",
    label: "Google Ads",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "tiktok",
    category: "Mídia",
    label: "TikTok Ads",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "manse",
    category: "ERP",
    label: "Mansé",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "miredata",
    category: "ERP",
    label: "Miredata",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "shop9",
    category: "ERP",
    label: "Shop9",
    implemented: false,
    credentialStrategy: null,
  },
  {
    id: "ga4",
    category: "Analytics",
    label: "GA4",
    implemented: false,
    credentialStrategy: null,
  },
];
