import { describe, it, expect, vi } from "vitest";
import { createLiveDataApi } from "@/services/api/live";
import {
  orderDetailView,
  productView,
  geographyView,
} from "@/services/api/live-presenters";
import { parseIntelligence } from "@/services/api/intelligence";
import { ticket } from "@/services/api/overview-presenter";
import type { RequestContext } from "@/types/domain";
import {
  customer,
  metadata,
  performance,
  orderDetail,
  productDetail,
  envelope,
  campaign,
  geography,
} from "./fixtures/restoration";
const context: RequestContext = {
  scope: {
    tenant_id: "synthetic-tenant",
    store_id: "workspace-synthetic",
    workspace_operation_id: "workspace-synthetic",
    operation: "B2B",
  },
  session: {
    id: "verified-synthetic",
    name: "Synthetic",
    role: "VIEWER",
    tenant_ids: ["synthetic-tenant"],
    store_ids: ["workspace-synthetic"],
  },
  filters: { days: 30, channel: "all", collection: "all" },
};
describe("original component real adapter", () => {
  it("searches the entire authorized collection, validates envelopes and never sends browser technical store", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        Response.json(envelope([customer], false, "opaque-cursor")),
      )
      .mockResolvedValueOnce(
        Response.json(
          envelope([
            {
              ...customer,
              customer_id: "second-customer",
              name: "Pesquisa na segunda página",
            },
          ]),
        ),
      );
    const api = createLiveDataApi(metadata, fetcher);
    const rows = await api.read("customers", {
      ...context,
      filters: { ...context.filters, search: "segunda página" },
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe("second-customer");
    expect(rows[0].fulfilled).toBeNull();
    expect(rows[0].paid).toBeNull();
    const url = new URL(
      String(fetcher.mock.calls[1][0]),
      "https://web.example.test",
    );
    expect(url.searchParams.get("cursor")).toBe("opaque-cursor");
    expect(url.searchParams.has("store_id")).toBe(false);
    expect(url.searchParams.get("workspace_operation_id")).toBe(
      "workspace-synthetic",
    );
  });
  it("fails closed for changing generation, duplicate identity and looping cursors", async () => {
    for (const next of [
      envelope([customer]),
      {
        ...envelope([{ ...customer, customer_id: "other" }]),
        metadata: { ...metadata, generation: 7 },
      },
      envelope([{ ...customer, customer_id: "other" }], false, "same"),
    ]) {
      const f = vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(
          Response.json(envelope([customer], false, "same")),
        )
        .mockResolvedValueOnce(Response.json(next));
      await expect(
        createLiveDataApi(metadata, f).read("customers", context),
      ).rejects.toThrow();
    }
  });
  it("uses decimal daily Meta evidence and preserves all eight original KPI positions", async () => {
    const f = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(envelope(performance, true)))
      .mockResolvedValueOnce(Response.json(envelope([campaign], true)));
    const result = await createLiveDataApi(metadata, f).read(
      "marketing",
      context,
    );
    expect(result.metrics).toHaveLength(8);
    expect(result.metrics![0].value).toBe("100.01");
    expect(result.metrics![1].value).toBeNull();
    expect(result.creatives).toEqual([]);
    expect(result.series[0].revenue).toBeNull();
    expect(result.series[0].spend).toBe("100.01");
  });
  it("pins Intelligence across separate projections", async () => {
    const f = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(envelope(performance, true)))
      .mockResolvedValueOnce(
        Response.json({
          ...envelope([campaign], true),
          metadata: { ...envelope(null, true).metadata, generation: 5 },
        }),
      );
    await expect(
      createLiveDataApi(metadata, f).read("marketing", context),
    ).rejects.toMatchObject({ status: 409 });
  });
  it("keeps canonical routing, NULL and requested/fulfilled differences in drill-down view models", () => {
    const order = orderDetailView(orderDetail);
    expect(order.order.requested).toBe("50.01");
    expect(order.order.fulfilled).toBeNull();
    expect(order.customer!.email).toBeNull();
    expect(order.items[0].requested).toBe("50.010");
    const product = productView(productDetail);
    expect(product.id).toBe(productDetail.product_key);
    expect(product.stock).toBeNull();
    expect(product.sizes).toBeNull();
    expect(product.canonicalProductId).toBeNull();
    expect(product.name).toBeNull();
    expect(ticket("50.01", 2)).toBe("25.01");
    expect(ticket(null, 2)).toBeNull();
  });
  it("keeps missing geography customer evidence NULL without hiding the original map", () => {
    const view = geographyView({
      ...geography,
      states: [
        {
          ...geography.states[0],
          customers: null,
          top_cities: [
            { ...geography.states[0].top_cities[0], customers: null },
          ],
        },
      ],
    });
    expect(view[0].customers).toBeNull();
    expect(view[0].cities[0].customers).toBeNull();
    expect(view[0].orders).toBe(1);
  });
  it("rejects float money or duplicate daily Meta evidence", () => {
    expect(() =>
      parseIntelligence("performance", {
        ...performance,
        series: [{ ...performance.series[0], spend: 100.01 }],
      }),
    ).toThrow();
    expect(() =>
      parseIntelligence("performance", {
        ...performance,
        series: [...performance.series, ...performance.series],
      }),
    ).toThrow();
  });
  it("fails unavailable resources, authorization and unsupported filters without fixture IO", async () => {
    const f = vi.fn<typeof fetch>(),
      api = createLiveDataApi(metadata, f);
    await expect(api.read("erp", context)).rejects.toMatchObject({
      status: 424,
    });
    await expect(
      api.read("customers", {
        ...context,
        scope: { ...context.scope, tenant_id: "foreign" },
      }),
    ).rejects.toMatchObject({ status: 403 });
    await expect(
      api.read("customers", {
        ...context,
        filters: { ...context.filters, collection: "unsupported" },
      }),
    ).rejects.toMatchObject({ status: 400 });
    expect(f).not.toHaveBeenCalled();
  });
});
