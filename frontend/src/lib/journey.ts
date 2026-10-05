/** Presentation grouping only: source identity and event timestamps stay intact. */
import type { TimelineEvent } from "@/types/domain";

export function compareJourney(a: TimelineEvent, b: TimelineEvent): number {
  return Date.parse(a.date) - Date.parse(b.date) || a.id.localeCompare(b.id);
}
export function groupJourney(events: TimelineEvent[]): TimelineEvent[] {
  const ordered = events.toSorted(compareJourney);
  const parents = new Map<string, TimelineEvent>();
  const key = (event: TimelineEvent) =>
    JSON.stringify([event.store_id, event.customer_id, event.orderId]);
  for (const event of ordered) {
    if (!event.orderId || !["purchase", "order_created"].includes(event.type))
      continue;
    const identity = key(event),
      previous = parents.get(identity);
    // Prefer the purchase evidence to the creation event; equal kinds keep the
    // first canonical timestamp/ID. Never attach by proximity or ingestion order.
    if (
      !previous ||
      (event.type === "purchase" && previous.type !== "purchase")
    )
      parents.set(identity, event);
  }
  const items = new Map<string, TimelineEvent[]>();
  const nested = new Set<string>();
  for (const event of ordered) {
    if (event.type !== "purchase_item" || !event.orderId) continue;
    const parent = parents.get(key(event));
    if (!parent) continue; // Orphans remain visible; absence is not proof.
    items.set(parent.id, [...(items.get(parent.id) ?? []), event]);
    nested.add(event.id);
  }
  return ordered
    .filter((event) => !nested.has(event.id))
    .map((event) =>
      items.has(event.id) ? { ...event, items: items.get(event.id) } : event,
    );
}
