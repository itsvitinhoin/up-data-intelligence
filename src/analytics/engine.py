"""Bounded offline reference implementation over current CORE snapshots.

Pure functions: no clients, credentials, queries or persistence. Production extraction
and incremental materialization are future work; this is not a full-table Python job.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

from src.analytics.policy import LTV_DAYS, VERSION, Policy
from src.analytics.quality import AnalyticsQualityError, issue, unique, validate_outputs
from src.utils.data import digest, numeric, timestamp

Row = dict[str, Any]


def amount(value: Any) -> Decimal | None:
    normalized = numeric(value)
    if normalized is None:
        return None
    result = Decimal(normalized)
    if result < 0:
        raise AnalyticsQualityError("negative_revenue")
    return result


def total(values: list[Any]) -> Decimal | None:
    parsed = [amount(v) for v in values]
    return (
        None
        if any(v is None for v in parsed)
        else sum((v for v in parsed if v is not None), Decimal(0))
    )


def ratio(numerator: Any, denominator: Any) -> Decimal | None:
    if numerator is None or denominator is None or Decimal(str(denominator)) == 0:
        return None
    with localcontext() as context:
        context.prec = 28
        return Decimal(str(numerator)) / Decimal(str(denominator))


def instant(value: str) -> datetime:
    return datetime.fromisoformat(timestamp(value))


def month_index(value: str) -> int:
    day = date.fromisoformat(value)
    return day.year * 12 + day.month - 1


def month_name(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}-01"


def stamped(policy: Policy, grain: list[Any], **fields: Any) -> Row:
    return {
        "row_key": digest([policy.store_id, policy.key, *grain]),
        "store_id": policy.store_id,
        "currency": policy.currency,
        "reporting_timezone": policy.timezone,
        "calculated_at": timestamp(policy.as_of),
        "policy_hash": policy.key,
        "analytics_version": VERSION,
        "history_complete": policy.history_complete,
        **fields,
    }


def scoped(rows: list[Row], policy: Policy) -> list[Row]:
    selected = [r for r in rows if r.get("store_id") == policy.store_id]
    if any(r.get("source_system") != "upzero" for r in selected):
        raise AnalyticsQualityError("unsupported_analytics_source")
    if any(
        r.get("observed_at") and instant(r["observed_at"]) > instant(policy.as_of) for r in selected
    ):
        raise AnalyticsQualityError("snapshot_observed_after_as_of")
    return selected


def build(
    policy: Policy, *, orders: list[Row], customers: list[Row], items: list[Row], events: list[Row]
) -> dict[str, Any]:
    if sum(map(len, (orders, customers, items, events))) > 100_000:
        raise ValueError("offline_reference_requires_bounded_input")
    with localcontext() as context:
        context.prec = 78
        return _build(policy, orders=orders, customers=customers, items=items, events=events)


def _build(
    policy: Policy, *, orders: list[Row], customers: list[Row], items: list[Row], events: list[Row]
) -> dict[str, Any]:
    orders, customers, items, events = [
        scoped(rows, policy) for rows in (orders, customers, items, events)
    ]
    unique(orders, "order_id", "duplicate_order")
    unique(customers, "customer_id", "duplicate_customer")
    unique(events, "fact_id", "duplicate_fact")
    # Item identity is parent-scoped, not a SKU; do not dedupe arbitrarily.
    if len({(i.get("order_id"), i.get("item_id")) for i in items}) != len(items):
        raise AnalyticsQualityError("duplicate_order_item")
    findings = []
    customer_map = {c["customer_id"]: c for c in customers}
    prepared = []
    for order in orders:
        at = instant(order["created_at"])
        if at >= instant(policy.as_of):
            continue
        if order.get("order_status") not in {
            "RESERVED",
            "CONFIRMED",
            "PROCESSING",
            "INVOICED",
            "SHIPPED",
            "CANCELED",
        } or order.get("payment_status") not in {"paid", "unpaid", "canceled"}:
            raise AnalyticsQualityError("unknown_commerce_status")
        generated, fulfilled = (
            amount(order.get("requested_total")),
            amount(order.get("fulfilled_total")),
        )
        cid = order.get("customer_id")
        resolved = cid if cid in customer_map else None
        if resolved is None:
            findings.append(issue("order_without_customer"))
        if generated is None or fulfilled is None:
            findings.append(issue("missing_revenue_component"))
        if generated is not None and fulfilled is not None and fulfilled > generated:
            findings.append(issue("fulfilled_greater_than_requested"))
        prepared.append(
            {
                **order,
                "resolved_customer_id": resolved,
                "customer_type": customer_map[resolved].get("customer_type") if resolved else None,
                "order_at": timestamp(order["created_at"]),
                "order_date": policy.local_date(order["created_at"]),
                "revenue_generated": generated,
                "revenue_fulfilled": fulfilled,
                "revenue_paid": None,
                "payment_date": None,
                "is_purchase": order["order_status"] in policy.purchase_statuses,
            }
        )
    by_customer: dict[str, list[Row]] = defaultdict(list)
    for order in prepared:
        if order["is_purchase"] and order["resolved_customer_id"]:
            by_customer[order["resolved_customer_id"]].append(order)
    sequences, customer_metrics = [], []
    for cid, purchases in sorted(by_customer.items()):
        purchases.sort(key=lambda o: (instant(o["order_at"]), o["order_id"]))
        first = purchases[0]
        for ordinal, order in enumerate(purchases, 1):
            order["purchase_number"] = ordinal
            sequences.append(
                stamped(
                    policy,
                    ["sequence", order["order_id"]],
                    customer_id=cid,
                    customer_type=order["customer_type"],
                    order_id=order["order_id"],
                    source_order_version_id=order.get("version_id"),
                    order_at=order["order_at"],
                    order_date=order["order_date"],
                    first_purchase_at=first["order_at"],
                    first_purchase_date=first["order_date"],
                    purchase_number=ordinal,
                    customer_classification="returning_customer"
                    if ordinal > 1
                    else "new_customer"
                    if policy.history_complete
                    else "first_observed",
                    revenue_generated=order["revenue_generated"],
                    revenue_fulfilled=order["revenue_fulfilled"],
                    revenue_paid=None,
                )
            )
        metrics = stamped(
            policy,
            ["customer", cid],
            customer_id=cid,
            customer_type=first["customer_type"],
            first_purchase_date=first["order_date"],
            purchases=len(purchases),
            ltv_lifetime_observed=total([o["revenue_generated"] for o in purchases]),
            ltv_paid=None,
            ltv_basis="requested_total_of_qualifying_orders",
            observed_through=timestamp(policy.as_of),
        )
        for number, name in enumerate(("first", "second", "third", "fourth")):
            metrics[name + "_purchase_at"] = (
                purchases[number]["order_at"] if len(purchases) > number else None
            )
        for n, pair in enumerate(("first_to_second", "second_to_third", "third_to_fourth")):
            metrics["days_" + pair] = (
                Decimal(
                    str(
                        (
                            instant(purchases[n + 1]["order_at"])
                            - instant(purchases[n]["order_at"])
                        ).total_seconds()
                    )
                )
                / Decimal(86400)
                if len(purchases) > n + 1
                else None
            )
        for days in LTV_DAYS:
            end = instant(first["order_at"]) + timedelta(days=days)
            mature = instant(policy.as_of) >= end
            metrics[f"ltv_{days}d"] = (
                total([o["revenue_generated"] for o in purchases if instant(o["order_at"]) < end])
                if mature
                else None
            )
            metrics[f"ltv_{days}d_complete"] = mature and policy.history_complete
        customer_metrics.append(metrics)
    daily = []
    day = date.fromisoformat(policy.report_from)
    while day < date.fromisoformat(policy.report_to):
        selected = [o for o in prepared if o["order_date"] == day.isoformat()]
        qualified = [o for o in selected if o["is_purchase"]]
        ids = {o["resolved_customer_id"] for o in qualified if o["resolved_customer_id"]}
        new_ids = {cid for cid in ids if by_customer[cid][0]["order_date"] == day.isoformat()}
        cancelled = [o for o in selected if o["order_status"] == "CANCELED"]
        generated, fulfilled = (
            total([o["revenue_generated"] for o in selected]),
            total([o["revenue_fulfilled"] for o in selected]),
        )
        daily.append(
            stamped(
                policy,
                ["daily", day.isoformat()],
                order_date=day.isoformat(),
                payment_date=None,
                orders_generated=len(selected),
                orders_paid=sum(o["payment_status"] == "paid" for o in selected),
                orders_cancelled=len(cancelled),
                approved_orders=len(qualified),
                revenue_generated=generated,
                revenue_fulfilled=fulfilled,
                revenue_paid=None,
                revenue_cancelled=total([o["revenue_generated"] for o in cancelled]),
                revenue_unfulfilled=generated - fulfilled
                if generated is not None and fulfilled is not None and generated >= fulfilled
                else None,
                approval_rate=ratio(len(qualified), len(selected)),
                average_order_value_generated=ratio(generated, len(selected)),
                average_order_value_paid=None,
                items_per_order_generated=ratio(
                    total([o.get("requested_items_qty") for o in selected]), len(selected)
                ),
                items_per_order_fulfilled=ratio(
                    total([o.get("fulfilled_items_qty") for o in selected]), len(selected)
                ),
                new_customers=len(new_ids) if policy.history_complete else None,
                returning_customers=len(ids - new_ids),
                purchasing_customers=len(ids),
                orders_without_customer=sum(o["resolved_customer_id"] is None for o in selected),
                observation_complete=policy.history_complete,
                meta_spend=None,
                meta_impressions=None,
                meta_clicks=None,
                meta_reported_purchases=None,
                meta_reported_purchase_value=None,
                first_party_new_customers_attributed=None,
                first_party_orders_attributed=None,
                first_party_revenue_generated_attributed=None,
                first_party_revenue_paid_attributed=None,
                new_customer_cac=None,
                roas_generated=None,
                roas_paid=None,
            )
        )
        day += timedelta(days=1)
    cohorts = cohort_rows(policy, by_customer)
    distributions = distribution_rows(policy, by_customer)
    products = product_rows(policy, prepared, items, findings)
    funnel = funnel_rows(policy, events)
    tables = {
        "analytics_store_daily": daily,
        "analytics_customer_metrics": customer_metrics,
        "analytics_customer_purchase_sequence": sequences,
        "analytics_cohorts": cohorts,
        "analytics_purchase_distribution": distributions,
        "analytics_products_daily": products,
        "analytics_funnel_daily": funnel,
    }
    findings += validate_outputs(tables)
    if any(f["severity"] == "blocking" for f in findings):
        raise AnalyticsQualityError("analytics_output_quality_failed")
    active = {
        o["resolved_customer_id"]
        for o in prepared
        if o["is_purchase"]
        and o["resolved_customer_id"]
        and policy.report_from <= o["order_date"] < policy.report_to
    }
    in_period = [
        o
        for o in prepared
        if o["is_purchase"]
        and o["resolved_customer_id"] in active
        and policy.report_from <= o["order_date"] < policy.report_to
    ]
    repeated = {
        cid
        for cid in active
        if sum(o["order_date"] < policy.report_to for o in by_customer[cid]) >= 2
    }
    period_days = (
        date.fromisoformat(policy.report_to) - date.fromisoformat(policy.report_from)
    ).days
    previous_start = (
        date.fromisoformat(policy.report_from) - timedelta(days=period_days)
    ).isoformat()
    previous = {
        o["resolved_customer_id"]
        for o in prepared
        if o["is_purchase"]
        and o["resolved_customer_id"]
        and previous_start <= o["order_date"] < policy.report_from
    }
    summary = {
        "period_from": policy.report_from,
        "period_to_exclusive": policy.report_to,
        "purchase_frequency": ratio(len(in_period), len(active)),
        "customer_repurchase_rate": ratio(len(repeated), len(active))
        if policy.history_complete
        else None,
        "repurchase_denominator": len(active),
        "frequency_denominator": len(active),
        "customer_retention_rate": ratio(len(active & previous), len(previous))
        if policy.history_complete
        else None,
        "retention_denominator": len(previous),
        "retention_previous_from": previous_start,
        "retention_previous_to_exclusive": policy.report_from,
    }
    return {"tables": tables, "period_metrics": summary, "quality": findings}


def cohort_rows(policy: Policy, customers: dict[str, list[Row]]) -> list[Row]:
    cohorts: dict[int, dict[str, list[Row]]] = defaultdict(dict)
    for cid, purchases in customers.items():
        cohorts[month_index(purchases[0]["order_date"])][cid] = purchases
    rows = []
    last_closed_day = policy.local_date(policy.as_of)
    for start, members in sorted(cohorts.items()):
        for month in range(start, month_index(last_closed_day) + 1):
            observed = [
                o
                for purchases in members.values()
                for o in purchases
                if month_index(o["order_date"]) == month
            ]
            complete = month_name(month + 1) <= last_closed_day
            active = len({o["resolved_customer_id"] for o in observed})
            rows.append(
                stamped(
                    policy,
                    ["cohort", start, month - start],
                    cohort_month=month_name(start),
                    months_since_first_purchase=month - start,
                    reporting_month=month_name(month),
                    customers_in_cohort=len(members),
                    active_customers=active,
                    orders=len(observed),
                    retention_rate=ratio(active, len(members))
                    if complete and policy.history_complete
                    else None,
                    observed_retention_rate=ratio(active, len(members)),
                    period_complete=complete,
                    revenue_generated=total([o["revenue_generated"] for o in observed]),
                    revenue_paid=None,
                )
            )
    return rows


def distribution_rows(policy: Policy, customers: dict[str, list[Row]]) -> list[Row]:
    cohorts: dict[str, dict[str, list[Row]]] = defaultdict(dict)
    for cid, purchases in customers.items():
        cohorts[purchases[0]["order_date"][:7] + "-01"][cid] = purchases
    rows = []
    for cohort, members in sorted(cohorts.items()):
        for bucket in range(1, 6):
            selected = [
                o
                for purchases in members.values()
                for i, o in enumerate(purchases, 1)
                if min(i, 5) == bucket
            ]
            reached = len({o["resolved_customer_id"] for o in selected})
            rows.append(
                stamped(
                    policy,
                    ["distribution", cohort, bucket],
                    cohort_month=cohort,
                    purchase_bucket=str(bucket) if bucket < 5 else "5+",
                    customers=reached,
                    original_cohort_customers=len(members),
                    percentage_of_original_cohort=ratio(reached, len(members)),
                    revenue=total([o["revenue_generated"] for o in selected]),
                    revenue_basis="generated_qualifying_orders",
                )
            )
    return rows


def product_key(item: Row) -> str:
    identifiers = [item.get("asset_id"), item.get("variant_id"), item.get("sku")]
    if not item.get("variant_id") and not item.get("sku"):
        # Asset alone does not prove colour/size. Keep unresolved lines separate.
        identifiers += [item.get("order_id"), item.get("item_id")]
    return digest(identifiers)


def product_rows(
    policy: Policy, orders: list[Row], items: list[Row], findings: list[Row]
) -> list[Row]:
    order_map = {
        o["order_id"]: o for o in orders if policy.report_from <= o["order_date"] < policy.report_to
    }
    grouped: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for item in items:
        order = order_map.get(item.get("order_id"))
        if not order or not item.get("present_in_latest_snapshot"):
            continue
        if (
            not order.get("version_id")
            or item.get("parent_order_version_id") != order["version_id"]
        ):
            findings.append(issue("item_order_snapshot_mismatch"))
            continue
        if item.get("status") not in {"active", "attended", "removed"}:
            findings.append(issue("unsupported_item_status"))
            continue
        key = product_key(item)
        if not item.get("variant_id") and not item.get("sku"):
            findings.append(issue("product_variant_unknown"))
        grouped[(order["order_date"], key)].append(
            {**item, "customer": order["resolved_customer_id"]}
        )
    result = []
    for (day, key), group in sorted(grouped.items()):
        requested = total([i.get("original_qty") for i in group])
        fulfilled = total(
            [i.get("qty") if i["status"] in {"active", "attended"} else 0 for i in group]
        )
        requested_values, fulfilled_values = [], []
        for item in group:
            price, original, quantity = (
                amount(item.get("unit_price")),
                amount(item.get("original_qty")),
                amount(item.get("qty")),
            )
            requested_values.append(
                price * original if price is not None and original is not None else None
            )
            fulfilled_values.append(
                Decimal(0)
                if item["status"] == "removed"
                else price * quantity
                if price is not None and quantity is not None
                else None
            )
        generated_value, fulfilled_value = total(requested_values), total(fulfilled_values)
        # Only explicitly removed units are cancelled, not all unfulfilled units.
        removed = total([i.get("original_qty") if i["status"] == "removed" else 0 for i in group])
        result.append(
            stamped(
                policy,
                ["product", day, key],
                order_date=day,
                product_key=key,
                product_id=None,
                asset_id=group[0].get("asset_id"),
                variant_id=group[0].get("variant_id"),
                sku=group[0].get("sku"),
                reference=None,
                units_requested=requested,
                units_fulfilled=fulfilled,
                orders=len({i["order_id"] for i in group}),
                customers=len({i["customer"] for i in group if i["customer"]}),
                revenue_generated=generated_value,
                revenue_fulfilled=fulfilled_value,
                revenue_paid=None,
                revenue_basis="line_gross_at_current_unit_price",
                average_selling_price=ratio(fulfilled_value, fulfilled),
                cancellation_rate=ratio(removed, requested),
                spend=None,
                impressions=None,
                clicks=None,
                first_party_orders_attributed=None,
                first_party_revenue_attributed=None,
                roas=None,
            )
        )
    return result


def funnel_rows(policy: Policy, events: list[Row]) -> list[Row]:
    days: dict[str, list[Row]] = defaultdict(list)
    for event in events:
        day = policy.local_date(event["occurred_at"])
        if policy.report_from <= day < policy.report_to and instant(event["occurred_at"]) < instant(
            policy.as_of
        ):
            days[day].append(event)
    result = []
    day_value = date.fromisoformat(policy.report_from)
    while day_value < date.fromisoformat(policy.report_to):
        day = day_value.isoformat()
        group = days.get(day, [])
        sessions: dict[str, list[Row]] = defaultdict(list)
        for event in group:
            if isinstance(event.get("session_id"), str) and event["session_id"].strip():
                sessions[event["session_id"]].append(event)
        cart_sessions = checkout_sessions = purchase_sessions = converted_sessions = 0
        for sequence in sessions.values():
            cart_at = checkout_at = None
            purchased = False
            for event in sorted(sequence, key=lambda e: (instant(e["occurred_at"]), e["fact_id"])):
                at, name = instant(event["occurred_at"]), event["event_name"]
                if name == "add_to_cart" and cart_at is None:
                    cart_at = at
                if (
                    name == "checkout_started"
                    and cart_at is not None
                    and at >= cart_at
                    and checkout_at is None
                ):
                    checkout_at = at
                if name == "purchase" and checkout_at is not None and at >= checkout_at:
                    purchased = True
            cart_sessions += int(cart_at is not None)
            checkout_sessions += int(checkout_at is not None)
            purchase_sessions += int(purchased)
            converted_sessions += int(any(e["event_name"] == "purchase" for e in sequence))
        result.append(
            stamped(
                policy,
                ["funnel", day],
                event_date=day,
                sessions=len(sessions),
                product_views=sum(e["event_name"] == "product_view" for e in group),
                add_to_cart=sum(e["event_name"] == "add_to_cart" for e in group),
                checkout_started=sum(e["event_name"] == "checkout_started" for e in group),
                purchase=sum(e["event_name"] == "purchase" for e in group),
                sessions_with_cart=cart_sessions,
                sessions_cart_then_checkout=checkout_sessions,
                sessions_cart_checkout_purchase=purchase_sessions,
                sessions_with_purchase=converted_sessions,
                events_without_session=sum(
                    not isinstance(e.get("session_id"), str) or not e["session_id"].strip()
                    for e in group
                ),
                observation_complete=policy.facts_complete,
                session_to_cart_rate=ratio(cart_sessions, len(sessions))
                if policy.facts_complete
                else None,
                cart_to_checkout_rate=ratio(checkout_sessions, cart_sessions)
                if policy.facts_complete
                else None,
                checkout_to_purchase_rate=ratio(purchase_sessions, checkout_sessions)
                if policy.facts_complete
                else None,
                session_conversion_rate=ratio(converted_sessions, len(sessions))
                if policy.facts_complete
                else None,
                cost_per_session=None,
                cost_per_add_to_cart=None,
                cost_per_checkout=None,
            )
        )
        day_value += timedelta(days=1)
    return result
