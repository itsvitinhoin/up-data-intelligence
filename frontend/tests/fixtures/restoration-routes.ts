import { creative } from "./creatives";
import type { Page } from "@playwright/test";
import * as data from "./restoration";
import { installationFixture } from "./installation";
export async function restorationResources(page: Page, preview = false) {
  await page.route("**/api/dashboard/**", (r) => {
    const url = new URL(r.request().url()),
      path = url.pathname.replace("/api/dashboard/", "");
    if (
      preview &&
      url.searchParams.get("workspace_operation_id") !== "mx-fashion-b2b"
    )
      return r.fulfill({
        status: 404,
        json: { error: { code: "preview_binding_absent" } },
      });
    const customer = data.customer.customer_id,
      campaign = data.campaign.campaign_id;
    const intelligence = [
      "performance",
      "campaigns",
      `campaigns/${campaign}`,
      `campaigns/${campaign}/customers`,
      `campaigns/${campaign}/orders`,
      `customers/${customer}/intelligence`,
      `customers/${customer}/timeline`,
      `customers/${customer}/products`,
      `customers/${customer}/campaigns`,
      "orders/influenced",
    ].includes(path);
    const responses: Record<string, unknown> = {
      overview: data.overview,
      orders: [data.order],
      customers: [data.customer],
      products: [data.product],
      retention: data.retention,
      geography: data.geography,
      performance: data.performance,
      campaigns: [data.campaign],
      creatives: [creative],
      acquisition: {
        buyers_observed: 1,
        first_purchase_customers_observed: 1,
        first_purchase_orders_observed: 1,
        requested_first_purchase_observed: "50.01",
        fulfilled_first_purchase_observed: null,
        confirmed_new_customers: null,
      },
      [`orders/${data.order.order_id}`]: data.orderDetail,
      [`products/${data.product.product_key}`]: data.productDetail,
      [`customers/${customer}`]: data.customerDetail,
      [`customers/${customer}/orders`]: [data.order],
      [`customers/${customer}/intelligence`]: data.customer360,
      [`customers/${customer}/timeline`]: data.timeline,
      [`customers/${customer}/products`]: data.customerProducts,
      [`customers/${customer}/campaigns`]: [data.campaign],
      [`campaigns/${campaign}`]: [data.campaign],
      [`campaigns/${campaign}/customers`]: data.campaignCustomers,
      [`campaigns/${campaign}/orders`]: data.campaignOrders,
      "orders/influenced": data.influencedOrders,
    };
    if (path === "installation") {
      if (!preview) return r.fallback();
      return r.fulfill({ json: installationFixture() });
    }
    if (!(path in responses))
      return r.fulfill({
        status: 424,
        json: { error: { code: "coverage_not_certified" } },
      });
    const value = data.envelope(responses[path], intelligence);
    if (preview) {
      value.metadata = {
        ...value.metadata,
        store_id: "mx-fashion",
        as_of: "2026-09-28T03:00:00Z",
        report_to: "2026-09-28",
        generation: intelligence ? 4 : 7,
      };
      if (intelligence)
        Object.assign(value.metadata, { analytics_generation: 7 });
      value.data = JSON.parse(
        JSON.stringify(value.data).replaceAll(
          '"store_id":"synthetic-store"',
          '"store_id":"mx-fashion"',
        ),
      );
    }
    return r.fulfill({ json: value });
  });
}
