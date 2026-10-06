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
from src.connectors.meta.purchase_reporting import PurchaseCertificate
from src.dashboard.aggregate_cache import AggregateCache, cache_key
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


def resolve_publication(rows: list[dict[str, Any]], policy: AnalyticsPolicy) -> Publication:
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
        or (row.get("report_to") is not None and _publication_date(row["report_to"]) != receipt_to)
    ):
        raise ReadError(503, "publication_head_invalid")
    generation = integer(row.get("generation"))
    if generation is None:
        raise ReadError(503, "publication_head_invalid")
    publication = Publication(
        store_id=str(row.get("store_id")),
        policy_hash=str(row.get("policy_hash")),
        generation=generation,
        publication_id=str(row.get("publication_id")),
        snapshot_at=_timestamp(row.get("snapshot_at")),
        as_of=_timestamp(row.get("as_of")),
        report_from=receipt_from,
        report_to=receipt_to,
    )
    publication.validate(policy)
    return publication


class DashboardService:
    def __init__(
        self,
        project: str,
        policies: Mapping[str, AnalyticsPolicy],
        reader_factory: Callable[[], Reader],
        cursor_key: bytes,
        *,
        installation_v2: bool = False,
        catalog_enabled: bool = False,
        creatives_enabled: bool = False,
        images_enabled: bool = False,
        purchase_certificates: tuple[PurchaseCertificate, ...] = (),
        aggregate_cache: AggregateCache | None = None,
    ):
        self.project = project
        self.installation_v2 = installation_v2
        self.catalog_enabled = catalog_enabled
        self.creatives_enabled = creatives_enabled
        self.images_enabled = images_enabled
        self.purchase_certificates = purchase_certificates
        self.aggregate_cache = aggregate_cache
        self.aggregate_workspace: tuple[str, str, str, str] | None = None
        self.policies = dict(policies)
        self.reader_factory = reader_factory
        self.cursors = CursorCodec(cursor_key)
        if any(key != policy.store_id for key, policy in self.policies.items()):
            raise ValueError("policy_store_mismatch")

    def _query(self, name: str, **values: object) -> list[dict[str, Any]]:
        query = build(self.project, name, **values)
        key = None
        if self.aggregate_cache is not None and self.aggregate_workspace is not None:
            tenant, _, store, operation = self.aggregate_workspace
            if (tenant, store, operation) == (
                self.grant.tenant_id,
                self.grant.store_id,
                self.grant.operation,
            ) and hasattr(self, "publication"):
                key = cache_key(
                    self.project,
                    self.aggregate_workspace,
                    self.publication,
                    query,
                    (self.policy.history_complete, self.policy.facts_complete),
                )
            if key is not None:
                cached = self.aggregate_cache.get(key)
                if cached is not None:
                    return cached
        rows = self.reader.query(
            query,
            request_id=self.request_id,
            store_id=self.grant.store_id,
            generation=self.publication.generation if hasattr(self, "publication") else None,
        )
        if key is not None and self.aggregate_cache is not None:
            self.aggregate_cache.put(key, rows)
        return rows

    def _scope(self, principal: Principal | None, grant: Grant) -> None:
        if principal is None:
            raise ReadError(401, "unauthenticated")
        principal.authorize(grant.tenant_id, grant.store_id, grant.operation)
        self.grant = grant
        self.principal = principal
        self.request_id = uuid4().hex
        self.reader = self.reader_factory()
        from src.dashboard.catalog import CatalogReader

        self.catalog_reader: CatalogReader | None = None
        policy = self.policies.get(grant.store_id)
        if self.installation_v2:
            from src.installation.publication import resolve_policy

            installation = resolve_policy(
                self.reader,
                self.project,
                grant,
                self.request_id,
                consolidated=self.catalog_enabled,
            )
            if installation:
                self.policy, self.publication = installation
                return
        if policy is None:
            raise ReadError(404, "store_not_configured")
        self.policy = policy
        rows = self._query("head", store=grant.store_id, policy=self.policy.policy_hash)
        self.publication = resolve_publication(rows, self.policy)

    def _catalog(self, identifiers: list[str]) -> dict[str, dict[str, Any]]:
        if not self.catalog_enabled:
            return {}
        from src.dashboard.catalog import CatalogReader

        if self.catalog_reader is None:
            self.catalog_reader = CatalogReader(
                self.project,
                self.reader,
                self.grant.store_id,
                None,
                self.request_id,
                images_enabled=self.images_enabled,
            )
        return self.catalog_reader.variants(identifiers)

    def _catalog_family(self, product_id: str) -> dict[str, dict[str, Any]]:
        if not self.catalog_enabled or self.catalog_reader is None:
            return {}
        return self.catalog_reader.family(product_id)

    def meta_ads(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        if not self.creatives_enabled:
            raise ReadError(424, "meta_period_coverage_unavailable")
        from src.dashboard.meta_period import MetaPeriodReader

        data = MetaPeriodReader(
            self.project,
            self.reader,
            grant.store_id,
            self.request_id,
            self.publication.snapshot_at,
            self.purchase_certificates,
        ).read(start, end)
        return self._response(
            data,
            limitations=[
                "meta_reported_not_commercial_attribution",
                "creative_preview_current_not_historical",
            ],
        )

    def creatives(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        if not self.creatives_enabled:
            raise ReadError(424, "creative_coverage_unavailable")
        from src.dashboard.creatives import CreativeReader

        rows = CreativeReader(
            self.project,
            self.reader,
            grant.store_id,
            self.request_id,
            self.publication.snapshot_at,
            purchase_certificates=self.purchase_certificates,
        ).read(start, end)
        return self._response(
            rows,
            limitations=[
                "meta_reported_not_commercial_attribution",
                "creative_preview_current_not_historical",
                "reach_frequency_period_not_certified",
            ],
        )

    def installation(self, principal: Principal | None, grant: Grant) -> dict[str, Any]:
        from src.dashboard.installation import InstallationReader

        return InstallationReader(self.project, self.policies, self.reader_factory).read(
            principal, grant
        )

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

    def _daily(
        self, name: str, start: str, end: str, rows: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        if rows is None:
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

    def _operational_leads(
        self, start: str, end: str, rows: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        if not self.catalog_enabled:
            return {}
        from src.dashboard.leads import operational_counts

        if rows is None:
            rows = self._rows(
                "operational_leads",
                from_day=start,
                to_day=end,
                as_of=self.publication.as_of,
                timezone=self.policy.reporting_timezone,
            )
        if len(rows) != 1:
            raise ReadError(503, "lead_summary_missing_or_duplicate")
        return operational_counts(rows[0], facts_complete=self.policy.facts_complete)

    def _overview_data(self, start: str, end: str) -> dict[str, Any]:
        """Shared commercial projection. No new scope, reader or publication resolution."""
        bundle: dict[str, list[dict[str, Any]]] = {}
        if self.catalog_enabled:
            combined = self._rows(
                "overview_details",
                from_day=start,
                to_day=end,
                as_of=self.publication.as_of,
                timezone=self.policy.reporting_timezone,
            )
            if len(combined) != 1 or any(
                not isinstance(combined[0].get(key), list)
                or any(not isinstance(row, dict) for row in combined[0][key])
                for key in ("daily", "population", "quantities", "leads")
            ):
                raise ReadError(503, "overview_details_invalid")
            bundle = combined[0]
        rows = self._daily("store_daily", start, end, bundle.get("daily"))
        population = (
            bundle["population"]
            if bundle
            else self._rows("customer_period", from_day=start, to_day=end)
        )
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
        quantities: dict[str, Any] = {}
        if self.catalog_enabled:
            summary = bundle["quantities"]
            if (
                len(summary) != 1
                or summary[0].get("duplicate_orders") != 0
                or summary[0].get("invalid_identity") != 0
                or summary[0].get("orders") != _sum_count(rows, "orders_generated")
            ):
                raise ReadError(503, "order_quantity_summary_not_reconciled")
            paid = integer(summary[0].get("paid_orders"))
            unknown_payment = integer(summary[0].get("unknown_payment_status"))
            if (paid is not None and not 0 <= paid <= summary[0]["orders"]) or (
                unknown_payment is not None and not 0 <= unknown_payment <= summary[0]["orders"]
            ):
                raise ReadError(503, "order_payment_summary_invalid")
            quantities = {
                "requested_pieces": integer(summary[0].get("requested_pieces")),
                "fulfilled_pieces": integer(summary[0].get("fulfilled_pieces")),
                "requested_pieces_per_order": _ratio(
                    summary[0].get("requested_pieces"), summary[0].get("orders")
                ),
                "orders_paid": paid if unknown_payment == 0 else None,
                "orders_paid_rate": (
                    _ratio(paid * 100 if paid is not None else None, summary[0]["orders"])
                    if unknown_payment == 0
                    else None
                ),
                "monthly_payments": [
                    {**row, "month": _date(row["month"])} for row in summary[0].get("monthly", [])
                ],
            }
        leads = self._operational_leads(start, end, bundle.get("leads"))
        return {
            **quantities,
            "retention_ticket_observed": _ratio(
                population[0].get("recurring_fulfilled"), population[0].get("recurring_orders")
            ),
            "repeat_mean_days_observed": _float(population[0].get("repeat_mean_days")),
            **leads,
            "requested_revenue": requested,
            "fulfilled_revenue": fulfilled,
            "average_requested_ticket": _ratio(requested, _sum_count(rows, "orders_generated")),
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
            "monthly_customers": [
                {
                    "month": str(r["month"]),
                    "buyers_observed": integer(r.get("buyers")),
                    "recurring_buyers_observed": integer(r.get("recurring_buyers")),
                    "qualifying_orders": integer(r.get("qualifying_orders")),
                }
                for r in population[0].get("monthly", [])
            ],
            "series": [
                {
                    "date": _date(row["order_date"]),
                    "requested": decimal_string(row.get("revenue_generated")),
                    "fulfilled": decimal_string(row.get("revenue_fulfilled")),
                    "orders": integer(row.get("orders_generated")),
                    "cancelled_requested": decimal_string(row.get("revenue_cancelled")),
                    "new_customers_confirmed": integer(row.get("new_customers"))
                    if self.policy.history_complete
                    else None,
                }
                for row in rows
            ],
        }

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
        data = self._overview_data(start, end)
        leads = data
        return self._response(
            data,
            limitations=[
                *leads.get("lead_coverage", {}).get(
                    "limitations", ["operational_registration_read_not_enabled"]
                ),
                "paid_media_has_separate_intelligence_publication",
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
            "fulfilled_lifetime_observed": decimal_string(row.get("summary_fulfilled")),
            "last_purchase_at_observed": _timestamp(row["last_observed_at"])
            if row.get("last_observed_at") is not None
            else None,
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
        if integer(row.get("qualifying_orders")) != integer(row.get("purchases")):
            raise ReadError(503, "invalid_customer_summary")
        commercial = {
            "qualifying_orders_observed": integer(row.get("qualifying_orders")),
            "requested_revenue_observed": decimal_string(row.get("summary_requested")),
            "fulfilled_revenue_observed": decimal_string(row.get("summary_fulfilled")),
            "first_purchase_at_observed": _timestamp(row["first_observed_at"])
            if row.get("first_observed_at") is not None
            else None,
            "last_purchase_at_observed": _timestamp(row["last_observed_at"])
            if row.get("last_observed_at") is not None
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

    def customer_contact(
        self,
        principal: Principal | None,
        grant: Grant,
        customer_id: str,
        *,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        """Authorized, on-demand contact only. Never part of list/commercial DTOs."""
        self._scope(principal, grant)
        if not customer_id or len(customer_id) > 200:
            raise ReadError(400, "invalid_customer_id")
        basis = "current_core_profile"
        if order_id:
            if len(order_id) > 200:
                raise ReadError(400, "invalid_order_id")
            rows = self._rows("order_contact", customer=customer_id, order=order_id)
            if not rows:
                raise ReadError(404, "order_not_found")
            basis = "order_snapshot"
        else:
            rows = self._rows("customer_contact", customer=customer_id)
        if not rows:
            raise ReadError(404, "customer_not_found")
        if len(rows) != 1:
            raise ReadError(503, "customer_contact_identity_ambiguous")
        row = rows[0]
        if row.get("store_id") != grant.store_id or row.get("customer_id") != customer_id:
            raise ReadError(503, "customer_contact_identity_invalid")
        contact: dict[str, Any] = {"basis": basis, "observed_at": None}
        for field in ("cpf", "cnpj", "email", "phone", "state", "city"):
            value = row.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 320):
                raise ReadError(503, "customer_contact_invalid")
            contact[field] = value
        if row.get("observed_at") is not None:
            contact["observed_at"] = _timestamp(row["observed_at"])
        return self._response(
            contact,
            limitations=["current_core_profile_not_historical_order_contact"]
            if basis == "current_core_profile"
            else ["order_snapshot_contact"],
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
        first_purchase: bool = False,
    ) -> dict[str, Any]:
        self._scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        if status is not None and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,49}", status):
            raise ReadError(400, "invalid_order_status")
        if type(first_purchase) is not bool:
            raise ReadError(400, "invalid_first_purchase_filter")
        selected, pagination = self._page(
            "store_orders",
            page_size(size),
            cursor,
            extra={
                "from_day": start,
                "to_day": end,
                "status": status,
                "first_purchase": first_purchase,
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
        leads = self._operational_leads(start, end)
        return self._response(
            {
                **leads,
                "buyers_observed": integer(population[0].get("buyers")),
                "first_purchase_customers_observed": integer(row.get("customers")),
                "first_purchase_orders_observed": integer(row.get("orders")),
                "requested_first_purchase_observed": decimal_string(row.get("requested")),
                "ticket_first_purchase_observed": _ratio(row.get("requested"), row.get("orders")),
                "fulfilled_first_purchase_observed": decimal_string(row.get("fulfilled")),
                "confirmed_new_customers": integer(row.get("customers"))
                if self.policy.history_complete
                else None,
            },
            limitations=[
                "first_purchase_is_observed_not_confirmed",
                *leads.get("lead_coverage", {}).get(
                    "limitations", ["operational_registration_read_not_enabled"]
                ),
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
        details = self._rows("retention_details", from_day=start, to_day=end)
        if len(details) != 1:
            raise ReadError(503, "retention_details_invalid")
        distribution, cohorts, gaps, series = (
            details[0][field] for field in ("distribution", "cohorts", "gaps", "series")
        )
        if (
            len(population) != 1
            or any(not isinstance(rows, list) for rows in (distribution, cohorts, gaps, series))
            or len(distribution) > 1000
            or len(cohorts) > 1000
            or len(gaps) > 4
            or len(series) > 366
        ):
            raise ReadError(503, "retention_result_unbounded")
        dates = [_date(row["order_date"]) for row in series]
        if len(set(dates)) != len(dates) or any(not start <= day < end for day in dates):
            raise ReadError(503, "retention_series_invalid")
        by_stage: dict[str, int] = {}
        for row in distribution:
            bucket = str(row["purchase_bucket"])
            count = integer(row["customers"])
            if count is None or count < 0 or bucket not in {"1", "2", "3", "4", "5+"}:
                raise ReadError(503, "retention_population_invalid")
            by_stage[bucket] = by_stage.get(bucket, 0) + count
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
        purchase_stages = []
        accumulated: str | None = "0"
        for stage in range(1, 6):
            bucket = "5+" if stage == 5 else str(stage)
            rows = [r for r in distribution if str(r["purchase_bucket"]) == bucket]
            revenue = _sum_money(rows, "revenue")
            accumulated = (
                None
                if accumulated is None or revenue is None
                else format(Decimal(accumulated) + Decimal(revenue), "f")
            )
            previous_stage = by_stage.get(str(stage - 1), 0) if stage > 1 else None
            count = by_stage.get(bucket, 0)
            purchase_stages.append(
                {
                    "stage": stage,
                    "buyers_observed": count,
                    "share_observed": _ratio(count, by_stage.get("1", 0)),
                    "continuation_observed": _ratio(count, previous_stage)
                    if previous_stage is not None
                    else None,
                    "requested_revenue_observed": revenue,
                    "accumulated_requested_revenue_observed": accumulated,
                    "mean_days_observed": _float(gap_map[stage].get("mean_days"))
                    if stage in gap_map
                    else None,
                }
            )
        data = {
            "purchase_stages": purchase_stages,
            "series": [
                {
                    "date": _date(r["order_date"]),
                    "buyers_observed": integer(r.get("buyers")),
                    "recurring_buyers_observed": integer(r.get("recurring_buyers")),
                    "retention_observed": _ratio(r.get("recurring_buyers"), r.get("buyers")),
                    "retention_ticket_observed": _ratio(
                        r.get("recurring_fulfilled"), r.get("recurring_orders")
                    ),
                }
                for r in series
            ],
            "buyers_observed": integer(population[0].get("buyers")),
            "recurring_buyers_observed": integer(population[0].get("recurring_buyers")),
            "retention_observed": _ratio(
                population[0].get("recurring_buyers"), population[0].get("buyers")
            ),
            "retention_ticket_observed": _ratio(
                population[0].get("recurring_fulfilled"), population[0].get("recurring_orders")
            ),
            "repeat_mean_days_observed": _float(population[0].get("repeat_mean_days")),
            "repeat_median_days_observed": _float(population[0].get("repeat_median_days")),
            "recurring_fulfilled_observed": decimal_string(
                population[0].get("recurring_fulfilled")
            ),
            "recurring_orders_observed": integer(population[0].get("recurring_orders")),
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
        if self.catalog_enabled:
            exact = self._rows("retention_exact_stages", from_day=start, to_day=end)
            indexed: dict[int, dict[str, Any]] = {}
            for row in exact:
                exact_stage = integer(row.get("stage"))
                if (
                    exact_stage is None
                    or not 1 <= exact_stage <= 6
                    or exact_stage in indexed
                    or row.get("duplicate_orders") != 0
                    or row.get("invalid_identity") != 0
                    or integer(row.get("orders")) != integer(row.get("buyers"))
                    or integer(row.get("buyers")) is None
                    or row["buyers"] < 0
                ):
                    raise ReadError(503, "retention_exact_stages_invalid")
                indexed[exact_stage] = row
            if len(exact) > 6:
                raise ReadError(503, "retention_exact_stages_invalid")
            accumulated = "0"
            exact_stages = []
            for stage in range(1, 7):
                # Missing group is certified absence within this observed period,
                # never a claim about lifetime history.
                row = indexed.get(stage, {"buyers": 0, "orders": 0, "requested": "0"})
                revenue = decimal_string(row.get("requested"))
                accumulated = (
                    None
                    if revenue is None or accumulated is None
                    else format(Decimal(accumulated) + Decimal(revenue), "f")
                )
                exact_stages.append(
                    {
                        "stage": stage,
                        "buyers_observed": row["buyers"],
                        "share_observed": _ratio(
                            row["buyers"], indexed.get(1, {}).get("buyers", 0)
                        ),
                        "continuation_observed": None,
                        "requested_revenue_observed": revenue,
                        "accumulated_requested_revenue_observed": accumulated,
                        "mean_days_observed": _float(row.get("mean_days")),
                    }
                )
            data["exact_purchase_stages"] = exact_stages
            data["exact_purchase_stages_basis"] = "observed_purchase_number_in_selected_period"
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
            "products",
            page_size(size),
            cursor,
            extra={
                "from_day": start,
                "to_day": end,
                "as_of": self.publication.as_of,
                "timezone": self.policy.reporting_timezone,
            },
        )
        catalog = self._catalog(
            sorted({row["variant_id"] for row in selected if row.get("variant_id")})
        )
        return self._response(
            [
                {
                    "store_id": self.grant.store_id,
                    "product_key": row["product_key"],
                    "product_id": row.get("product_id")
                    or catalog.get(row.get("variant_id") or "", {}).get("product_id"),
                    "sku": row.get("sku"),
                    "name": row.get("name")
                    or catalog.get(row.get("variant_id") or "", {}).get("name"),
                    "reference": catalog.get(row.get("variant_id") or "", {}).get("reference"),
                    "image": catalog.get(row.get("variant_id") or "", {}).get("image"),
                    "catalog": catalog.get(row.get("variant_id") or "", {}).get("catalog"),
                    "requested_revenue": decimal_string(row.get("requested")),
                    "fulfilled_revenue": decimal_string(row.get("fulfilled")),
                    "units_requested": decimal_string(row.get("units_requested")),
                    "units_fulfilled": decimal_string(row.get("units_fulfilled")),
                    "orders_observed": integer(row.get("orders")),
                    "buyers_unique": integer(row.get("buyers_unique")),
                }
                for row in selected
            ],
            pagination=pagination,
            limitations=[
                "product_identity_uses_exact_current_core_variant_sku",
                "current_core_at_publication_read_snapshot",
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
        if self.catalog_enabled:
            extra = self._rows(
                "funnel_extra",
                from_day=start,
                to_day=end,
                as_of=self.publication.as_of,
                timezone=self.policy.reporting_timezone,
            )
            if len(extra) != 1:
                raise ReadError(503, "funnel_extra_invalid")
            totals["purchase_item"] = (
                integer(extra[0].get("purchase_item"))
                if self.policy.facts_complete and extra[0].get("invalid_identity") == 0
                else None
            )
        return self._response(
            {
                "totals": totals,
                "session_to_purchase_rate": _ratio(
                    totals["sessions_with_purchase"], totals["sessions"]
                ),
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

    def order(self, principal: Principal | None, grant: Grant, order_id: str) -> dict[str, Any]:
        from src.dashboard.product_reads import order

        return order(self, principal, grant, order_id)

    def product(
        self,
        principal: Principal | None,
        grant: Grant,
        product_key: str,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        from src.dashboard.product_reads import product

        return product(self, principal, grant, product_key, from_day, to_day)

    def geography(
        self,
        principal: Principal | None,
        grant: Grant,
        *,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        from src.dashboard.product_reads import geography

        return geography(self, principal, grant, from_day, to_day)
