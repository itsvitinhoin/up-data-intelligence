import { productView } from "@/services/api/live-presenters";
import { describe, expect, it, vi } from "vitest";
import { createHttpApi, decodeReadEnvelope } from "@/services/api/http";
import { liveRead, type PrivateCaller } from "@/services/auth/bff.server";
const scope = {
  tenant_id: "synthetic-tenant",
  store_id: "synthetic-store",
  operation: "B2B" as const,
};
const metadata = {
  contract_version: "1.0.0",
  store_id: scope.store_id,
  generation: 6,
  policy_hash: "a".repeat(64),
  currency: "BRL",
  reporting_timezone: "America/Sao_Paulo",
  as_of: "2026-10-05T03:00:00Z",
  report_from: "2026-09-01",
  report_to: "2026-10-05",
  history_complete: false,
  facts_complete: true,
  limitations: [],
};
const order = {
  store_id: scope.store_id,
  order_id: "order-synthetic",
  customer_id: null,
  created_at: "2026-09-01T12:00:00Z",
  order_status: "CANCELED",
  payment_status: "unpaid",
  requested_total: "8.99",
  fulfilled_total: "0.00",
  requested_items_qty: 3,
  fulfilled_items_qty: 0,
};
const detail = {
  order,
  customer: null,
  items: [
    {
      item_id: "item-synthetic",
      product_key: "d".repeat(64),
      product_id: null,
      asset_id: null,
      variant_id: "variant-synthetic",
      name: null,
      sku: "SKU",
      image: null,
      color: null,
      size: null,
      status: "removed",
      requested_quantity: "3",
      fulfilled_quantity: "0",
      unit_price: "3.33",
      requested_value: "9.99",
      fulfilled_value: "0.00",
    },
  ],
  reconciliation: {
    item_value_basis: "line_gross_at_current_unit_price",
    gross_requested: "9.99",
    gross_fulfilled: "0.00",
    requested_order_adjustment: "-1.00",
    fulfilled_order_adjustment: "0.00",
    quantity_reconciled: true,
  },
};
const envelope = (data: unknown) => ({ data, metadata, pagination: null });
const product = {
  store_id: scope.store_id,
  product_key: "d".repeat(64),
  product_id: null,
  name: null,
  sku: "SKU",
  image: null,
  variant_id: "variant-synthetic",
  requested_revenue: "9.99",
  fulfilled_revenue: "0.00",
  units_requested: "3",
  units_fulfilled: "0",
  orders_observed: 1,
  buyers_unique: 1,
  stock: null,
  sizes: null,
  colors: null,
  abc: null,
  sell_through: null,
  revenue_basis: "line_gross_at_current_unit_price",
};
describe("real drill-down contracts", () => {
  it("keeps exact decimals, canceled status and nullable customer/product identity", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(envelope(detail)));
    const api = createHttpApi("https://read.example.test", fetcher);
    const result = await api.order(scope, order.order_id);
    expect(result.data).toMatchObject(detail);
    expect(fetcher.mock.calls[0][0].pathname).toBe(
      "/v1/orders/order-synthetic",
    );
    expect(result.data.items[0].product_id).toBeNull();
    expect(result.data.customer).toBeNull();
  });
  it("rejects foreign order identity/store, float money and duplicate items", () => {
    for (const data of [
      { ...detail, order: { ...order, store_id: "foreign" } },
      { ...detail, order: { ...order, order_id: "foreign" } },
      { ...detail, order: { ...order, requested_total: 8.99 } },
      { ...detail, items: [...detail.items, ...detail.items] },
    ])
      expect(() =>
        decodeReadEnvelope("order", envelope(data), order.order_id),
      ).toThrow();
  });
  it("preserves a missing reconciliation proof as null", () => {
    const parsed = decodeReadEnvelope(
      "order",
      envelope({
        ...detail,
        reconciliation: {
          ...detail.reconciliation,
          quantity_reconciled: null,
          gross_requested: null,
        },
      }),
      order.order_id,
    );
    expect(parsed.data.reconciliation.quantity_reconciled).toBeNull();
    expect(parsed.data.reconciliation.gross_requested).toBeNull();
  });
  it("routes by canonical product_key without fabricating stock/name/image/grade", () => {
    const parsed = decodeReadEnvelope(
      "product",
      envelope(product),
      product.product_key,
    );
    expect(parsed.data).toEqual(product);
    expect(() =>
      decodeReadEnvelope("product", envelope(product), "e".repeat(64)),
    ).toThrow();
    expect(() =>
      decodeReadEnvelope(
        "product",
        envelope({ ...product, stock: 0 }),
        product.product_key,
      ),
    ).toThrow();
  });
  it("validates shipping coverage and unknown geography without inferring a state", () => {
    const data = {
      states: [],
      coverage: {
        basis: "order_shipping_location",
        orders_observed: 1,
        mapped_orders: 0,
        unmapped_orders: 1,
        orders_without_customer: 1,
      },
    };
    expect(decodeReadEnvelope("geography", envelope(data)).data).toEqual(data);
    expect(() =>
      decodeReadEnvelope(
        "geography",
        envelope({ ...data, coverage: { ...data.coverage, mapped_orders: 1 } }),
      ),
    ).toThrow();
  });
  it("checks workspace grant before forwarding a detail and never trusts a browser store", async () => {
    // The private API is the authoritative gate before constructing a business reader.
    const caller = vi
      .fn<PrivateCaller>()
      .mockResolvedValue(
        Response.json(
          { error: { code: "workspace_access_denied" } },
          { status: 403 },
        ),
      );
    const response = await liveRead(
      new Request(
        "https://web.example.test/api/dashboard/orders/order-synthetic?tenant_id=synthetic-tenant&workspace_operation_id=foreign&operation=B2B",
        { headers: { cookie: "__Host-up_session=verified-synthetic" } },
      ),
      "order",
      order.order_id,
      caller,
    );
    expect(response.status).toBe(403);
    expect(caller).toHaveBeenCalledTimes(1);
    expect(caller.mock.calls[0][1]).toContain(
      "/v1/dashboard/orders/order-synthetic?",
    );
  });
});

describe("certified current catalog mapping", () => {
  const catalog = {
    basis: "current_source_snapshot",
    snapshot_as_of: "2026-10-05T03:00:00Z",
    evidence_hash: "b".repeat(64),
  };
  it("preserves current labels and exact stock decimals without inventing a complete grade", () => {
    const parsed = decodeReadEnvelope(
      "product",
      envelope({
        ...product,
        catalog,
        name: "Produto fonte",
        reference: "REF",
        color: "Azul",
        size: "M",
        color_hex: "#123abc",
        stock: "12.25",
        sale_price: "42.10",
        active: true,
      }),
      product.product_key,
    ).data;
    expect(parsed.stock).toBe("12.25");
    expect(parsed.sale_price).toBe("42.10");
    const view = productView(parsed);
    expect(view.variants).toEqual([
      { color: "Azul", size: "M", sku: "SKU", stock: 12.25, hex: "#123abc" },
    ]);
    expect(view.sizes).toBeNull();
    expect(view.variantSales).toBeUndefined();
    expect(view.abc).toBeNull();
  });
  it("rejects catalog values without certification, malformed evidence, float stock and guessed hex", () => {
    for (const patch of [
      { stock: "0" },
      { color: "Azul" },
      { catalog, stock: 12 },
      { catalog, stock: "-1" },
      { catalog: { ...catalog, evidence_hash: "guess" } },
      { catalog, color_hex: "blue" },
      { catalog: { ...catalog, snapshot_as_of: "invalid" } },
      { catalog: { ...catalog, basis: "historical" } },
    ])
      expect(() =>
        decodeReadEnvelope(
          "product",
          envelope({ ...product, ...patch }),
          product.product_key,
        ),
      ).toThrow();
  });
  it("maps order variant dimensions only with catalog proof and preserves requested versus fulfilled", () => {
    const parsed = decodeReadEnvelope(
      "order",
      envelope({
        ...detail,
        items: [
          {
            ...detail.items[0],
            catalog,
            color: "Azul",
            size: "M",
            reference: "REF",
          },
        ],
      }),
      order.order_id,
    );
    expect(parsed.data.items[0]).toMatchObject({
      catalog,
      color: "Azul",
      size: "M",
      requested_value: "9.99",
      fulfilled_value: "0.00",
    });
    expect(() =>
      decodeReadEnvelope(
        "order",
        envelope({ ...detail, items: [{ ...detail.items[0], color: "Azul" }] }),
        order.order_id,
      ),
    ).toThrow();
  });
});

describe("exact variant family", () => {
  const catalog = {
    basis: "current_source_snapshot",
    snapshot_as_of: "2026-10-05T03:00:00Z",
    evidence_hash: "b".repeat(64),
  };
  const variant = {
    variant_id: "variant-synthetic",
    product_id: "canonical-parent",
    sku: "SKU",
    color: "Azul",
    size: "M",
    catalog,
    stock: "5",
    sale_price: "42.10",
    color_hex: "#123abc",
    active: true,
    requested_revenue: "9.99",
    fulfilled_revenue: "6.66",
    units_requested: "3",
    units_fulfilled: "2",
    orders_observed: 1,
    buyers_observed: 1,
  };
  const data = {
    ...product,
    product_id: "canonical-parent",
    catalog,
    variants: [variant],
    variant_sales_basis: "observed_line_gross_current_catalog",
  };
  it("maps stock and attended sales from separate evidence without deriving full-grade or paid status", () => {
    const parsed = decodeReadEnvelope(
      "product",
      envelope(data),
      product.product_key,
    ).data;
    const view = productView(parsed);
    expect(view.variants?.[0].stock).toBe(5);
    expect(view.variantSales).toEqual([{ color: "Azul", size: "M", units: 2 }]);
    expect(view.sizes).toBeNull();
    expect(view.variantSalesBasis).toBe("observed_line_gross_current_catalog");
  });
  it("rejects foreign parent, duplicate variants, snapshot mixing and invented sales basis", () => {
    for (const patch of [
      { variants: [{ ...variant, product_id: "foreign" }] },
      { variants: [variant, variant] },
      {
        variants: [
          {
            ...variant,
            catalog: { ...catalog, evidence_hash: "c".repeat(64) },
          },
        ],
      },
      { variant_sales_basis: "paid" },
    ])
      expect(() =>
        decodeReadEnvelope(
          "product",
          envelope({ ...data, ...patch }),
          product.product_key,
        ),
      ).toThrow();
  });
});
