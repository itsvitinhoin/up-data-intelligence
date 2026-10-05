import type { ErpData } from "./erp";
export interface RetentionSummary {
  buyers: number | null;
  recurring: number | null;
  rate: number | null;
  ticket: string | number | null;
  weekly: {
    date: string;
    buyers: number | null;
    recurring: number | null;
    rate: number | null;
    ticket: string | number | null;
  }[];
  series: RetentionSummary["weekly"];
}
export type Role = "ADMIN" | "MANAGER" | "VIEWER";
export type Operation = "B2B" | "B2C";
export type DashboardDataMode = "demo" | "read-api-preview" | "live";
export interface Scope {
  tenant_id: string;
  /** Canonical browser workspace identity. Present for every live scope. */
  workspace_operation_id?: string;
  /** Legacy UI workspace alias, never the technical data store ID. */
  store_id: string;
  operation: Operation;
}
export interface Tenant {
  id: string;
  name: string;
  brands: {
    id: string;
    name: string;
    operations: { id: string; type: Operation }[];
  }[];
}
export interface Session {
  id: string;
  name: string;
  role: Role;
  brand_id?: string | null;
  tenant_ids: string[];
  store_ids: string[];
}
export interface Filters {
  days: number;
  from?: string;
  to?: string;
  period?: string;
  channel: string;
  collection: string;
  search?: string;
  state?: string;
  segment?: string;
  media?: string;
}
export interface Metric {
  comparison?: import("@/lib/metric-comparison").MetricComparison;
  comparisonBasis?: "period" | "snapshot";
  comparisonDirection?: "higher" | "lower" | "neutral";
  group?: "Receita" | "Pedidos" | "Clientes" | "Mídia";
  label: string;
  value: string | null;
  format: "currency" | "number" | "percent" | "ratio" | "decimal" | "days";
  displayDigits?: number;
  delta?: number;
  hint: string;
  secondary?: {
    label: string;
    value: string | null;
    hint: string;
    comparison?: import("@/lib/metric-comparison").MetricComparison;
  };
}
export interface Customer {
  id: string;
  name: string | null;
  city: string | null;
  state: string | null;
  orders: number | null;
  requested: string | null;
  fulfilled: string | null;
  lastPurchase: string | null;
  segment: string | null;
  paid: boolean | null;
  firstPurchase: string | null;
}
export interface Order {
  id: string;
  customer_id: string | null;
  date: string;
  requested: string | null;
  fulfilled: string | null;
  requestedQuantity: number | null;
  fulfilledQuantity: number | null;
  status: string | null;
  paid: boolean | null;
}
export interface OrderDetail {
  order: Order;
  customer:
    | (Pick<Customer, "id" | "name" | "city" | "state"> & {
        cnpj: string | null;
        email: string | null;
        phone: string | null;
      })
    | null;
  items: {
    product_id: string | null;
    product_key?: string;
    image?: string | null;
    unitPrice?: string | null;
    name: string | null;
    sku: string | null;
    color: string | null;
    size: string | null;
    requestedQuantity: number | null;
    fulfilledQuantity: number | null;
    requested: string | null;
    fulfilled: string | null;
  }[];
  reconciliation?: {
    requestedOrderAdjustment: string | null;
    fulfilledOrderAdjustment: string | null;
    quantityReconciled: boolean | null;
  };
}
export interface Product {
  reference?: string | null;
  catalog?: {
    basis: "current_source_snapshot";
    snapshot_as_of: string;
    evidence_hash: string;
  } | null;
  category?: string | null;
  active?: boolean | null;
  salePrice?: string | null;
  colorHex?: string | null;
  variantSales?: {
    color: string | null;
    size: string | null;
    units: number | null;
  }[];
  variantSalesBasis?: "observed_line_gross_current_catalog";
  variants?: {
    color: string | null;
    size: string | null;
    sku: string | null;
    stock: number | null;
    hex?: string | null;
  }[];
  id: string;
  name: string | null;
  sku: string | null;
  requested: string | null;
  fulfilled: string | null;
  units: number | null;
  customers: number | null;
  orders: number | null;
  share: number | null;
  sizes: Record<string, boolean> | null;
  abc: string | null;
  views: number | null;
  cart: number | null;
  checkout: number | null;
  stock: number | null;
  sellThrough: number | null;
  turnover: number | null;
  coverage: number | null;
  color: string | null;
  image?: string | null;
  canonicalProductId?: string | null;
  variantId?: string | null;
}
export interface Campaign {
  id: string;
  name: string | null;
  spend: string | null;
  customers: number | null;
  newCustomers: number | null;
  orders: number | null;
  requested: string | null;
  fulfilled: string | null;
  roasRequested: string | null;
  roasFulfilled: string | null;
  cac: string | null;
}
export interface TimelineEvent {
  orderId?: string | null;
  productId?: string | null;
  variantId?: string | null;
  campaignId?: string | null;
  adsetId?: string | null;
  adId?: string | null;
  items?: TimelineEvent[];
  customer_id: string;
  store_id: string;
  id: string;
  type: string;
  date: string;
  title: string;
  detail: string;
  evidence: "DIRECT" | "CUSTOMER_JOURNEY" | "SUPPORTED";
}
export interface Integration {
  id: string;
  name: string;
  type: string;
  endpoint: string;
  account_id?: string;
  status: "CONNECTED" | "PENDING" | "ERROR";
  lastRun: string | null;
  lastError: string | null;
  updated: string;
}
export interface Overview {
  metrics: Metric[];
  b2b?: {
    revenue: Metric[];
    orders: Metric[];
    customers: Metric[];
    media: Metric[];
    relationship: Metric[];
    series: {
      date: string;
      requested: number | null;
      fulfilled: number | null;
      newCustomers: number | null;
      recurringCustomers: number | null;
      mediaRevenue: number | null;
      spend: number | null;
    }[];
    attributedOrders: (Order & { campaign_names: string })[];
  };
  series: {
    date: string;
    requested: number | null;
    fulfilled: number | null;
    orders: number | null;
  }[];
  goal: { requested: number | null; fulfilled: number | null };
  week: { day: string; orders: number }[];
}
export interface Geography {
  approvedWithoutPurchase: number | null;
  conversionRate: number | null;
  fulfilled: number | string | null;
  influencedCustomers: number | null;
  averageTicket: number | null;
  cities: {
    name: string;
    customers: number | null;
    requested: number | string | null;
    fulfilled: number | string | null;
    orders: number | null;
  }[];
  uf: string;
  name: string;
  requested: number | string | null;
  customers: number | null;
  orders: number | null;
  newCustomers: number | null;
}
export interface Retention {
  sequence: string;
  customers: number;
  mean: number | null;
  median: number | null;
  rate: number | null;
  cohorts: { day: number; rate: number | null }[];
}
export interface CustomerDetail {
  marketingTouches?: { first: string | null; last: string | null };
  customer: Customer;
  orders: Order[];
  products: Product[];
  timeline: TimelineEvent[];
  campaigns: Campaign[];
  history_complete: boolean;
}
export const platforms = [
  "UP Zero",
  "Vesti",
  "Nuvemshop",
  "Shopify",
  "Outros",
] as const;
export const erps = ["Miré", "Mansé", "Bling", "Shop9", "Outros"] as const;
export type BrandIntegration = {
  provider: "Plataforma" | "Meta Ads" | "Google Ads" | "TikTok Ads" | "ERP";
  enabled: boolean;
  accountId: string;
};
export interface Company {
  /** Present only on server-catalog brand projections; not a browser authorization grant. */
  tenant_id?: string;
  integrations?: BrandIntegration[];
  /** Server-owned count of verified live connections; setup flags do not count. */
  activeConnections?: number;
  /** Recorded when the brand is first registered; legacy demo brands may lack it. */
  createdAt?: string | null;
  platform?: (typeof platforms)[number] | null;
  erp?: (typeof erps)[number] | null;
  id: string;
  name: string;
  cnpj: string;
  logo: string;
  segment: string;
  operation: "B2B" | "B2C" | "Ambos";
  status?: "ACTIVE" | "PENDING";
  meta_account_id?: string | null;
}
export interface User {
  email?: string;
  phone?: string;
  brand_id?: string | null;
  id: string;
  name: string;
  role: Role;
}
export interface MarketingCreative {
  source?: "real" | "demo";
  previewObservedAt?: string | null;
  evidenceHash?: string;
  id: string;
  campaign_id: string;
  campaign_name: string;
  name: string;
  platform: "Meta Ads";
  placement: string;
  status: string | null;
  preview: string | null;
  format: string;
  spend: number | null;
  impressions: number | null;
  clicks: number | null;
  leads: number | null;
  approved: number | null;
  purchases: number | null;
}
export interface Marketing {
  metrics?: Metric[];
  source?: "real" | "demo";
  summary?: {
    spend: string | null;
    leads: number | null;
    clicks: number | null;
    ctr: string | null;
  };
  creatives: MarketingCreative[];
  campaigns: (Campaign & {
    impressions: number | null;
    clicks: number | null;
    leads: number | null;
    approved: number | null;
    purchases: number | null;
    platform: string;
    status: string | null;
  })[];
  series: {
    date: string;
    spend: number | string | null;
    leads: number | null;
    purchases: number | null;
    revenue: number | string | null;
  }[];
}
export interface Lifecycle {
  stages: {
    stage: number;
    customers: number;
    share: number | null;
    continuation: number | null;
    revenue: number | string | null;
    accumulated: number | string | null;
    meanDays: number | null;
  }[];
  cohorts: { month: string; customers: number; rates: (number | null)[] }[];
  conversion: {
    buckets: { label: string; count: number | null; percent: number | null }[];
    buyers: number | null;
    excluded: number | null;
    mean: number | null;
    median: number | null;
    withinWeek: number | null;
    withinMonth: number | null;
  };
}
export interface Acquisition {
  customers: Customer[];
  firstOrders: Order[];
  buyerCount: number | null;
  confirmedNewCustomers: number | null;
  requested: string | null;
  fulfilled: string | null;
  historyComplete: boolean;
}
export interface LeadSummary {
  leads: number | null;
  approved: number | null;
  converted: number | null;
  qualificationRate: number | null;
  conversionRate: number | null;
}
export interface ResourceMap {
  retail: import("@/services/demo/retail").RetailSummary;
  erp: ErpData;
  retention_summary: RetentionSummary;
  leads: LeadSummary;
  acquisition: Acquisition;
  lifecycle: Lifecycle;
  marketing: Marketing;
  funnel: { label: string; value: number | null }[];
  overview: Overview;
  customers: Customer[];
  orders: Order[];
  products: Product[];
  inventory_products: Product[];
  order_history: Order[];
  campaigns: Campaign[];
  performance: Campaign[];
  integrations: Integration[];
  geography: Geography[];
  retention: Retention[];
  influence: Influence;
  companies: Company[];
  users: User[];
}
export type Resource = keyof ResourceMap;
export interface RequestContext {
  scope: Scope;
  session: Session;
  filters: Filters;
  signal?: AbortSignal;
}
export interface DataApi {
  read<K extends Resource>(
    resource: K,
    context: RequestContext,
  ): Promise<ResourceMap[K]>;
  order(id: string, context: RequestContext): Promise<OrderDetail>;
  product?(id: string, context: RequestContext): Promise<Product>;
  customer(id: string, context: RequestContext): Promise<CustomerDetail>;
  campaign(id: string, context: RequestContext): Promise<CampaignDetail>;
  saveCompany(company: Company, context: RequestContext): Promise<void>;
  saveIntegration(
    integration: Integration,
    context: RequestContext,
  ): Promise<void>;
  saveUser(user: User, context: RequestContext): Promise<void>;
}

export interface Influence {
  customers: Customer[];
  orders: Order[];
  campaigns: Campaign[];
  requested: string | null;
  fulfilled: string | null;
  metrics?: Metric[];
}
export interface CampaignDetail extends Influence {
  campaign: Campaign;
}
