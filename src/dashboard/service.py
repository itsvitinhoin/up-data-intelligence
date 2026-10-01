"""Analytics V1 projections; only the injected reader can touch BigQuery."""

import math
import re
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.analytics.config import AnalyticsPolicy
from src.analytics.policy import VERSION as ANALYTICS_VERSION
from src.dashboard.contracts import (
    CursorCodec,
    Grant,
    Principal,
    Publication,
    ReadError,
    cursor_context,
    decimal_string,
    integer,
    iso_date,
    metadata,
    page_size,
)
from src.dashboard.queries import build
from src.dashboard.repository import Reader


def _date(value: Any) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _timestamp(value: Any) -> str:
    return value.isoformat().replace("+00:00", "Z") if hasattr(value, "isoformat") else str(value)


def _publication_date(value: Any) -> str:
    """Require a real, canonical DATE from a publication row (never a policy fallback)."""
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, str):
        try:
            if date.fromisoformat(value).isoformat() == value:
                return value
        except ValueError:
            pass
    raise ReadError(503, "publication_head_invalid")


def _sum_money(rows: list[dict[str, Any]], field: str) -> str | None:
    amounts = [decimal_string(row.get(field)) for row in rows]
    if any(value is None for value in amounts):
        return None
    return format(sum((Decimal(value) for value in amounts if value is not None), Decimal(0)), "f")


def _sum_count(rows: list[dict[str, Any]], field: str) -> int | None:
    values = [integer(row.get(field)) for row in rows]
    return (
        None if any(value is None for value in values) else sum(v for v in values if v is not None)
    )


def _ratio(numerator: int | str | None, denominator: int | str | None) -> str | None:
    if numerator is None or denominator is None or Decimal(str(denominator)) == 0:
        return None
    return format(Decimal(str(numerator)) / Decimal(str(denominator)), "f")


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ReadError(503, "invalid_numeric_value") from None
    if not math.isfinite(result):
        raise ReadError(503, "invalid_numeric_value")
    return result


class DashboardService:
    def __init__(
        self,
        project: str,
        policies: Mapping[str, AnalyticsPolicy],
        reader_factory: Callable[[], Reader],
        cursor_key: bytes,
    ):
        self.project = project
        self.policies = dict(policies)
        self.reader_factory = reader_factory
        self.cursors = CursorCodec(cursor_key)
        if any(key != policy.store_id for key, policy in self.policies.items()):
            raise ValueError("policy_store_mismatch")

    def _query(self, name: str, **values: object) -> list[dict[str, Any]]:
        query = build(self.project, name, **values)
        return self.reader.query(
            query,
            request_id=self.request_id,
            store_id=self.grant.store_id,
            generation=self.publication.generation if hasattr(self, "publication") else None,
        )

    def _scope(self, principal: Principal | None, grant: Grant) -> None:
        if principal is None:
            raise ReadError(401, "unauthenticated")
        principal.authorize(grant.tenant_id, grant.store_id, grant.operation)
        if grant.store_id not in self.policies:
            raise ReadError(404, "store_not_configured")
        self.grant = grant
        self.principal = principal
        self.policy = self.policies[grant.store_id]
        self.request_id = uuid4().hex
        self.reader = self.reader_factory()
        rows = self._query("head", store=grant.store_id, policy=self.policy.policy_hash)
        if not rows:
            raise ReadError(503, "publication_head_missing")
        if len(rows) != 1:
            raise ReadError(503, "publication_head_duplicate_or_invalid")
        row = rows[0]
        if (
            row.get("status") != "completed"
            or row.get("receipt_status") != "completed"
            or row.get("receipt_version") != ANALYTICS_VERSION
            or row.get("store_id") != row.get("receipt_store_id")
            or row.get("policy_hash") != row.get("receipt_policy_hash")
            or row.get("publication_id") != row.get("receipt_id")
            or row.get("generation") != row.get("receipt_generation")
            or row.get("source_watermark") != row.get("receipt_watermark")
            or _timestamp(row.get("as_of")) != _timestamp(row.get("receipt_as_of"))
        ):
            raise ReadError(503, "publication_head_invalid")
        receipt_from = _publication_date(row.get("receipt_from"))
        receipt_to = _publication_date(row.get("receipt_to"))
        if (
            receipt_from >= receipt_to
            or (
                row.get("report_from") is not None
                and _publication_date(row["report_from"]) != receipt_from
            )
            or (
                row.get("report_to") is not None
                and _publication_date(row["report_to"]) != receipt_to
            )
        ):
            raise ReadError(503, "publication_head_invalid")
        generation = integer(row.get("generation"))
        if generation is None:
            raise ReadError(503, "publication_head_invalid")
        self.publication = Publication(
            store_id=str(row.get("store_id")),
            policy_hash=str(row.get("policy_hash")),
            generation=generation,
            publication_id=str(row.get("publication_id")),
            snapshot_at=_timestamp(row.get("snapshot_at")),
            as_of=_timestamp(row.get("as_of")),
            report_from=receipt_from,
            report_to=receipt_to,
        )
        self.publication.validate(self.policy)

    def _rows(self, name: str, **values: object) -> list[dict[str, Any]]:
        return self._query(
            name,
            store=self.grant.store_id,
            policy=self.publication.policy_hash,
            snapshot_at=self.publication.snapshot_at,
            **values,
        )

    def _interval(self, from_day: str | None, to_day: str | None) -> tuple[str, str]:
        start = iso_date(from_day or self.publication.report_from)
        end = iso_date(to_day or self.publication.report_to)
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        if (
            start < self.publication.report_from
            or end > self.publication.report_to
            or not 1 <= days <= 366
        ):
            raise ReadError(400, "interval_outside_publication")
        return start, end

    def _response(
        self,
        data: Any,
        *,
        limitations: list[str] | None = None,
        pagination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = ["history_incomplete"] if not self.policy.history_complete else []
        if not self.policy.facts_complete:
            base.append("facts_incomplete")
        return {
            "data": data,
            "pagination": pagination,
            "metadata": metadata(self.publication, self.policy, base + (limitations or [])),
        }

    def _daily(self, name: str, start: str, end: str) -> list[dict[str, Any]]:
        rows = self._rows(name, from_day=start, to_day=end)
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        key = "order_date" if name == "store_daily" else "event_date"
        dates = [_date(row[key]) for row in rows]
        if len(rows) != days or len(set(dates)) != days:
            raise ReadError(503, "analytics_daily_coverage_incomplete")
        if name == "funnel_daily" and any(
            row.get("observation_complete") is not True for row in rows
        ):
            raise ReadError(503, "analytics_facts_coverage_incomplete")
        if name == "store_daily" and any(
            row.get("currency") != self.policy.currency
            or row.get("reporting_timezone") != self.policy.reporting_timezone
            or row.get("history_complete") is not self.policy.history_complete
            or row.get("observation_complete") is not self.policy.history_complete
            for row in rows
        ):
            raise ReadError(503, "analytics_policy_mismatch")
        return rows

    def overview(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        rows = self._daily("store_daily", start, end)
        population = self._rows("customer_period", from_day=start, to_day=end)
        if len(population) != 1:
            raise ReadError(503, "invalid_customer_period")
        requested = _sum_money(rows, "revenue_generated")
        fulfilled = _sum_money(rows, "revenue_fulfilled")
        gap = (
            decimal_string(Decimal(requested) - Decimal(fulfilled))
            if requested is not None
            and fulfilled is not None
            and Decimal(requested) >= Decimal(fulfilled)
            else None
        )
        data = {
            "requested_revenue": requested,
            "fulfilled_revenue": fulfilled,
            "fulfillment_rate": _ratio(fulfilled, requested),
            "fulfillment_gap": gap,
            "cancelled_requested_revenue": _sum_money(rows, "revenue_cancelled"),
            "orders_requested": _sum_count(rows, "orders_generated"),
            "orders_cancelled": _sum_count(rows, "orders_cancelled"),
            "buyers_observed": integer(population[0].get("buyers")),
            "recurring_buyers_observed": integer(population[0].get("recurring_buyers")),
            "purchase_frequency_observed": _ratio(
                population[0].get("qualifying_orders"), population[0].get("buyers")
            ),
            "new_customers_confirmed": None,
            "ltv_complete": None,
            "cac": None,
            "revenue_paid": None,
            "series": [
                {
                    "date": _date(row["order_date"]),
                    "requested": decimal_string(row.get("revenue_generated")),
                    "fulfilled": decimal_string(row.get("revenue_fulfilled")),
                    "orders": integer(row.get("orders_generated")),
                    "new_customers_confirmed": integer(row.get("new_customers"))
                    if self.policy.history_complete
                    else None,
                }
                for row in rows
            ],
        }
        return self._response(
            data,
            limitations=[
                "leads_not_in_analytics_v1",
                "paid_media_not_materialized",
                "payment_not_certified",
                "ltv_requires_complete_history",
            ],
        )

    def _customer(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "store_id": self.grant.store_id,
            "customer_id": row["customer_id"],
            "customer_type": row.get("customer_type"),
            "name": row.get("trade_name") or row.get("company_name") or row.get("name"),
            "state": row.get("state"),
            "city": row.get("city"),
            "purchases_observed": integer(row.get("purchases")),
            "first_purchase_at_observed": _timestamp(row["first_purchase_at"])
            if row.get("first_purchase_at") is not None
            else None,
            "requested_lifetime_observed": decimal_string(row.get("ltv_lifetime_observed")),
            "ltv_complete": decimal_string(row.get("ltv_paid"))
            if self.policy.history_complete
            else None,
        }

    def _page(
        self, name: str, size: int, cursor: str | None, *, extra: dict[str, object] | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        context = cursor_context(self.principal, self.grant, self.publication, name, size)
        if extra:
            context.update(extra)
        after = self.cursors.decode(cursor, context) if cursor else ""
        rows = self._rows(name, after=after, limit=size + 1, **(extra or {}))
        if len(rows) > size + 1:
            raise ReadError(503, "unbounded_page")
        has_next = len(rows) > size
        selected = rows[:size]
        next_cursor = (
            self.cursors.encode(context, str(selected[-1]["cursor_key"]))
            if has_next and selected
            else None
        )
        return selected, {"page_size": size, "cursor": next_cursor, "has_more": has_next}

    def customers(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        size: str | None = None,
        cursor: str | None = None,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        extra: dict[str, object] | None = None
        if from_day is not None or to_day is not None:
            start, end = self._interval(from_day, to_day)
            extra = {"from_day": start, "to_day": end}
        selected, pagination = self._page("customers", page_size(size), cursor, extra=extra)
        return self._response(
            [self._customer(row) for row in selected],
            pagination=pagination,
            limitations=["observed_buyers_only", "core_profile_not_source_generation_pinned"],
        )

    def _customer_row(self, customer_id: str) -> dict[str, Any]:
        if not customer_id or len(customer_id) > 200:
            raise ReadError(400, "invalid_customer_id")
        rows = self._rows("customer", customer=customer_id, limit=2)
        if not rows:
            raise ReadError(404, "customer_not_found")
        if len(rows) != 1:
            raise ReadError(503, "duplicate_customer_metric")
        return rows[0]

    def customer(
        self, principal: Principal | None, grant: Grant, customer_id: str
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        row = self._customer_row(customer_id)
        summary = self._rows("customer_summary", customer=customer_id)
        if len(summary) != 1:
            raise ReadError(503, "invalid_customer_summary")
        commercial = {
            "qualifying_orders_observed": integer(summary[0].get("qualifying_orders")),
            "requested_revenue_observed": decimal_string(summary[0].get("requested")),
            "fulfilled_revenue_observed": decimal_string(summary[0].get("fulfilled")),
            "first_purchase_at_observed": _timestamp(summary[0]["first_purchase_at"])
            if summary[0].get("first_purchase_at") is not None
            else None,
            "last_purchase_at_observed": _timestamp(summary[0]["last_purchase_at"])
            if summary[0].get("last_purchase_at") is not None
            else None,
            "ltv_complete": None,
        }
        return self._response(
            {"profile": self._customer(row), "commercial": commercial},
            limitations=[
                "customer_360_not_materialized",
                "core_profile_not_source_generation_pinned",
            ],
        )

    def customer_orders(
        self,
        principal: Principal | None,
        grant: Grant,
        customer_id: str,
        *,
        size: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        self._customer_row(customer_id)  # Avoid IDOR and reject a foreign-store customer.
        selected, pagination = self._page(
            "orders",
            page_size(size),
            cursor,
            extra={
                "customer": customer_id,
                "history_from": self.policy.history_from,
                "as_of": self.publication.as_of,
            },
        )
        return self._response(
            [self._order(row) for row in selected],
            pagination=pagination,
            limitations=["core_orders_not_source_generation_pinned", "fulfilled_is_not_paid"],
        )

    def _order(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "store_id": self.grant.store_id,
            "customer_id": row.get("customer_id"),
            "order_id": row["order_id"],
            "created_at": _timestamp(row["created_at"]),
            "order_status": row.get("order_status"),
            "payment_status": row.get("payment_status"),
            "requested_total": decimal_string(row.get("requested_total")),
            "fulfilled_total": decimal_string(row.get("fulfilled_total")),
            "requested_items_qty": integer(row.get("requested_items_qty")),
            "fulfilled_items_qty": integer(row.get("fulfilled_items_qty")),
        }

    def orders(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
        size: str | None = None,
        cursor: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        if status is not None and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,49}", status):
            raise ReadError(400, "invalid_order_status")
        selected, pagination = self._page(
            "store_orders",
            page_size(size),
            cursor,
            extra={
                "from_day": start,
                "to_day": end,
                "status": status,
                "timezone": self.policy.reporting_timezone,
                "as_of": self.publication.as_of,
            },
        )
        return self._response(
            [self._order(row) for row in selected],
            pagination=pagination,
            limitations=[
                "core_orders_not_source_generation_pinned",
                "fulfilled_is_not_paid",
                "payment_not_certified",
            ],
        )

    def acquisition(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        population = self._rows("customer_period", from_day=start, to_day=end)
        first = self._rows("acquisition_first", from_day=start, to_day=end)
        if len(population) != 1 or len(first) != 1 or first[0].get("invalid_first_orders") != 0:
            raise ReadError(503, "invalid_first_purchase_sequence")
        row = first[0]
        return self._response(
            {
                "buyers_observed": integer(population[0].get("buyers")),
                "first_purchase_customers_observed": integer(row.get("customers")),
                "first_purchase_orders_observed": integer(row.get("orders")),
                "requested_first_purchase_observed": decimal_string(row.get("requested")),
                "fulfilled_first_purchase_observed": decimal_string(row.get("fulfilled")),
                "confirmed_new_customers": integer(row.get("customers"))
                if self.policy.history_complete
                else None,
            },
            limitations=[
                "first_purchase_is_observed_not_confirmed",
                "leads_not_in_analytics_v1",
                "approval_to_purchase_not_certified",
            ],
        )

    def retention(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        population = self._rows("customer_period", from_day=start, to_day=end)
        distribution = self._rows("retention_distribution")
        cohorts = self._rows("retention_cohorts")
        gaps = self._rows("retention_gaps")
        if len(population) != 1 or len(distribution) > 1000 or len(cohorts) > 1000:
            raise ReadError(503, "retention_result_unbounded")
        by_stage: dict[str, int] = {}
        for row in distribution:
            bucket = str(row["purchase_bucket"])
            by_stage[bucket] = by_stage.get(bucket, 0) + (integer(row["customers"]) or 0)
        gap_map = {integer(row["stage"]): row for row in gaps}
        stages = []
        for stage in range(1, 5):
            previous = by_stage.get(str(stage), 0)
            reached = by_stage.get("5+" if stage == 4 else str(stage + 1), 0)
            gap = gap_map.get(stage + 1)
            stages.append(
                {
                    "from_purchase": stage,
                    "to_purchase": "5+" if stage == 4 else str(stage + 1),
                    "customers_reached_observed": reached,
                    "continuation_observed": _ratio(reached, previous),
                    "mean_days_observed": _float(gap.get("mean_days")) if gap else None,
                    "median_days_observed": _float(gap.get("median_days")) if gap else None,
                }
            )
        data = {
            "buyers_observed": integer(population[0].get("buyers")),
            "recurring_buyers_observed": integer(population[0].get("recurring_buyers")),
            "retention_observed": _ratio(
                population[0].get("recurring_buyers"), population[0].get("buyers")
            ),
            "retention_ticket_observed": _ratio(
                population[0].get("recurring_fulfilled"), population[0].get("recurring_orders")
            ),
            "frequency_observed": _ratio(
                population[0].get("qualifying_orders"), population[0].get("buyers")
            ),
            "progression": stages,
            "cohorts": [
                {
                    "cohort_month": _date(row["cohort_month"]),
                    "reporting_month": _date(row["reporting_month"]),
                    "month": integer(row.get("months_since_first_purchase")),
                    "buyers_observed": integer(row.get("customers_in_cohort")),
                    "rate": decimal_string(row.get("retention_rate"))
                    if row.get("period_complete") is True
                    else None,
                    "observed_rate": decimal_string(row.get("observed_retention_rate"))
                    if row.get("period_complete") is True
                    else None,
                    "period_complete": row.get("period_complete") is True,
                }
                for row in cohorts
            ],
        }
        return self._response(data, limitations=["first_purchase_is_observed_not_confirmed"])

    def products(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
        size: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        selected, pagination = self._page(
            "products", page_size(size), cursor, extra={"from_day": start, "to_day": end}
        )
        return self._response(
            [
                {
                    "store_id": self.grant.store_id,
                    "product_key": row["product_key"],
                    "product_id": row.get("product_id"),
                    "sku": row.get("sku"),
                    "name": None,
                    "requested_revenue": decimal_string(row.get("requested")),
                    "fulfilled_revenue": decimal_string(row.get("fulfilled")),
                    "units_requested": decimal_string(row.get("units_requested")),
                    "units_fulfilled": decimal_string(row.get("units_fulfilled")),
                    "orders_observed": integer(row.get("orders")),
                    "buyers_unique": None,
                }
                for row in selected
            ],
            pagination=pagination,
            limitations=[
                "product_name_not_in_analytics_v1",
                "unique_buyers_not_additive_across_days",
            ],
        )

    def funnel(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        rows = self._daily("funnel_daily", start, end)
        fields = (
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
        )
        totals = {field: _sum_count(rows, field) for field in fields}
        return self._response(
            {
                "totals": totals,
                "session_to_cart_rate": _ratio(totals["sessions_with_cart"], totals["sessions"]),
                "cart_to_checkout_rate": _ratio(
                    totals["sessions_cart_then_checkout"], totals["sessions_with_cart"]
                ),
                "checkout_to_purchase_rate": _ratio(
                    totals["sessions_cart_checkout_purchase"],
                    totals["sessions_cart_then_checkout"],
                ),
                "days": [
                    {
                        "date": _date(row["event_date"]),
                        **{field: integer(row.get(field)) for field in fields},
                    }
                    for row in rows
                ],
            },
            limitations=["funnel_events_not_financial_orders"],
        )

    def geography(self, principal: Principal | None, grant: Grant) -> dict[str, Any]:
        self._scope(principal, grant)
        # Current-state CORE location is not a certified historic geography dimension.
        raise ReadError(424, "geography_coverage_not_certified")
