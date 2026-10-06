import { metaPeriodData } from "./fixtures/meta-period";
import { creative } from "./fixtures/creatives";
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
  customerDetail,
  customer360,
  order,
  timeline,
  customerProducts,
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
  it("loads exact customer campaigns without per-campaign customer scans", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      const path = new URL(String(input), "https://web.example.test").pathname;
      if (path.endsWith("/intelligence"))
        return Response.json(envelope(customer360, true));
      if (path.endsWith("/orders")) return Response.json(envelope([order]));
      if (path.endsWith("/products"))
        return Response.json(envelope(customerProducts, true));
      if (path.endsWith("/timeline"))
        return Response.json(envelope(timeline, true));
      if (path.endsWith("/campaigns"))
        return Response.json(envelope([campaign], true));
      return Response.json(envelope(customerDetail));
    });
    const result = await createLiveDataApi(metadata, fetcher).customer(
      customer.customer_id,
      context,
    );
    expect(result.campaigns.map((r) => r.id)).toEqual([campaign.campaign_id]);
    expect(result.orders).toHaveLength(1);
    expect(fetcher).toHaveBeenCalledTimes(6);
    const paths = fetcher.mock.calls.map(
      ([url]) => new URL(String(url), "https://web.example.test").pathname,
    );
    expect(paths).toContain(
      `/api/dashboard/customers/${customer.customer_id}/campaigns`,
    );
    expect(
      paths.some((path) => path.startsWith("/api/dashboard/campaigns")),
    ).toBe(false);
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
  it("uses official period Meta evidence without influence or commercial revenue substitution", async () => {
    const f = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(envelope(metaPeriodData())))
      .mockResolvedValueOnce(
        Response.json(
          { error: { code: "creative_coverage_unavailable" } },
          { status: 424 },
        ),
      );
    const result = await createLiveDataApi(metadata, f).read(
      "marketing",
      context,
    );
    expect(result.metrics).toHaveLength(12);
    expect(result.metrics![0].value).toBe("0.30");
    expect(result.metrics![1].value).toBe("1.00");
    expect(result.campaigns[0].requested).toBeNull();
    expect(result.campaigns[0].fulfilled).toBeNull();
    expect(result.creatives).toEqual([]);
    expect(result.series[0]).toMatchObject({
      source: "real",
      revenue: "1.00",
      spend: "0.30",
      roas: "3.333333333333333333",
    });
  });
  it("loads ad rankings independently and never substitutes campaign values", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      const path = new URL(String(input), "https://web.example.test").pathname;
      if (path.endsWith("/metaAds"))
        return Response.json(envelope(metaPeriodData()));
      if (path.endsWith("/creatives"))
        return Response.json(envelope([creative]));
      throw new Error("unexpected resource");
    });
    const result = await createLiveDataApi(metadata, fetcher).read(
      "marketing",
      context,
    );
    expect(result.creatives).toHaveLength(1);
    expect(result.creatives[0].id).toBe("000401");
    expect(result.creatives[0].source).toBe("real");
    expect(result.creatives[0].purchases).toBe(2);
    expect(result.creatives[0].approved).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("pins Intelligence across separate projections", async () => {
    const f = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(envelope([campaign], true)))
      .mockResolvedValueOnce(
        Response.json({
          ...envelope([campaign], true),
          metadata: { ...envelope(null, true).metadata, generation: 5 },
        }),
      );
    const api = createLiveDataApi(metadata, f);
    await api.read("campaigns", context);
    await expect(api.read("campaigns", context)).rejects.toMatchObject({
      status: 409,
    });
  });
  it("drills down official Meta campaign to exact adsets and ads without commercial IO", async () => {
    const f = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(envelope(metaPeriodData())));
    const detail = await createLiveDataApi(metadata, f).campaign(
      "101",
      context,
    );
    expect(detail.meta?.adsets).toHaveLength(1);
    expect(detail.meta?.ads).toHaveLength(1);
    expect(detail.requested).toBeNull();
    expect(detail.customers).toEqual([]);
    expect(detail.orders).toEqual([]);
    expect(f).toHaveBeenCalledTimes(1);
    expect(String(f.mock.calls[0][0])).toContain("/metaAds");
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
  it("validates and maps full-period product share without replacing unknown with zero", async () => {
    for (const value of ["0.25", "0", null]) {
      const f = vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json(
            envelope([{ ...productDetail, requested_share_observed: value }]),
          ),
        );
      const [p] = await createLiveDataApi(metadata, f).read(
        "products",
        context,
      );
      expect(p.share).toBe(value === null ? null : Number(value) * 100);
      expect(p.fulfilled).toBeNull();
    }
    const f = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          envelope([{ ...productDetail, requested_share_observed: 0.25 }]),
        ),
      );
    await expect(
      createLiveDataApi(metadata, f).read("products", context),
    ).rejects.toThrow();
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
