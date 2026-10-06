import { parseCreatives, type LiveCreative } from "./creatives";
import {
  parseOrderDetail,
  parseCatalogEvidence,
  type CatalogEvidence,
  parseProductDetail,
  parseGeography,
  type LiveOrderDetail,
  type LiveProductDetail,
  type LiveGeography,
} from "./product-contracts";
import { parseInstallation } from "./installation";
/** Analytics V1 read transport. Never selected by the demo composition root. */
import {
  parseIntelligence,
  intelligenceResources,
  type IntelligenceResource,
  type IntelligenceResourceMap,
} from "./intelligence";
import { ApiError } from "./access";
import { validDate } from "@/lib/period";

export type LiveScope = {
  tenant_id: string;
  store_id: string;
  operation: "B2B";
};
export type ReadMetadata = {
  contract_version: string;
  store_id: string;
  generation: number;
  policy_hash: string;
  currency: string | null;
  reporting_timezone: string;
  as_of: string;
  report_from: string;
  report_to: string;
  history_complete: boolean;
  facts_complete: boolean;
  limitations: string[];
  publication_domain?: "intelligence";
  analytics_generation?: number;
  publication_id?: string;
  meta_complete?: boolean;
  influence_complete?: boolean;
  customer_intelligence_complete?: boolean;
  performance_complete?: boolean;
};
export type ReadPagination = {
  page_size: number;
  cursor: string | null;
  has_more: boolean;
};
export type ReadEnvelope<T> = {
  data: T;
  pagination: ReadPagination | null;
  metadata: ReadMetadata;
};
export type LiveCustomer = {
  store_id: string;
  customer_id: string;
  customer_type: string | null;
  name: string | null;
  state: string | null;
  city: string | null;
  purchases_observed: number | null;
  first_purchase_at_observed: string | null;
  requested_lifetime_observed: string | null;
  ltv_complete: string | null;
  fulfilled_lifetime_observed?: string | null;
  last_purchase_at_observed?: string | null;
};
export type LiveOrder = {
  store_id: string;
  customer_id: string | null;
  order_id: string;
  created_at: string;
  order_status: string | null;
  payment_status: string | null;
  requested_total: string | null;
  fulfilled_total: string | null;
  requested_items_qty: number | null;
  fulfilled_items_qty: number | null;
};
export type OperationalLeads = {
  leads_generated?: number | null;
  leads_approved?: number | null;
  lead_qualification_rate?: string | null;
  approved_conversion_rate?: string | null;
  approved_converted?: number | null;
};
export type LiveAcquisition = OperationalLeads & {
  buyers_observed: number | null;
  first_purchase_customers_observed: number | null;
  first_purchase_orders_observed: number | null;
  requested_first_purchase_observed: string | null;
  ticket_first_purchase_observed?: string | null;
  fulfilled_first_purchase_observed: string | null;
  confirmed_new_customers: number | null;
};
export type LiveOverview = OperationalLeads & {
  requested_revenue: string | null;
  fulfilled_revenue: string | null;
  average_requested_ticket?: string | null;
  fulfillment_rate: string | null;
  fulfillment_gap: string | null;
  cancelled_requested_revenue: string | null;
  orders_requested: number | null;
  orders_cancelled: number | null;
  buyers_observed: number | null;
  recurring_buyers_observed: number | null;
  purchase_frequency_observed: string | null;
  new_customers_confirmed: number | null;
  ltv_complete: string | null;
  cac: string | null;
  revenue_paid: string | null;
  monthly_customers?: {
    month: string;
    buyers_observed: number | null;
    recurring_buyers_observed: number | null;
    qualifying_orders: number | null;
  }[];
  series: {
    date: string;
    cancelled_requested?: string | null;
    requested: string | null;
    fulfilled: string | null;
    orders: number | null;
    new_customers_confirmed: number | null;
  }[];
};
export type LiveProduct = {
  reference?: string | null;
  catalog?: CatalogEvidence | null;
  store_id: string;
  product_key: string;
  product_id: string | null;
  sku: string | null;
  name: string | null;
  requested_revenue: string | null;
  fulfilled_revenue: string | null;
  units_requested: string | null;
  units_fulfilled: string | null;
  orders_observed: number | null;
  buyers_unique: number | null;
};
export type LiveCustomerDetail = {
  profile: LiveCustomer;
  commercial: {
    qualifying_orders_observed: number | null;
    requested_revenue_observed: string | null;
    fulfilled_revenue_observed: string | null;
    first_purchase_at_observed: string | null;
    last_purchase_at_observed: string | null;
    ltv_complete: string | null;
  };
};
export type LiveRetention = {
  recurring_fulfilled_observed?: string | null;
  recurring_orders_observed?: number | null;
  repeat_mean_days_observed?: number | null;
  repeat_median_days_observed?: number | null;
  purchase_stages?: {
    stage: number;
    buyers_observed: number;
    share_observed: string | null;
    continuation_observed: string | null;
    requested_revenue_observed: string | null;
    accumulated_requested_revenue_observed: string | null;
    mean_days_observed: number | null;
  }[];
  series?: {
    date: string;
    buyers_observed: number | null;
    recurring_buyers_observed: number | null;
    retention_observed: string | null;
    retention_ticket_observed: string | null;
  }[];
  buyers_observed: number | null;
  recurring_buyers_observed: number | null;
  retention_observed: string | null;
  retention_ticket_observed: string | null;
  frequency_observed: string | null;
  progression: {
    from_purchase: number;
    to_purchase: string;
    customers_reached_observed: number;
    continuation_observed: string | null;
    mean_days_observed: number | null;
    median_days_observed: number | null;
  }[];
  cohorts: {
    cohort_month: string;
    reporting_month: string;
    month: number | null;
    buyers_observed: number | null;
    rate: string | null;
    observed_rate: string | null;
    period_complete: boolean;
  }[];
};
export type LiveFunnel = {
  session_to_purchase_rate?: string | null;
  totals: Record<string, number | null>;
  session_to_cart_rate: string | null;
  cart_to_checkout_rate: string | null;
  checkout_to_purchase_rate: string | null;
  days: { date: string; [key: string]: string | number | null }[];
};
type ObjectRow = Record<string, unknown>;
const invalid = () => new ApiError(502, "Resposta inválida da API de leitura.");
function object(value: unknown): ObjectRow {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw invalid();
  return value as ObjectRow;
}
function text(value: unknown): string {
  if (typeof value !== "string" || !value) throw invalid();
  return value;
}
function nullableText(value: unknown): string | null {
  return value === null ? null : text(value);
}
function decimal(value: unknown): string | null {
  if (value === null) return null;
  if (typeof value !== "string" || !/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value))
    throw invalid();
  return value;
}
function count(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw invalid();
  return value;
}
function flag(value: unknown): boolean {
  if (typeof value !== "boolean") throw invalid();
  return value;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw invalid();
  return value;
}
export function parseMetadata(value: unknown, scope?: LiveScope): ReadMetadata {
  const row = object(value),
    generation = count(row.generation);
  if (
    (scope !== undefined && row.store_id !== scope.store_id) ||
    row.contract_version !== "1.0.0" ||
    generation === null ||
    generation < 1 ||
    typeof row.report_from !== "string" ||
    !validDate(row.report_from) ||
    typeof row.report_to !== "string" ||
    !validDate(row.report_to) ||
    row.report_from >= row.report_to ||
    typeof row.policy_hash !== "string" ||
    !/^[a-f0-9]{64}$/.test(row.policy_hash)
  )
    throw invalid();
  const intelligence: Partial<ReadMetadata> = {};
  if (row.publication_domain !== undefined) {
    if (
      row.publication_domain !== "intelligence" ||
      count(row.analytics_generation) === null ||
      !Number.isSafeInteger(row.analytics_generation) ||
      typeof row.publication_id !== "string" ||
      !/^[a-f0-9]{64}$/.test(row.publication_id)
    )
      throw invalid();
    intelligence.publication_domain = "intelligence";
    intelligence.analytics_generation = Number(row.analytics_generation);
    intelligence.publication_id = row.publication_id;
    intelligence.meta_complete = flag(row.meta_complete);
    intelligence.influence_complete = flag(row.influence_complete);
    intelligence.customer_intelligence_complete = flag(
      row.customer_intelligence_complete,
    );
    intelligence.performance_complete = flag(row.performance_complete);
  }
  return {
    ...intelligence,
    contract_version: text(row.contract_version),
    store_id: text(row.store_id),
    generation,
    policy_hash: row.policy_hash,
    currency: nullableText(row.currency),
    reporting_timezone: text(row.reporting_timezone),
    as_of: text(row.as_of),
    report_from: text(row.report_from),
    report_to: text(row.report_to),
    history_complete: flag(row.history_complete),
    facts_complete: flag(row.facts_complete),
    limitations: array(row.limitations).map(text),
  };
}
/** Decode a same-origin bridge response after the server has resolved the store binding. */
export function decodeOverviewEnvelope(
  value: unknown,
): ReadEnvelope<LiveOverview> {
  const payload = object(value);
  const metadata = parseMetadata(payload.metadata);
  const data = parseOverview(payload.data);
  if (
    !metadata.history_complete &&
    (data.new_customers_confirmed !== null || data.ltv_complete !== null)
  )
    throw invalid();
  return { data, pagination: parsePagination(payload.pagination), metadata };
}
function parsePagination(value: unknown): ReadPagination | null {
  if (value === null) return null;
  const row = object(value),
    size = count(row.page_size);
  if (size === null || size < 1 || size > 100) throw invalid();
  const cursor = nullableText(row.cursor),
    hasMore = flag(row.has_more);
  if (hasMore !== (cursor !== null)) throw invalid();
  return { page_size: size, cursor, has_more: hasMore };
}
function parseCustomer(value: unknown, scope: LiveScope): LiveCustomer {
  const row = object(value);
  if (row.store_id !== scope.store_id) throw invalid();
  return {
    store_id: text(row.store_id),
    customer_id: text(row.customer_id),
    customer_type: nullableText(row.customer_type),
    name: nullableText(row.name),
    state: nullableText(row.state),
    city: nullableText(row.city),
    purchases_observed: count(row.purchases_observed),
    fulfilled_lifetime_observed:
      row.fulfilled_lifetime_observed === undefined
        ? null
        : decimal(row.fulfilled_lifetime_observed),
    last_purchase_at_observed:
      row.last_purchase_at_observed === undefined
        ? null
        : nullableText(row.last_purchase_at_observed),
    first_purchase_at_observed: nullableText(row.first_purchase_at_observed),
    requested_lifetime_observed: decimal(row.requested_lifetime_observed),
    ltv_complete: decimal(row.ltv_complete),
  };
}
function parseOrder(
  value: unknown,
  scope: LiveScope,
  customerId?: string,
): LiveOrder {
  const row = object(value);
  if (
    row.store_id !== scope.store_id ||
    (customerId !== undefined && row.customer_id !== customerId)
  )
    throw invalid();
  return {
    store_id: text(row.store_id),
    customer_id: nullableText(row.customer_id),
    order_id: text(row.order_id),
    created_at: text(row.created_at),
    order_status: nullableText(row.order_status),
    payment_status: nullableText(row.payment_status),
    requested_total: decimal(row.requested_total),
    fulfilled_total: decimal(row.fulfilled_total),
    requested_items_qty: count(row.requested_items_qty),
    fulfilled_items_qty: count(row.fulfilled_items_qty),
  };
}
function parseLeads(row: Record<string, unknown>): OperationalLeads {
  return {
    leads_generated: count(row.leads_generated ?? null),
    leads_approved: count(row.leads_approved ?? null),
    lead_qualification_rate: decimal(row.lead_qualification_rate ?? null),
    approved_conversion_rate: decimal(row.approved_conversion_rate ?? null),
    approved_converted: count(row.approved_converted ?? null),
  };
}
function parseOverview(value: unknown): LiveOverview {
  const row = object(value);
  return {
    ...parseLeads(row),
    requested_revenue: decimal(row.requested_revenue),
    fulfilled_revenue: decimal(row.fulfilled_revenue),
    average_requested_ticket: decimal(row.average_requested_ticket ?? null),
    fulfillment_rate: decimal(row.fulfillment_rate),
    fulfillment_gap: decimal(row.fulfillment_gap),
    cancelled_requested_revenue: decimal(row.cancelled_requested_revenue),
    orders_requested: count(row.orders_requested),
    orders_cancelled: count(row.orders_cancelled),
    buyers_observed: count(row.buyers_observed),
    recurring_buyers_observed: count(row.recurring_buyers_observed),
    purchase_frequency_observed: decimal(row.purchase_frequency_observed),
    new_customers_confirmed: count(row.new_customers_confirmed),
    ltv_complete: decimal(row.ltv_complete),
    cac: decimal(row.cac),
    revenue_paid: decimal(row.revenue_paid),
    monthly_customers: array(row.monthly_customers ?? []).map((item) => {
      const r = object(item);
      return {
        month: text(r.month),
        buyers_observed: count(r.buyers_observed),
        recurring_buyers_observed: count(r.recurring_buyers_observed),
        qualifying_orders: count(r.qualifying_orders),
      };
    }),
    series: array(row.series).map((item) => {
      const point = object(item);
      return {
        date: text(point.date),
        cancelled_requested: decimal(point.cancelled_requested ?? null),
        requested: decimal(point.requested),
        fulfilled: decimal(point.fulfilled),
        orders: count(point.orders),
        new_customers_confirmed: count(point.new_customers_confirmed),
      };
    }),
  };
}
function parseAcquisition(value: unknown): LiveAcquisition {
  const row = object(value);
  return {
    ...parseLeads(row),
    buyers_observed: count(row.buyers_observed),
    first_purchase_customers_observed: count(
      row.first_purchase_customers_observed,
    ),
    first_purchase_orders_observed: count(row.first_purchase_orders_observed),
    requested_first_purchase_observed: decimal(
      row.requested_first_purchase_observed,
    ),
    ticket_first_purchase_observed: decimal(
      row.ticket_first_purchase_observed ?? null,
    ),
    fulfilled_first_purchase_observed: decimal(
      row.fulfilled_first_purchase_observed,
    ),
    confirmed_new_customers: count(row.confirmed_new_customers),
  };
}
function parseCustomerDetail(
  value: unknown,
  scope: LiveScope,
  id: string,
): LiveCustomerDetail {
  const row = object(value),
    profile = parseCustomer(row.profile, scope),
    commercial = object(row.commercial);
  if (profile.customer_id !== id) throw invalid();
  return {
    profile,
    commercial: {
      qualifying_orders_observed: count(commercial.qualifying_orders_observed),
      requested_revenue_observed: decimal(
        commercial.requested_revenue_observed,
      ),
      fulfilled_revenue_observed: decimal(
        commercial.fulfilled_revenue_observed,
      ),
      first_purchase_at_observed: nullableText(
        commercial.first_purchase_at_observed,
      ),
      last_purchase_at_observed: nullableText(
        commercial.last_purchase_at_observed,
      ),
      ltv_complete: decimal(commercial.ltv_complete),
    },
  };
}

export type ReadResourceMap = IntelligenceResourceMap & {
  overview: LiveOverview;
  orders: LiveOrder[];
  order: LiveOrderDetail;
  acquisition: LiveAcquisition;
  customers: LiveCustomer[];
  customer: LiveCustomerDetail;
  customerOrders: LiveOrder[];
  retention: LiveRetention;
  products: LiveProduct[];
  product: LiveProductDetail;
  funnel: LiveFunnel;
  geography: LiveGeography;
  creatives: LiveCreative[];
};
export type ReadResource = keyof ReadResourceMap;
export function decodeReadEnvelope<K extends ReadResource>(
  resource: K,
  value: unknown,
  customerId?: string,
): ReadEnvelope<ReadResourceMap[K]> {
  const payload = object(value),
    meta = parseMetadata(payload.metadata);
  const scope: LiveScope = {
    tenant_id: "bridge-validated",
    store_id: meta.store_id,
    operation: "B2B",
  };
  if (intelligenceResources.includes(resource as IntelligenceResource)) {
    if (meta.publication_domain !== "intelligence") throw invalid();
    const data = parseIntelligence(
      resource as IntelligenceResource,
      payload.data,
      customerId,
    );
    const pagination = parsePagination(payload.pagination);
    if (!["customer360", "performance"].includes(resource) && !pagination)
      throw invalid();
    if (
      !meta.history_complete &&
      resource === "performance" &&
      (object(payload.data).new_customers_influenced !== null ||
        object(payload.data).cac_new_customer !== null)
    )
      throw invalid();
    return { data: data as ReadResourceMap[K], pagination, metadata: meta };
  }
  const parsers: {
    [R in Exclude<ReadResource, IntelligenceResource>]: (
      value: unknown,
    ) => ReadResourceMap[R];
  } = {
    overview: parseOverview,
    acquisition: parseAcquisition,
    customers: (v) => array(v).map((item) => parseCustomer(item, scope)),
    orders: (v) => array(v).map((item) => parseOrder(item, scope)),
    customerOrders: (v) => {
      if (!customerId) throw invalid();
      return array(v).map((item) => parseOrder(item, scope, customerId));
    },
    customer: (v) => {
      if (!customerId) throw invalid();
      return parseCustomerDetail(v, scope, customerId);
    },
    retention: parseRetention,
    products: (v) => array(v).map((item) => parseProduct(item, scope)),
    funnel: parseFunnel,
    order: (v) => {
      if (!customerId) throw invalid();
      return parseOrderDetail(v, scope, customerId, parseOrder);
    },
    product: (v) => {
      if (!customerId) throw invalid();
      return parseProductDetail(v, scope, customerId, parseProduct);
    },
    geography: parseGeography,
    creatives: (v) => parseCreatives(v, meta),
  };
  const data = parsers[resource as Exclude<ReadResource, IntelligenceResource>](
    payload.data,
  ) as ReadResourceMap[K];
  const pagination = parsePagination(payload.pagination);
  if (
    ["orders", "customers", "customerOrders", "products"].includes(resource) &&
    !pagination
  )
    throw invalid();
  if (!meta.history_complete) {
    // Validate history-dependent values after their concrete DTO parsers have run.
    if (resource === "overview") decodeOverviewEnvelope(payload);
    if (
      resource === "acquisition" &&
      parseAcquisition(payload.data).confirmed_new_customers !== null
    )
      throw invalid();
    if (
      resource === "customers" &&
      array(payload.data).some(
        (v) => parseCustomer(v, scope).ltv_complete !== null,
      )
    )
      throw invalid();
    if (resource === "customer") {
      const detail = parseCustomerDetail(payload.data, scope, customerId!);
      if (
        detail.profile.ltv_complete !== null ||
        detail.commercial.ltv_complete !== null
      )
        throw invalid();
    }
  }
  return { data, pagination, metadata: meta };
}
function parseProduct(value: unknown, scope: LiveScope): LiveProduct {
  const row = object(value);
  if (row.store_id !== scope.store_id) throw invalid();
  return {
    store_id: text(row.store_id),
    product_key: text(row.product_key),
    ...(row.reference === undefined
      ? {}
      : { reference: nullableText(row.reference) }),
    ...(row.catalog === undefined
      ? {}
      : { catalog: parseCatalogEvidence(row.catalog) }),
    product_id: nullableText(row.product_id),
    sku: nullableText(row.sku),
    name: nullableText(row.name),
    requested_revenue: decimal(row.requested_revenue),
    fulfilled_revenue: decimal(row.fulfilled_revenue),
    units_requested: decimal(row.units_requested),
    units_fulfilled: decimal(row.units_fulfilled),
    orders_observed: count(row.orders_observed),
    buyers_unique: count(row.buyers_unique),
  };
}
function nullableNumber(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) throw invalid();
  return value;
}
function finiteOrNull(v: unknown): number | null {
  if (v === null) return null;
  if (typeof v !== "number" || !Number.isFinite(v) || v < 0)
    throw new ApiError(502, "Intervalo observado inválido.");
  return v;
}
function parseRetention(value: unknown): LiveRetention {
  const row = object(value);
  return {
    repeat_mean_days_observed: finiteOrNull(
      row.repeat_mean_days_observed ?? null,
    ),
    repeat_median_days_observed: finiteOrNull(
      row.repeat_median_days_observed ?? null,
    ),
    recurring_fulfilled_observed: decimal(
      row.recurring_fulfilled_observed ?? null,
    ),
    recurring_orders_observed: count(row.recurring_orders_observed ?? null),
    ...(row.purchase_stages === undefined
      ? {}
      : {
          purchase_stages: array(row.purchase_stages).map((v) => {
            const s = object(v),
              stage = count(s.stage),
              buyers = count(s.buyers_observed);
            if (stage === null || stage < 1 || stage > 5 || buyers === null)
              throw invalid();
            return {
              stage,
              buyers_observed: buyers,
              share_observed: decimal(s.share_observed),
              continuation_observed: decimal(s.continuation_observed),
              requested_revenue_observed: decimal(s.requested_revenue_observed),
              accumulated_requested_revenue_observed: decimal(
                s.accumulated_requested_revenue_observed,
              ),
              mean_days_observed: nullableNumber(s.mean_days_observed),
            };
          }),
        }),
    ...(row.series === undefined
      ? {}
      : {
          series: array(row.series).map((v) => {
            const p = object(v);
            return {
              date: text(p.date),
              buyers_observed: count(p.buyers_observed),
              recurring_buyers_observed: count(p.recurring_buyers_observed),
              retention_observed: decimal(p.retention_observed),
              retention_ticket_observed: decimal(p.retention_ticket_observed),
            };
          }),
        }),
    buyers_observed: count(row.buyers_observed),
    recurring_buyers_observed: count(row.recurring_buyers_observed),
    retention_observed: decimal(row.retention_observed),
    retention_ticket_observed: decimal(row.retention_ticket_observed),
    frequency_observed: decimal(row.frequency_observed),
    progression: array(row.progression).map((value) => {
      const step = object(value),
        reached = count(step.customers_reached_observed),
        from = count(step.from_purchase);
      if (reached === null || from === null) throw invalid();
      return {
        from_purchase: from,
        to_purchase: text(step.to_purchase),
        customers_reached_observed: reached,
        continuation_observed: decimal(step.continuation_observed),
        mean_days_observed: nullableNumber(step.mean_days_observed),
        median_days_observed: nullableNumber(step.median_days_observed),
      };
    }),
    cohorts: array(row.cohorts).map((value) => {
      const cohort = object(value),
        complete = flag(cohort.period_complete);
      const rate = decimal(cohort.rate),
        observed = decimal(cohort.observed_rate);
      if (!complete && (rate !== null || observed !== null)) throw invalid();
      return {
        cohort_month: text(cohort.cohort_month),
        reporting_month: text(cohort.reporting_month),
        month: count(cohort.month),
        buyers_observed: count(cohort.buyers_observed),
        rate,
        observed_rate: observed,
        period_complete: complete,
      };
    }),
  };
}
const funnelFields = [
  "sessions",
  "product_views",
  "add_to_cart",
  "checkout_started",
  "purchase",
  "sessions_with_cart",
  "sessions_cart_then_checkout",
  "sessions_cart_checkout_purchase",
  "sessions_with_purchase",
  "events_without_session",
] as const;
function parseFunnel(value: unknown): LiveFunnel {
  const row = object(value),
    totals = object(row.totals);
  return {
    totals: Object.fromEntries([
      ...funnelFields.map((field) => [field, count(totals[field])]),
      ["purchase_item", count(totals.purchase_item ?? null)],
    ]),
    session_to_purchase_rate: decimal(row.session_to_purchase_rate ?? null),
    session_to_cart_rate: decimal(row.session_to_cart_rate),
    cart_to_checkout_rate: decimal(row.cart_to_checkout_rate),
    checkout_to_purchase_rate: decimal(row.checkout_to_purchase_rate),
    days: array(row.days).map((value) => {
      const day = object(value);
      return {
        date: text(day.date),
        ...Object.fromEntries(
          funnelFields.map((field) => [field, count(day[field])]),
        ),
      };
    }),
  };
}
export type ReadOptions = {
  from?: string;
  to?: string;
  pageSize?: number;
  cursor?: string;
  status?: string;
  firstPurchase?: boolean;
  signal?: AbortSignal;
};
export function createHttpApi(baseUrl: string, fetcher: typeof fetch = fetch) {
  const base = new URL(baseUrl);
  if (!["http:", "https:"].includes(base.protocol))
    throw new Error("Invalid read API URL");
  async function request<T>(
    path: string,
    scope: LiveScope,
    decode: (value: unknown) => T,
    options: ReadOptions = {},
  ): Promise<ReadEnvelope<T>> {
    if (!scope.tenant_id || !scope.store_id || scope.operation !== "B2B")
      throw invalid();
    const url = new URL(path, base);
    url.searchParams.set("tenant_id", scope.tenant_id);
    url.searchParams.set("operation", scope.operation);
    if (!path.startsWith("/v1/stores/"))
      url.searchParams.set("store_id", scope.store_id);
    if (options.from) url.searchParams.set("from", options.from);
    if (options.to) url.searchParams.set("to", options.to);
    if (options.pageSize !== undefined)
      url.searchParams.set("page_size", String(options.pageSize));
    if (options.cursor) url.searchParams.set("cursor", options.cursor);
    if (options.status) url.searchParams.set("status", options.status);
    if (options.firstPurchase !== undefined)
      url.searchParams.set("first_purchase", String(options.firstPurchase));
    const response = await fetcher(url, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: options.signal,
    });
    if (!response.ok)
      throw new ApiError(response.status, "Falha na leitura do dashboard.");
    const payload = object(await response.json());
    return {
      data: decode(payload.data),
      pagination: parsePagination(payload.pagination),
      metadata: parseMetadata(payload.metadata, scope),
    };
  }
  return {
    installation: async (
      scope: LiveScope,
      options: { signal?: AbortSignal } = {},
    ) => {
      if (!scope.tenant_id || !scope.store_id || scope.operation !== "B2B")
        throw invalid();
      const url = new URL(
        `/v1/stores/${encodeURIComponent(scope.store_id)}/installation`,
        base,
      );
      url.searchParams.set("tenant_id", scope.tenant_id);
      url.searchParams.set("operation", scope.operation);
      const response = await fetcher(url, {
        method: "GET",
        credentials: "include",
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: options.signal,
      });
      if (!response.ok)
        throw new ApiError(
          response.status,
          "Estado de instalação indisponível.",
        );
      return parseInstallation(await response.json(), scope.store_id);
    },
    intelligence: async <K extends IntelligenceResource>(
      resource: K,
      scope: LiveScope,
      entity?: string,
      options?: ReadOptions,
    ) => {
      const paths: Record<IntelligenceResource, string> = {
        performance: "/v1/performance",
        campaigns: "/v1/campaigns",
        campaign: `/v1/campaigns/${encodeURIComponent(entity ?? "")}`,
        campaignCustomers: `/v1/campaigns/${encodeURIComponent(entity ?? "")}/customers`,
        campaignOrders: `/v1/campaigns/${encodeURIComponent(entity ?? "")}/orders`,
        customer360: `/v1/customers/${encodeURIComponent(entity ?? "")}/intelligence`,
        timeline: `/v1/customers/${encodeURIComponent(entity ?? "")}/timeline`,
        customerProducts: `/v1/customers/${encodeURIComponent(entity ?? "")}/products`,
        customerCampaigns: `/v1/customers/${encodeURIComponent(entity ?? "")}/campaigns`,
        influencedOrders: "/v1/orders/influenced",
        influencedCustomers: "/v1/customers/influenced",
      };
      const response = await request(paths[resource], scope, (v) => v, options);
      return decodeReadEnvelope(resource, response, entity);
    },
    orders: async (scope: LiveScope, options?: ReadOptions) => {
      const response = await request(
        "/v1/orders",
        scope,
        (value) => array(value).map((item) => parseOrder(item, scope)),
        options,
      );
      if (!response.pagination) throw invalid();
      return response;
    },
    order: (scope: LiveScope, id: string, options?: ReadOptions) =>
      request(
        `/v1/orders/${encodeURIComponent(id)}`,
        scope,
        (v) => parseOrderDetail(v, scope, id, parseOrder),
        options,
      ),
    product: (scope: LiveScope, id: string, options?: ReadOptions) =>
      request(
        `/v1/products/${encodeURIComponent(id)}`,
        scope,
        (v) => parseProductDetail(v, scope, id, parseProduct),
        options,
      ),
    acquisition: (scope: LiveScope, options?: ReadOptions) =>
      request("/v1/acquisition", scope, parseAcquisition, options),
    creatives: (scope: LiveScope, options?: ReadOptions) =>
      request("/v1/creatives", scope, (v) => v, options).then((r) =>
        decodeReadEnvelope("creatives", r),
      ),
    geography: (scope: LiveScope, options?: ReadOptions) =>
      request("/v1/geography", scope, parseGeography, options),
    overview: async (scope: LiveScope, options?: ReadOptions) => {
      const response = await request(
        `/v1/stores/${encodeURIComponent(scope.store_id)}/overview`,
        scope,
        parseOverview,
        options,
      );
      if (
        !response.metadata.history_complete &&
        (response.data.new_customers_confirmed !== null ||
          response.data.ltv_complete !== null)
      )
        throw invalid();
      return response;
    },
    customers: async (scope: LiveScope, options?: ReadOptions) => {
      const response = await request(
        "/v1/customers",
        scope,
        (value) => array(value).map((item) => parseCustomer(item, scope)),
        options,
      );
      if (
        !response.metadata.history_complete &&
        response.data.some((row) => row.ltv_complete !== null)
      )
        throw invalid();
      if (!response.pagination) throw invalid();
      return response;
    },
    customer: async (scope: LiveScope, id: string, options?: ReadOptions) => {
      const response = await request(
        `/v1/customers/${encodeURIComponent(id)}`,
        scope,
        (value) => parseCustomerDetail(value, scope, id),
        options,
      );
      if (
        !response.metadata.history_complete &&
        (response.data.profile.ltv_complete !== null ||
          response.data.commercial.ltv_complete !== null)
      )
        throw invalid();
      return response;
    },
    customerOrders: async (
      scope: LiveScope,
      id: string,
      options?: ReadOptions,
    ) => {
      const response = await request(
        `/v1/customers/${encodeURIComponent(id)}/orders`,
        scope,
        (value) => array(value).map((item) => parseOrder(item, scope, id)),
        options,
      );
      if (!response.pagination) throw invalid();
      return response;
    },
    retention: (scope: LiveScope, options?: ReadOptions) =>
      request("/v1/retention", scope, parseRetention, options),
    products: async (scope: LiveScope, options?: ReadOptions) => {
      const response = await request(
        "/v1/products",
        scope,
        (value) => array(value).map((item) => parseProduct(item, scope)),
        options,
      );
      if (!response.pagination) throw invalid();
      return response;
    },
    funnel: (scope: LiveScope, options?: ReadOptions) =>
      request("/v1/funnel", scope, parseFunnel, options),
  };
}

/** Nullable presentation projection; never cast an envelope to demo Customer[]. */
export function customerCard(row: LiveCustomer) {
  return {
    id: row.customer_id,
    name: row.name,
    state: row.state,
    city: row.city,
    ordersObserved: row.purchases_observed,
    requestedObserved: row.requested_lifetime_observed,
    fulfilledObserved: null,
    completeLtv: row.ltv_complete,
  };
}
