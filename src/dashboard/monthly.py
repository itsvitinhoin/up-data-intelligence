"""Monthly observed aggregates; the backend owns all decimal ratios."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from src.dashboard.contracts import ReadError, integer, iso_date
from src.dashboard.service import _ratio, _sum_count, _sum_money


def monthly_performance(
    commercial: dict[str, Any],
    funnel: list[dict[str, Any]],
    media: list[dict[str, Any]],
    start: str,
    end: str,
    *,
    meta_complete: bool,
) -> list[dict[str, Any]]:
    """One publication/window, month-distinct customers, explicit paid status only."""
    if start >= end:
        raise ReadError(503, "monthly_period_invalid")
    last_month = (date.fromisoformat(end) - timedelta(days=1)).isoformat()[:7]
    buckets: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for source, rows, date_key in (
        ("commercial", commercial.get("series", []), "date"),
        ("funnel", funnel, "event_date"),
        ("media", media, "date"),
    ):
        seen: set[str] = set()
        for row in rows:
            day = iso_date(str(row[date_key]))
            if not start <= day < end or day in seen:
                raise ReadError(503, "monthly_daily_grain_invalid")
            seen.add(day)
            buckets.setdefault(day[:7], {}).setdefault(source, []).append(row)
    customers: dict[str, dict[str, Any]] = {}
    payments: dict[str, dict[str, Any]] = {}
    for result, rows in (
        (customers, commercial.get("monthly_customers", [])),
        (payments, commercial.get("monthly_payments", [])),
    ):
        for row in rows:
            month_day = iso_date(str(row["month"]))
            month = month_day[:7]
            if month_day[8:] != "01" or month in result or not start[:7] <= month <= last_month:
                raise ReadError(503, "monthly_summary_grain_invalid")
            result[month] = row
    result_rows = []
    for month, groups in sorted(buckets.items()):
        sales = groups.get("commercial", [])
        events = groups.get("funnel", [])
        ads = groups.get("media", [])
        requested = _sum_money(sales, "requested") if sales else None
        orders = _sum_count(sales, "orders") if sales else None
        spend = _sum_money(ads, "spend") if meta_complete and ads else None
        customer = customers.get(month, {})
        payment = payments.get(month, {})
        if payment and integer(payment.get("orders")) != orders:
            raise ReadError(503, "monthly_payment_not_reconciled")
        paid = integer(payment.get("paid_orders"))
        unknown = integer(payment.get("unknown_payment_status"))
        if payment and (
            paid is None
            or unknown is None
            or orders is None
            or not 0 <= paid <= orders
            or not 0 <= unknown <= orders - paid
        ):
            raise ReadError(503, "monthly_payment_not_reconciled")
        row = {
            "month": month,
            "requested": requested,
            "fulfilled": _sum_money(sales, "fulfilled") if sales else None,
            "cancelled": _sum_money(sales, "cancelled_requested") if sales else None,
            "orders": orders,
            "paid_orders": paid if unknown == 0 else None,
            "paid_revenue": None,
            "buyers": integer(customer.get("buyers_observed")),
            "recurring": integer(customer.get("recurring_buyers_observed")),
            "meta_spend": spend,
            "available_media_spend": spend,
            "requested_ticket": _ratio(requested, orders),
            "commercial_roas_requested": _ratio(requested, spend),
            "commercial_roas_paid": None,
        }
        for field in (
            "sessions",
            "add_to_cart",
            "checkout_started",
            "sessions_with_cart",
            "sessions_cart_then_checkout",
            "sessions_cart_checkout_purchase",
            "sessions_with_purchase",
        ):
            row[field] = _sum_count(events, field) if events else None
        for key, numerator, denominator in (
            ("recurring_rate", "recurring", "buyers"),
            ("session_purchase_rate", "sessions_with_purchase", "sessions"),
            ("session_cart_rate", "sessions_with_cart", "sessions"),
            ("cart_checkout_rate", "sessions_cart_then_checkout", "sessions_with_cart"),
            (
                "checkout_purchase_rate",
                "sessions_cart_checkout_purchase",
                "sessions_cart_then_checkout",
            ),
            ("cost_per_session", "available_media_spend", "sessions"),
            ("cost_per_add_to_cart", "available_media_spend", "add_to_cart"),
            ("cost_per_checkout", "available_media_spend", "checkout_started"),
            ("cost_per_paid_order", "available_media_spend", "paid_orders"),
        ):
            value = _ratio(row[numerator], row[denominator])
            row[key] = (
                format(Decimal(value) * 100, "f")
                if key.endswith("_rate") and value is not None
                else value
            )
        result_rows.append(row)
    return result_rows
