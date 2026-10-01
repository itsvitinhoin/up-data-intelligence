"""Read-only bounded invariants; returns counts, never identifiers or customer payloads."""

from typing import Any

from src.analytics.cloud.transport import Transport, scalar
from src.analytics.config import AnalyticsPolicy
from src.dashboard.contracts import Grant, Principal
from src.dashboard.intelligence import IntelligenceDashboardService
from src.dashboard.repository import BigQueryReadSession, ReadBudget
from src.intelligence.live.schema import PUBLICATION, SCHEMAS


def sql(project: str) -> str:
    pieces = []
    for name in SCHEMAS:
        if name == PUBLICATION:
            continue
        table = f"`{project}.up_analytics.{name}`"
        pieces.append(
            f"SELECT '{name}:duplicate_key' invariant,COUNT(*) failures FROM (SELECT row_key FROM {table} WHERE store_id=@store AND policy_hash=@policy AND generation=@generation GROUP BY row_key HAVING COUNT(*)>1)"
        )
    prefix = f"`{project}.up_analytics."
    scope = "store_id=@store AND policy_hash=@policy AND generation=@generation"
    pieces += [
        f"SELECT 'timeline:foreign_customer',COUNT(*) FROM {prefix}analytics_customer_timeline` AS t WHERE t.{scope.replace(' AND ', ' AND t.')} AND NOT EXISTS(SELECT 1 FROM {prefix}analytics_customer_360_profile` p WHERE p.store_id=t.store_id AND p.policy_hash=t.policy_hash AND p.generation=t.generation AND p.customer_id=t.customer_id)",
        f"SELECT 'campaign:duplicate_order',COUNT(*) FROM (SELECT campaign_id,order_id,influence_scope FROM {prefix}analytics_campaign_order_performance` WHERE {scope} GROUP BY campaign_id,order_id,influence_scope HAVING COUNT(*)>1)",
        f"SELECT 'influence:duplicate_order_campaign',COUNT(*) FROM (SELECT order_id,campaign_id,influence_scope FROM {prefix}analytics_order_paid_influence` WHERE {scope} GROUP BY order_id,campaign_id,influence_scope HAVING COUNT(*)>1)",
        f"SELECT 'meta:duplicate_campaign_day_config',COUNT(*) FROM (SELECT campaign_id,date_start,configuration_hash FROM `{project}.up_core.meta_live_insights_daily` FOR SYSTEM_TIME AS OF @snapshot WHERE store_id=@store AND account_id=@account AND configuration_hash=@configuration AND date_start>=@from AND date_start<@to GROUP BY campaign_id,date_start,configuration_hash HAVING COUNT(*)>1)",
        f"SELECT 'summary:meta_spend',COUNT(*) FROM {prefix}analytics_performance_summary` s WHERE s.{scope.replace(' AND ', ' AND s.')} AND s.meta_spend IS DISTINCT FROM (SELECT IF(COUNTIF(spend IS NULL)>0,NULL,COALESCE(SUM(spend),0)) FROM `{project}.up_core.meta_live_insights_daily` FOR SYSTEM_TIME AS OF @snapshot WHERE store_id=@store AND account_id=@account AND configuration_hash=@configuration AND date_start>=@from AND date_start<@to)",
        f"SELECT 'summary:dedupe_revenue_null_roas',COUNT(*) FROM {prefix}analytics_performance_summary` s WHERE s.{scope.replace(' AND ', ' AND s.')} AND (influenced_customers>influenced_orders OR (NOT history_complete AND (new_customers_influenced IS NOT NULL OR cac_new_customer IS NOT NULL)) OR (NOT influence_complete AND (roas_requested IS NOT NULL OR roas_fulfilled IS NOT NULL)) OR influenced_orders IS DISTINCT FROM (SELECT COUNT(DISTINCT order_id) FROM {prefix}analytics_customer_orders_summary` o WHERE o.store_id=s.store_id AND o.policy_hash=s.policy_hash AND o.generation=s.generation AND o.influence_scope='LIFETIME' AND o.paid_media_influenced IS TRUE))",
    ]
    # Revenue is selected once per order, never summed across campaign participation.
    pieces.append(f"""SELECT 'summary:distinct_order_finance',COUNT(*) FROM {prefix}analytics_performance_summary` s
      WHERE s.{scope.replace(" AND ", " AND s.")} AND EXISTS(
       SELECT 1 FROM (SELECT IF(COUNTIF(requested_total IS NULL)>0,NULL,COALESCE(SUM(requested_total),0)) requested,
                             IF(COUNTIF(fulfilled_total IS NULL)>0,NULL,COALESCE(SUM(fulfilled_total),0)) fulfilled
        FROM (SELECT order_id,ANY_VALUE(requested_total) requested_total,ANY_VALUE(fulfilled_total) fulfilled_total
         FROM {prefix}analytics_customer_orders_summary` o WHERE o.store_id=s.store_id AND o.policy_hash=s.policy_hash AND o.generation=s.generation AND influence_scope='LIFETIME' AND paid_media_influenced IS TRUE GROUP BY order_id)) v
       WHERE v.requested IS DISTINCT FROM s.requested_revenue_influenced OR v.fulfilled IS DISTINCT FROM s.fulfilled_revenue_influenced
        OR s.influence_complete AND SAFE_DIVIDE(v.requested,s.meta_spend) IS DISTINCT FROM s.roas_requested AND ABS(SAFE_DIVIDE(v.requested,s.meta_spend)-s.roas_requested)>0.000000001)
    """)
    return " UNION ALL ".join(pieces)


def validate(transport: Transport, policy: AnalyticsPolicy, *, tenant: str) -> dict[str, Any]:
    reader = BigQueryReadSession(
        transport.client, ReadBudget(transport.config.project, transport.config.location)
    )
    svc = IntelligenceDashboardService(
        transport.config.project,
        {policy.store_id: policy},
        lambda: reader,
        b"synthetic-internal-validation-key-32-bytes",
    )
    grant = Grant(tenant, policy.store_id, "B2B")
    principal = Principal("change16-validator", "ADMIN_UP", frozenset({grant}))
    overview = svc.overview(principal, grant)
    actual = overview["data"]
    if policy.store_id == "mx-fashion" and (
        actual["requested_revenue"] != "86319.62"
        or actual["fulfilled_revenue"] != "73220.13"
        or actual["orders_requested"] != 18
        or actual["buyers_observed"] != 16
    ):
        raise ValueError("analytics_v1_parity_failed")
    customers = svc.customers(
        principal, grant, size="100", from_day=policy.report_from, to_day=policy.report_to
    )
    if policy.store_id == "mx-fashion" and (
        len(customers["data"]) != 16 or customers["pagination"]["has_more"]
    ):
        raise ValueError("customer_period_parity_failed")
    svc._intelligence_scope(principal, grant)
    h = svc.intelligence_head
    rows, _ = transport.query(
        sql(transport.config.project),
        [
            scalar("store", "STRING", policy.store_id),
            scalar("policy", "STRING", policy.policy_hash),
            scalar("generation", "INT64", h["generation"]),
            scalar("account", "STRING", h["meta_account_id"]),
            scalar("configuration", "STRING", h["meta_configuration_hash"]),
            scalar("snapshot", "TIMESTAMP", h["source_snapshot_at"]),
            scalar("from", "DATE", policy.report_from),
            scalar("to", "DATE", policy.report_to),
        ],
    )
    if any(r["failures"] for r in rows):
        raise ValueError("intelligence_invariant_failed")
    return {"status": "completed", "generation": h["generation"], "invariants_checked": len(rows)}
