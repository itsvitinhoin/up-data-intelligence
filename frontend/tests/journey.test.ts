import { describe, expect, it } from "vitest";
import { groupJourney } from "@/lib/journey";
import { timelineView } from "@/services/api/live-presenters";
import type { TimelineEvent } from "@/types/domain";
import { metadata } from "./fixtures/restoration";
const event = (
  id: string,
  type: string,
  date: string,
  orderId: string | null = "order",
): TimelineEvent => ({
  id,
  type,
  date,
  orderId,
  store_id: "store",
  customer_id: "customer",
  title: type,
  detail: "",
  evidence: "DIRECT",
});
describe("evidence-backed journey presentation", () => {
  it("groups exact order items under purchase without changing evidence or input", () => {
    const events = [
      event("i2", "purchase_item", "2026-09-01T15:00:00Z"),
      event("created", "order_created", "2026-09-01T14:00:00Z"),
      event("purchase", "purchase", "2026-09-01T15:00:00Z"),
      event("i1", "purchase_item", "2026-09-01T12:00:00-03:00"),
      event("orphan", "purchase_item", "2026-09-01T16:00:00Z", "other-order"),
    ];
    const grouped = groupJourney(events);
    expect(grouped.map((r) => r.id)).toEqual(["created", "purchase", "orphan"]);
    expect(grouped[1].items!.map((r) => r.id)).toEqual(["i1", "i2"]);
    expect(grouped[1].items![0]).toBe(events[3]);
    expect(events).toHaveLength(5);
    expect(events.every((r) => !r.items)).toBe(true);
  });
  it("never attaches using a missing identity, a foreign customer, store or nearby timestamp", () => {
    const purchase = event("p", "purchase", "2026-09-01T15:00:00Z");
    const items = [
      event("null", "purchase_item", purchase.date, null),
      {
        ...event("foreign", "purchase_item", purchase.date),
        customer_id: "foreign",
      },
      {
        ...event("foreign-store", "purchase_item", purchase.date),
        store_id: "foreign",
      },
    ];
    expect(groupJourney([purchase, ...items])).toHaveLength(4);
    expect(groupJourney([purchase, ...items]).every((r) => !r.items)).toBe(
      true,
    );
  });
  it("keeps verified media identifiers as observed touchpoints, never claims causality", () => {
    const view = timelineView(
      {
        record_key: "touch",
        event_name: "paid_touch",
        occurred_at: "2026-09-01T15:00:00Z",
        channel: "meta",
        campaign_id: "campaign",
        adset_id: "adset",
        ad_id: "ad",
        confidence_type: "DIRECT",
      },
      "customer",
      metadata,
    );
    expect(view.title).toBe("Touchpoint de mídia observado");
    expect(view.detail).toBe(
      "meta · Campanha: campaign · Conjunto: adset · Anúncio: ad",
    );
    expect(view.orderId).toBeNull();
    expect(view.campaignId).toBe("campaign");
  });
});
