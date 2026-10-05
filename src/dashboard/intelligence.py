"""Materialized #16 readers. Analytics V1 and Intelligence generations stay separate."""

from decimal import Decimal
from typing import Any

from src.dashboard.contracts import Grant, Principal, ReadError, metadata, page_size
from src.dashboard.queries import Query
from src.dashboard.service import DashboardService, _date, _timestamp
from src.intelligence.api import JOURNEY, PRODUCT, PROFILE, TIMELINE
from src.intelligence.live.schema import PUBLICATION, SCHEMAS
from src.utils.data import timestamp

DENIED = frozenset(
    "cpf cnpj email phone identity_path session_id visitor_id user_id fbclid fbc fbp gclid raw payload access_token".split()
)


def safe(row: dict[str, Any], fields: str, schema: str) -> dict[str, Any]:
    result = {}
    for key in fields.split():
        if key in DENIED:
            raise ReadError(503, "unsafe_intelligence_projection")
        value = row.get(key)
        typ = SCHEMAS[schema].fields.get(key)
        if typ == "NUMERIC" and value is not None:
            if isinstance(value, float):
                raise ReadError(503, "invalid_numeric_value")
            value = format(Decimal(str(value)), "f")
        elif typ == "TIMESTAMP" and value is not None:
            value = _timestamp(value)
        elif typ == "DATE" and value is not None:
            value = _date(value)
        result[key] = value
    return result


class IntelligenceDashboardService(DashboardService):
    def _iq(
        self, name: str, sql: str, parameters: dict[str, tuple[str, object]]
    ) -> list[dict[str, Any]]:
        return self.reader.query(
            Query("intelligence_" + name, sql, parameters),
            request_id=self.request_id,
            store_id=self.grant.store_id,
            generation=getattr(self, "intelligence_head", {}).get("generation"),
        )

    def _intelligence_scope(self, principal: Principal | None, grant: Grant) -> None:
        self._scope(principal, grant)
        self._resolve_intelligence()

    def _resolve_intelligence(self) -> None:
        pub = f"`{self.project}.up_analytics.{PUBLICATION}`"
        params: dict[str, tuple[str, object]] = {
            "store": ("STRING", self.grant.store_id),
            "policy": ("STRING", self.policy.policy_hash),
        }
        rows = self._iq(
            "head",
            f"SELECT h.*,TO_JSON_STRING(r) receipt_json FROM {pub} h LEFT JOIN {pub} r ON r.record_kind='RECEIPT' AND r.store_id=h.store_id AND r.policy_hash=h.policy_hash AND r.publication_id=h.publication_id WHERE h.record_kind='HEAD' AND h.store_id=@store AND h.policy_hash=@policy",
            params,
        )
        if not rows or (len(rows) == 1 and rows[0].get("status") == "initialized"):
            raise ReadError(424, "intelligence_publication_unavailable")
        if len(rows) != 1:
            raise ReadError(503, "intelligence_publication_invalid")
        import json

        from src.intelligence.live.runtime import primitive

        h = primitive(dict(rows[0]))
        receipt = h.pop("receipt_json", None)
        r = json.loads(receipt) if isinstance(receipt, str) else primitive(receipt)
        for row in (h, r):
            if isinstance(row, dict):
                for field in ("row_counts", "limitations"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
        if not isinstance(r, dict) or any(
            h.get(k) != r.get(k)
            for k in SCHEMAS[PUBLICATION].fields
            if k not in {"row_key", "record_kind", "as_of", "calculated_at", "source_snapshot_at"}
        ):
            raise ReadError(503, "intelligence_publication_invalid")
        counts = h.get("row_counts")
        if (
            not isinstance(counts, dict)
            or set(counts) != set(SCHEMAS) - {PUBLICATION}
            or any(type(n) is not int or n < 0 for n in counts.values())
        ):
            raise ReadError(503, "intelligence_publication_invalid")
        if (
            h.get("status") != "completed"
            or type(h.get("generation")) is not int
            or h["generation"] < 1
            or h.get("base_generation") != self.publication.generation
            or h.get("base_publication_id") != self.publication.publication_id
            or timestamp(_timestamp(h.get("as_of"))) != timestamp(self.publication.as_of)
            or str(h.get("report_from")) != self.publication.report_from
            or str(h.get("report_to")) != self.publication.report_to
            or h.get("history_complete") != self.policy.history_complete
            or h.get("facts_complete") != self.policy.facts_complete
            or h.get("customer_intelligence_complete") is not True
            or h.get("performance_complete") is not True
        ):
            raise ReadError(503, "intelligence_publication_incompatible")
        for field in ("as_of", "calculated_at", "source_snapshot_at"):
            if timestamp(_timestamp(h[field])) != timestamp(_timestamp(r[field])):
                raise ReadError(503, "intelligence_publication_invalid")
        self.intelligence_head = h

    def _model(
        self,
        name: str,
        *,
        customer: str | None = None,
        campaign: str | None = None,
        after: str = "",
        limit: int = 101,
        scope: str | None = None,
        influenced_only: bool = False,
    ) -> list[dict[str, Any]]:
        if name not in SCHEMAS or name == PUBLICATION:
            raise ReadError(400, "intelligence_model_not_allowed")
        h = self.intelligence_head
        params: dict[str, tuple[str, object]] = {
            "store": ("STRING", self.grant.store_id),
            "policy": ("STRING", h["policy_hash"]),
            "generation": ("INT64", h["generation"]),
            "snapshot": ("TIMESTAMP", self.publication.snapshot_at),
            "after": ("STRING", after),
            "limit": ("INT64", limit),
            "from": ("DATE", self.intelligence_period[0]),
            "to": ("DATE", self.intelligence_period[1]),
            "timezone": ("STRING", self.policy.reporting_timezone),
        }
        where = (
            "store_id=@store AND policy_hash=@policy AND generation=@generation AND row_key>@after"
        )
        for field, value in (
            ("customer_id", customer),
            ("campaign_id", campaign),
            ("influence_scope", scope),
        ):
            if value is not None:
                if field not in SCHEMAS[name].fields and not (
                    field == "customer_id" and name == "analytics_campaign_performance_daily"
                ):
                    raise ReadError(400, "invalid_intelligence_filter")
                key = field.removesuffix("_id")
                params[key] = ("STRING", value)
                if not (field == "customer_id" and name == "analytics_campaign_performance_daily"):
                    where += f" AND {field}=@{key}"
        if influenced_only:
            where += " AND paid_media_influenced IS TRUE"
        if name == "analytics_campaign_performance_daily":
            from src.dashboard.intelligence_queries import campaigns

            params["campaign"] = ("STRING", campaign)
            sql = campaigns(self.project, customer_scoped=customer is not None)
        elif name == "analytics_campaign_customer_performance":
            from src.dashboard.intelligence_queries import campaign_customers_period

            sql = f"SELECT * FROM ({campaign_customers_period(self.project)}) WHERE {where} ORDER BY row_key LIMIT @limit"
        elif name == "analytics_campaign_order_performance":
            from src.dashboard.intelligence_queries import period_order_relations

            sql = f"SELECT * FROM ({period_order_relations(self.project)}) WHERE {where} ORDER BY row_key LIMIT @limit"
        else:
            if name == "analytics_customer_orders_summary":
                where += " AND DATE(created_at,@timezone)>=@from AND DATE(created_at,@timezone)<@to"
            fields = [k for k in SCHEMAS[name].fields if k not in DENIED]
            sql = f"SELECT {','.join('`' + k + '`' for k in fields)} FROM `{self.project}.up_analytics.{name}` FOR SYSTEM_TIME AS OF @snapshot WHERE {where} ORDER BY row_key LIMIT @limit"
        rows = self._iq(name, sql, params)
        if any(
            r.get("store_id") != self.grant.store_id
            or r.get("generation") != h["generation"]
            or r.get("policy_hash") != h["policy_hash"]
            or (customer is not None and r.get("customer_id") != customer)
            or (campaign is not None and r.get("campaign_id") != campaign)
            for r in rows
        ):
            raise ReadError(503, "intelligence_scope_mismatch")
        import json

        for row in rows:
            for field, typ in SCHEMAS[name].fields.items():
                if typ == "JSON" and isinstance(row.get(field), str):
                    row[field] = json.loads(row[field])
        return rows

    def _envelope(self, data: Any, pagination: dict[str, Any] | None = None) -> dict[str, Any]:
        h = self.intelligence_head
        m = metadata(self.publication, self.policy, list(h["limitations"]))
        m.update(
            generation=h["generation"],
            publication_domain="intelligence",
            analytics_generation=self.publication.generation,
            publication_id=h["publication_id"],
            meta_complete=h["meta_complete"],
            influence_complete=h["influence_complete"],
            customer_intelligence_complete=h["customer_intelligence_complete"],
            performance_complete=h["performance_complete"],
        )
        return {"data": data, "pagination": pagination, "metadata": m}

    def intelligence(
        self,
        principal: Principal | None,
        grant: Grant,
        resource: str,
        *,
        entity: str | None = None,
        size: str | None = None,
        cursor: str | None = None,
        from_day: str | None = None,
        to_day: str | None = None,
    ) -> dict[str, Any]:
        self._intelligence_scope(principal, grant)
        start, end = self._interval(from_day, to_day)
        self.intelligence_period = (start, end)
        period_resources = {
            "performance",
            "campaigns",
            "campaign",
            "campaignOrders",
            "campaignCustomers",
            "customerCampaigns",
            "influencedOrders",
        }
        if resource not in period_resources and (
            start != self.publication.report_from or end != self.publication.report_to
        ):
            raise ReadError(424, "intelligence_period_not_materialized")
        customer = (
            entity
            if resource in {"customer360", "timeline", "customerProducts", "customerCampaigns"}
            else None
        )
        campaign = (
            entity if resource in {"campaign", "campaignCustomers", "campaignOrders"} else None
        )
        if entity is not None and (not entity.strip() or len(entity) > 200):
            raise ReadError(400, "invalid_intelligence_entity")
        if customer:
            profiles = self._model("analytics_customer_360_profile", customer=customer, limit=2)
            if not profiles:
                raise ReadError(404, "customer_not_found")
            if len(profiles) != 1:
                raise ReadError(503, "duplicate_customer_profile")
        if campaign:
            # Entity belongs to this store/generation, never a global campaign lookup.
            catalog = self._model(
                "analytics_campaign_performance_daily", campaign=campaign, limit=1
            )
            if not catalog:
                raise ReadError(404, "campaign_not_found")
        if resource == "customer360":
            profile = safe(profiles[0], PROFILE, "analytics_customer_360_profile")
            from src.dashboard.intelligence_queries import customer_context

            h = self.intelligence_head
            context_rows = self._iq(
                "customer_context",
                customer_context(self.project),
                {
                    "store": ("STRING", grant.store_id),
                    "policy": ("STRING", h["policy_hash"]),
                    "generation": ("INT64", h["generation"]),
                    "snapshot": ("TIMESTAMP", self.publication.snapshot_at),
                    "customer": ("STRING", customer),
                },
            )
            if len(context_rows) != 1:
                raise ReadError(503, "customer_context_missing_or_duplicate")
            journey = context_rows[0].get("journey")
            influences = context_rows[0].get("marketing")
            if not isinstance(journey, list) or len(journey) != 1:
                raise ReadError(503, "customer_journey_missing_or_duplicate")
            if not isinstance(influences, list):
                raise ReadError(503, "influence_scopes_incomplete")
            if any(
                r.get("store_id") != grant.store_id
                or r.get("policy_hash") != h["policy_hash"]
                or r.get("generation") != h["generation"]
                or r.get("customer_id") != customer
                for r in journey + influences
            ):
                raise ReadError(503, "intelligence_scope_mismatch")
            if {r["influence_scope"] for r in influences} != {
                "LIFETIME",
                "ACQUISITION",
                "REPEAT_PURCHASE",
            } or len(influences) != 3:
                raise ReadError(503, "influence_scopes_incomplete")
            return self._envelope(
                {
                    "profile": profile,
                    "journey": safe(journey[0], JOURNEY, "analytics_customer_journey_summary"),
                    "marketing": [
                        safe(
                            r,
                            "influence_scope paid_media_influenced first_paid_touch_at last_paid_touch_at first_campaign_id last_campaign_id paid_touch_count campaign_count influenced_orders evidence_type",
                            "analytics_customer_paid_influence",
                        )
                        for r in influences
                    ],
                    "health_score": None,
                    "health_status": None,
                    "health_policy": "NOT_DEFINED",
                    "ltv_complete": None,
                }
            )
        if resource == "performance":
            from src.dashboard.intelligence_queries import performance_period

            h = self.intelligence_head
            rows = self._iq(
                "performance_period",
                performance_period(self.project),
                {
                    "store": ("STRING", grant.store_id),
                    "policy": ("STRING", h["policy_hash"]),
                    "generation": ("INT64", h["generation"]),
                    "snapshot": ("TIMESTAMP", self.publication.snapshot_at),
                    "from": ("DATE", start),
                    "to": ("DATE", end),
                    "timezone": ("STRING", self.policy.reporting_timezone),
                    "influence_complete": ("BOOL", h["influence_complete"]),
                    "meta_complete": ("BOOL", h["meta_complete"]),
                    "history_complete": ("BOOL", self.policy.history_complete),
                },
            )
            if len(rows) != 1:
                raise ReadError(503, "performance_summary_missing_or_duplicate")
            row = rows[0]
            if (
                row.get("store_id") != grant.store_id
                or row.get("policy_hash") != h["policy_hash"]
                or row.get("generation") != h["generation"]
            ):
                raise ReadError(503, "intelligence_scope_mismatch")
            if (
                not isinstance(row.get("summary"), dict)
                or not isinstance(row.get("series"), list)
                or len(row["series"]) > 366
            ):
                raise ReadError(503, "performance_period_invalid")
            fields = "meta_spend observed_meta_spend influenced_customers influenced_orders new_customers_influenced requested_revenue_influenced fulfilled_revenue_influenced requested_quantity_influenced fulfilled_quantity_influenced fulfillment_rate roas_requested roas_fulfilled cac_new_customer"
            data = safe(row["summary"], fields, "analytics_performance_summary")
            daily_fields = "date spend impressions clicks influenced_orders requested_revenue_influenced fulfilled_revenue_influenced"
            data.update(
                {
                    "ctr": row["summary"].get("ctr"),
                    "cpc": row["summary"].get("cpc"),
                    "cpm": row["summary"].get("cpm"),
                    "impressions": row["summary"].get("impressions"),
                    "clicks": row["summary"].get("clicks"),
                    "series": [
                        safe(r, daily_fields, "analytics_campaign_performance_daily")
                        for r in row["series"]
                    ],
                }
            )
            for field in ("ctr", "cpc", "cpm"):
                if data[field] is not None:
                    if isinstance(data[field], float):
                        raise ReadError(503, "invalid_numeric_value")
                    data[field] = format(Decimal(str(data[field])), "f")
            return self._envelope(data)
        models = {
            "timeline": "analytics_customer_timeline",
            "customerProducts": "analytics_customer_products_summary",
            "influencedOrders": "analytics_customer_orders_summary",
            "influencedCustomers": "analytics_customer_paid_influence",
            "campaigns": "analytics_campaign_performance_daily",
            "customerCampaigns": "analytics_campaign_performance_daily",
            "campaign": "analytics_campaign_performance_daily",
            "campaignCustomers": "analytics_campaign_customer_performance",
            "campaignOrders": "analytics_campaign_order_performance",
        }
        if resource not in models:
            raise ReadError(404, "intelligence_resource_not_found")
        name = models[resource]
        n = page_size(size)
        context = {
            "subject": self.principal.subject,
            "tenant": grant.tenant_id,
            "store": grant.store_id,
            "operation": grant.operation,
            "generation": self.intelligence_head["generation"],
            "analytics_generation": self.publication.generation,
            "policy": self.policy.policy_hash,
            "route": resource,
            "entity": entity,
            "from": from_day,
            "to": to_day,
            "page_size": n,
            "domain": "intelligence",
        }
        after = self.cursors.decode(cursor, context) if cursor else ""
        rows = self._model(
            name,
            customer=customer,
            campaign=campaign,
            after=after,
            limit=n + 1,
            scope="LIFETIME" if "influence_scope" in SCHEMAS[name].fields else None,
            influenced_only=resource in {"influencedOrders", "influencedCustomers"},
        )
        more = len(rows) > n
        rows = rows[:n]
        fields = (
            TIMELINE
            if resource == "timeline"
            else PRODUCT
            if resource == "customerProducts"
            else " ".join(
                k
                for k in SCHEMAS[name].fields
                if k not in DENIED | {"row_key", "policy_hash", "generation"}
            )
        )
        if resource in {"campaigns", "campaign", "customerCampaigns"}:
            fields = "campaign_id campaign_name campaign_status spend observed_spend impressions clicks ctr cpc cpm influenced_customers influenced_orders requested_revenue_influenced fulfilled_revenue_influenced roas_requested roas_fulfilled"
        result = [{**safe(r, fields, name), "record_key": r["row_key"]} for r in rows]
        token = self.cursors.encode(context, rows[-1]["row_key"]) if more and rows else None
        return self._envelope(result, {"page_size": n, "cursor": token, "has_more": more})

    def customer(
        self, principal: Principal | None, grant: Grant, customer_id: str
    ) -> dict[str, Any]:
        response = super().customer(principal, grant, customer_id)
        try:
            # Reuse the same authorized reader/request/base publication and its budget.
            self._resolve_intelligence()
            self.intelligence_period = (self.publication.report_from, self.publication.report_to)
            profile = self._model("analytics_customer_360_profile", customer=customer_id, limit=2)
            if len(profile) != 1:
                raise ReadError(503, "customer_profile_missing_or_duplicate")
            response["data"]["intelligence"] = {
                "profile": safe(profile[0], PROFILE, "analytics_customer_360_profile"),
                "generation": self.intelligence_head["generation"],
                "coverage": self.intelligence_head["customer_intelligence_complete"],
            }
        except ReadError as exc:
            if exc.status != 424:
                raise
            response["data"]["intelligence"] = None
        return response
