"""Injected, bounded DEV materialization runtime; no credential discovery on import."""

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from src.analytics.cloud.transport import Transport, scalar
from src.analytics.config import AnalyticsPolicy
from src.bigquery.catalog import TABLES
from src.connectors.meta.config import Account, Insights
from src.dashboard.contracts import Grant, Principal
from src.dashboard.repository import BigQueryReadSession, ReadBudget
from src.dashboard.service import DashboardService
from src.influence.identity import IdentityContext
from src.intelligence.live.events import EventReader
from src.intelligence.live.evidence import EvidenceReader
from src.intelligence.live.materialize import build_stream
from src.intelligence.live.publication import Writer
from src.intelligence.live.schema import PUBLICATION
from src.intelligence.live.spool import DiskAnchors, DiskEvidenceIndex, Spool
from src.performance.engine import MediaCoverage
from src.utils.data import digest, timestamp


def primitive(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [primitive(v) for v in value]
    return value


def foundation_row(resource: str, row: dict[str, Any]) -> dict[str, Any]:
    """Decode declared BigQuery JSON only; keep source strings and decimals intact."""
    fields = TABLES[f"meta_live_{resource}"].fields
    result = primitive(row)
    for key, typ in fields.items():
        if typ == "JSON" and isinstance(result.get(key), str):
            result[key] = json.loads(result[key])
    return {
        k: v for k, v in result.items() if k not in {"version_id", "payload_hash", "source_system"}
    }


def binding(transport: Transport, store: str, account_id: str) -> Account:
    rows, _ = transport.query(
        f"SELECT * FROM `{transport.config.project}.up_core.meta_account_bindings` WHERE store_id=@store OR account_id=@account",
        [scalar("store", "STRING", store), scalar("account", "STRING", account_id)],
    )
    if len(rows) != 1 or rows[0]["store_id"] != store or rows[0]["account_id"] != account_id:
        raise ValueError("META_ACCOUNT_BINDING_REQUIRED")
    r = rows[0]
    return Account(
        store, account_id, r["connection_id"], r["api_version"], r["source_timezone"], r["currency"]
    )


def reporting(account: Account, policy: AnalyticsPolicy) -> Insights:
    return Insights(
        policy.report_from,
        (date.fromisoformat(policy.report_to) - timedelta(days=1)).isoformat(),
        "impression",
        ("7d_click",),
        None,
    )


def configuration_hash(account: Account, insights: Insights) -> str:
    return digest(
        {
            "api_version": account.api_version,
            "currency": account.currency,
            "timezone": account.timezone,
            **insights.definition(),
            "level": "campaign",
        }
    )


def materialize(
    transport: Transport,
    policy: AnalyticsPolicy,
    account: Account,
    *,
    tenant: str,
    snapshot_at: str,
    calculated_at: str,
    initialize_head: bool = False,
) -> dict[str, Any]:
    if (
        account.store_id != policy.store_id
        or account.currency != policy.currency
        or account.timezone != policy.reporting_timezone
    ):
        raise ValueError("incompatible_meta_binding")
    snapshot_at = timestamp(snapshot_at)
    calculated_at = timestamp(calculated_at)
    grant = Grant(tenant, policy.store_id, "B2B")
    base_reader = BigQueryReadSession(
        transport.client, ReadBudget(transport.config.project, transport.config.location)
    )
    svc = DashboardService(
        transport.config.project,
        {policy.store_id: policy},
        lambda: base_reader,
        b"internal-runtime-no-cursor-exposed-key",
    )
    svc._scope(Principal("intelligence-runtime", "ADMIN_UP", frozenset({grant})), grant)
    transport.reserved_query_bytes += base_reader.reserved_bytes
    transport.query_count += len(getattr(svc.reader, "calls", [])) or 1
    base = asdict(svc.publication)
    params = [
        scalar("store", "STRING", policy.store_id),
        scalar("snapshot_at", "TIMESTAMP", snapshot_at),
        scalar("as_of", "TIMESTAMP", policy.as_of),
        scalar("history_from", "TIMESTAMP", policy.history_from),
    ]
    specs = {
        "customers": "store_id source_system customer_id customer_type company_name trade_name state city version_id observed_at".split(),
        "orders": "store_id source_system order_id customer_id created_at order_status requested_total fulfilled_total requested_items_qty fulfilled_items_qty version_id observed_at".split(),
        "order_items": "store_id source_system order_id item_id order_created_at variant_id sku asset_id qty original_qty unit_price status present_in_latest_snapshot parent_order_version_id observed_at".split(),
    }
    snapshot = {}
    source_rows = 0
    source_bytes = 0
    for name, fields in specs.items():
        if not set(fields) <= TABLES[name].fields.keys():
            raise ValueError("intelligence_source_schema_drift")
        conditions = " AND source_system='upzero'"
        stamp = {
            "orders": "created_at",
            "order_items": "order_created_at",
            "analytics_events": "occurred_at",
        }.get(name)
        if stamp:
            conditions += f" AND {stamp}>=@history_from AND {stamp}<@as_of"
        rows, _ = transport.query(
            f"SELECT {','.join('`' + k + '`' for k in fields)} FROM `{transport.config.project}.up_core.{name}` FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store"
            + conditions,
            params,
        )
        source_rows += len(rows)
        source_bytes += len(json.dumps(rows, default=str, separators=(",", ":")).encode())
        if (
            source_rows > transport.config.maximum_rows
            or source_bytes > transport.config.maximum_payload_bytes
        ):
            raise ValueError("bounded_intelligence_snapshot_required")
        snapshot[{"order_items": "items", "analytics_events": "events"}.get(name, name)] = (
            primitive(rows)
        )
    report = reporting(account, policy)
    config = configuration_hash(account, report)
    meta = {}
    account_param = [scalar("account", "STRING", account.account_id)]
    for resource in ("campaigns", "insights_daily"):
        rows, _ = transport.query(
            f"SELECT * FROM `{transport.config.project}.up_core.meta_live_{resource}` FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND account_id=@account"
            + (
                " AND configuration_hash=@configuration AND date_start>=DATE(@history_from) AND date_start<DATE(@as_of)"
                if resource == "insights_daily"
                else ""
            ),
            params + account_param + [scalar("configuration", "STRING", config)],
        )
        meta[resource] = [foundation_row(resource, r) for r in rows]
    report = reporting(account, policy)
    config = configuration_hash(account, report)
    checkpoints, _ = transport.query(
        f"SELECT filters,run_id,status,pending_raw_id FROM `{transport.config.project}.up_ops.sync_checkpoints` FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND resource='meta_live_insights_daily' AND status='complete' AND pending_raw_id IS NULL",
        params,
    )
    for r in checkpoints:
        if isinstance(r.get("filters"), str):
            r["filters"] = json.loads(r["filters"])
    compatible = [
        r
        for r in primitive(checkpoints)
        if r["filters"]
        == {"account": account.snapshot(), "insights": {**report.snapshot(), "level": "campaign"}}
    ]
    if len(compatible) != 1:
        raise ValueError("meta_complete_checkpoint_required")
    runs, _ = transport.query(
        f"SELECT status,core_records_failed FROM `{transport.config.project}.up_ops.sync_runs` FOR SYSTEM_TIME AS OF @snapshot_at WHERE store_id=@store AND run_id=@run",
        params + [scalar("run", "STRING", compatible[0]["run_id"])],
    )
    if len(runs) != 1 or runs[0]["status"] != "completed" or runs[0]["core_records_failed"] != 0:
        raise ValueError("meta_sync_incomplete")
    publication = f"`{transport.config.project}.up_analytics.{PUBLICATION}`"
    keys = [
        scalar("store", "STRING", policy.store_id),
        scalar("policy", "STRING", policy.policy_hash),
    ]
    heads, _ = transport.query(
        f"SELECT generation,(SELECT COALESCE(MAX(generation),0) FROM {publication} WHERE store_id=@store AND policy_hash=@policy AND record_kind='RECEIPT') maximum_generation FROM {publication} WHERE record_kind='HEAD' AND store_id=@store AND policy_hash=@policy",
        keys,
    )
    if not heads:
        if not initialize_head:
            raise ValueError("intelligence_head_initialization_required")
        # Initialization joins the final atomic transaction; failures leave HEAD untouched.
        heads = [{"generation": 0, "maximum_generation": 0}]
    if len(heads) != 1 or type(heads[0]["generation"]) is not int:
        raise ValueError("invalid_intelligence_head")
    expected = heads[0]["generation"]
    coverage = MediaCoverage(
        policy.store_id,
        account.account_id,
        policy.report_from,
        policy.report_to,
        config,
        True,
        digest(compatible),
    )
    with Spool() as spool:
        evidence = DiskEvidenceIndex(
            spool,
            store_id=policy.store_id,
            history_from=policy.history_from,
            as_of=policy.as_of,
            calculated_at=calculated_at,
        )
        for chunk in EvidenceReader(transport, policy, snapshot_at).chunks():
            for link in chunk:
                evidence.add(link)
            spool.db.commit()
        evidence.seal()
        reader = EventReader(transport, policy, snapshot_at)
        context = IdentityContext.build(
            snapshot["customers"],
            snapshot["orders"],
            evidence,
            (fact for chunk in reader.chunks(anchors=True) for fact in chunk),
            index=DiskAnchors(spool),
        )
        artifact = build_stream(
            policy,
            snapshot,
            events=reader.chunks(),
            context=context,
            spool=spool,
            account=account,
            meta_insights=meta["insights_daily"],
            meta_campaigns=meta["campaigns"],
            coverage=coverage,
            calculated_at=calculated_at,
            source_snapshot_at=snapshot_at,
            base_publication=base,
            generation=max(expected, heads[0]["maximum_generation"]) + 1,
        )
        return Writer(transport).publish(artifact, expected, initialize_head=initialize_head)
