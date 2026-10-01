import type { ErpData } from "./erp";
import type { RetentionSummary } from "@/services/demo/retention-summary";
export type Role = "ADMIN" | "MANAGER" | "VIEWER";
export type Operation = "B2B" | "B2C";
export type DashboardDataMode = "demo" | "read-api-preview";
export interface Scope {
  tenant_id: string;
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
  group?: "Receita" | "Pedidos" | "Clientes" | "Mídia";
  label: string;
  value: string | null;
  format: "currency" | "number" | "percent" | "ratio" | "decimal" | "days";
  displayDigits?: number;
  delta?: number;
  hint: string;
  secondary?: { label: string; value: string | null; hint: string };
}
export interface Customer {
  id: string;
  name: string;
  city: string;
  state: string;
  orders: number;
  requested: string;
  fulfilled: string;
  lastPurchase: string;
  segment: string;
  paid: boolean;
  firstPurchase: string;
}
export interface Order {
  id: string;
  customer_id: string;
  date: string;
  requested: string;
  fulfilled: string;
  requestedQuantity: number;
  fulfilledQuantity: number;
  status: string;
  paid: boolean;
}
export interface OrderDetail {
  order: Order;
  customer: Customer & {
    cnpj: string | null;
    email: string | null;
    phone: string | null;
  };
  items: {
    product_id: string;
    name: string;
    sku: string;
    color: string;
    size: string;
    requestedQuantity: number;
    fulfilledQuantity: number;
    requested: string;
    fulfilled: string;
  }[];
}
export interface Product {
  category?: string | null;
  active?: boolean | null;
  salePrice?: string | null;
  colorHex?: string | null;
  variantSales?: { color: string; size: string; units: number }[];
  variants?: {
    color: string;
    size: string;
    sku: string;
    stock: number | null;
    hex?: string | null;
  }[];
  id: string;
  name: string;
  sku: string;
  requested: string;
  fulfilled: string;
  units: number;
  customers: number;
  orders: number;
  share: number;
  sizes: Record<string, boolean>;
  abc: string;
  views: number;
  cart: number;
  checkout: number;
  stock: number;
  sellThrough: number;
  turnover: number;
  coverage: number;
  color: string;
}
export interface Campaign {
  id: string;
  name: string;
  spend: string;
  customers: number;
  newCustomers: number | null;
  orders: number;
  requested: string;
  fulfilled: string;
  roasRequested: string;
  roasFulfilled: string;
  cac: string | null;
}
export interface TimelineEvent {
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
    requested: number;
    fulfilled: number;
    orders: number;
  }[];
  goal: { requested: number; fulfilled: number };
  week: { day: string; orders: number }[];
}
export interface Geography {
  approvedWithoutPurchase: number | null;
  conversionRate: number | null;
  fulfilled: number;
  influencedCustomers: number;
  averageTicket: number | null;
  cities: {
    name: string;
    customers: number;
    requested: number;
    fulfilled: number;
    orders: number;
  }[];
  uf: string;
  name: string;
  requested: number;
  customers: number;
  orders: number;
  newCustomers: number | null;
}
export interface Retention {
  sequence: string;
  customers: number;
  mean: number | null;
  median: number | null;
  rate: number;
  cohorts: { day: number; rate: number | null }[];
}
export interface CustomerDetail {
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
  id: string;
  campaign_id: string;
  campaign_name: string;
  name: string;
  platform: "Meta Ads";
  placement: string;
  status: "ACTIVE" | "PAUSED";
  preview: string;
  format: string;
  spend: number;
  impressions: number;
  clicks: number;
  leads: number;
  approved: number;
  purchases: number;
}
export interface Marketing {
  creatives: MarketingCreative[];
  campaigns: (Campaign & {
    impressions: number;
    clicks: number;
    leads: number;
    approved: number;
    purchases: number;
    platform: string;
    status: string;
  })[];
  series: {
    date: string;
    spend: number;
    leads: number;
    purchases: number;
    revenue: number;
  }[];
}
export interface Lifecycle {
  stages: {
    stage: number;
    customers: number;
    share: number | null;
    continuation: number | null;
    revenue: number;
    accumulated: number;
    meanDays: number | null;
  }[];
  cohorts: { month: string; customers: number; rates: (number | null)[] }[];
  conversion: {
    buckets: { label: string; count: number; percent: number | null }[];
    buyers: number;
    excluded: number;
    mean: number | null;
    median: number | null;
    withinWeek: number;
    withinMonth: number;
  };
}
export interface Acquisition {
  customers: Customer[];
  firstOrders: Order[];
  buyerCount: number;
  confirmedNewCustomers: number | null;
  requested: string;
  fulfilled: string;
  historyComplete: boolean;
}
export interface LeadSummary {
  leads: number;
  approved: number;
  converted: number;
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
  funnel: { label: string; value: number }[];
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
  requested: string;
  fulfilled: string;
}
export interface CampaignDetail extends Influence {
  campaign: Campaign;
}
