/** Complete synthetic fixtures retain their explicit contract. Live view models stay nullable. */
import type * as View from "@/types/domain";
export type * from "@/types/domain";
export { platforms, erps } from "@/types/domain";
type Known<T> = { [K in keyof T]: NonNullable<T[K]> };
export type Customer = Known<View.Customer>;
export type Order = Known<View.Order>;
export type Product = Omit<
  View.Product,
  | "name"
  | "sku"
  | "requested"
  | "fulfilled"
  | "units"
  | "customers"
  | "orders"
  | "share"
  | "sizes"
  | "abc"
  | "views"
  | "cart"
  | "checkout"
  | "stock"
  | "sellThrough"
  | "turnover"
  | "coverage"
  | "color"
> &
  Known<
    Pick<
      View.Product,
      | "name"
      | "sku"
      | "requested"
      | "fulfilled"
      | "units"
      | "customers"
      | "orders"
      | "share"
      | "sizes"
      | "abc"
      | "views"
      | "cart"
      | "checkout"
      | "stock"
      | "sellThrough"
      | "turnover"
      | "coverage"
      | "color"
    >
  >;
export type Campaign = Omit<
  View.Campaign,
  | "name"
  | "spend"
  | "customers"
  | "orders"
  | "requested"
  | "fulfilled"
  | "roasRequested"
  | "roasFulfilled"
> &
  Known<
    Pick<
      View.Campaign,
      | "name"
      | "spend"
      | "customers"
      | "orders"
      | "requested"
      | "fulfilled"
      | "roasRequested"
      | "roasFulfilled"
    >
  >;
export type OrderDetail = Omit<
  View.OrderDetail,
  "order" | "customer" | "items"
> & {
  order: Order;
  customer: Customer & {
    cnpj: string | null;
    email: string | null;
    phone: string | null;
  };
  items: (Omit<
    View.OrderDetail["items"][number],
    | "product_id"
    | "name"
    | "sku"
    | "color"
    | "size"
    | "requestedQuantity"
    | "fulfilledQuantity"
    | "requested"
    | "fulfilled"
  > &
    Known<
      Pick<
        View.OrderDetail["items"][number],
        | "product_id"
        | "name"
        | "sku"
        | "color"
        | "size"
        | "requestedQuantity"
        | "fulfilledQuantity"
        | "requested"
        | "fulfilled"
      >
    >)[];
};
export type CustomerDetail = Omit<
  View.CustomerDetail,
  "customer" | "orders" | "products" | "campaigns"
> & {
  customer: Customer;
  orders: Order[];
  products: Product[];
  campaigns: Campaign[];
};
export type Influence = Omit<
  View.Influence,
  "customers" | "orders" | "campaigns"
> & {
  customers: Customer[];
  orders: Order[];
  campaigns: Campaign[];
  requested: string;
  fulfilled: string;
};
export type CampaignDetail = Influence & { campaign: Campaign };
export type ResourceMap = Omit<
  View.ResourceMap,
  | "customers"
  | "orders"
  | "products"
  | "inventory_products"
  | "order_history"
  | "campaigns"
  | "performance"
  | "influence"
  | "geography"
  | "leads"
  | "lifecycle"
  | "acquisition"
  | "retention"
  | "marketing"
> & {
  marketing: Marketing;
  customers: Customer[];
  orders: Order[];
  products: Product[];
  inventory_products: Product[];
  retention: (Omit<View.Retention, "rate"> & { rate: number })[];
  geography: Geography[];
  leads: LeadSummary;
  lifecycle: Lifecycle;
  acquisition: Acquisition;
  order_history: Order[];
  campaigns: Campaign[];
  performance: Campaign[];
  influence: Influence;
};
export type DataApi = Omit<
  View.DataApi,
  "read" | "order" | "customer" | "campaign"
> & {
  read<K extends View.Resource>(
    resource: K,
    context: View.RequestContext,
  ): Promise<ResourceMap[K]>;
  order(id: string, context: View.RequestContext): Promise<OrderDetail>;
  customer(id: string, context: View.RequestContext): Promise<CustomerDetail>;
  campaign(id: string, context: View.RequestContext): Promise<CampaignDetail>;
};

export type Geography = Omit<
  View.Geography,
  | "requested"
  | "fulfilled"
  | "influencedCustomers"
  | "cities"
  | "customers"
  | "orders"
> & {
  requested: number;
  fulfilled: number;
  influencedCustomers: number;
  customers: number;
  orders: number;
  cities: {
    name: string;
    customers: number;
    requested: number;
    fulfilled: number;
    orders: number;
  }[];
};
export type LeadSummary = Omit<
  View.LeadSummary,
  "leads" | "approved" | "converted"
> & { leads: number; approved: number; converted: number };
export type Lifecycle = Omit<View.Lifecycle, "stages" | "conversion"> & {
  stages: (Omit<View.Lifecycle["stages"][number], "revenue" | "accumulated"> & {
    revenue: number;
    accumulated: number;
  })[];
  conversion: Omit<
    View.Lifecycle["conversion"],
    "buckets" | "buyers" | "excluded" | "withinWeek" | "withinMonth"
  > & {
    buckets: { label: string; count: number; percent: number | null }[];
    buyers: number;
    excluded: number;
    withinWeek: number;
    withinMonth: number;
  };
};
export type Acquisition = Omit<
  View.Acquisition,
  "customers" | "firstOrders" | "buyerCount" | "requested" | "fulfilled"
> & {
  customers: Customer[];
  firstOrders: Order[];
  buyerCount: number;
  requested: string;
  fulfilled: string;
};

export type MarketingCreative = Known<View.MarketingCreative>;
export type Marketing = Omit<
  View.Marketing,
  "campaigns" | "series" | "creatives"
> & {
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
};
