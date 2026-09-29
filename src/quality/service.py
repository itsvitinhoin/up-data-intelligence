from collections import Counter
from pathlib import Path
from typing import Any

from src.bigquery.repository import BigQueryRepository, Repository
from src.config.settings import Settings
from src.observability.logging import event
from src.quality.gate import rule_resource
from src.quality.rules import purchase_severity, result, stale
from src.utils.data import now


def reconcile(repo: Repository, cfg: Settings, run_id: str) -> list[dict[str, Any]]:
    store, at = cfg.store_id, now()
    checks: list[dict[str, Any]] = []
    if isinstance(repo, BigQueryRepository):
        from google.cloud import bigquery

        from src.domain.models import SafeError

        sql = Path("sql/quality/reconcile.sql").read_text().replace("${project_id}", repo.project)
        try:
            query_rows = repo.client.query(
                sql,
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("store", "STRING", store),
                        bigquery.ScalarQueryParameter(
                            "effective", "TIMESTAMP", cfg.purchase_order_id_effective_at
                        ),
                    ]
                ),
            ).result()
            for row in query_rows:
                checks.append(
                    result(
                        store,
                        run_id,
                        rule_resource(row.rule_id, "all"),
                        row.rule_id,
                        "warning"
                        if row.rule_id
                        in {"order_id_without_order", "invalid_meta_parser", "duplicate_event_ids"}
                        or row.rule_id.endswith("before_effective")
                        else "alert",
                        failed=row.failed_count,
                        checked=row.checked_count,
                    )
                )
        except Exception:
            raise SafeError("quality_query_failed") from None
    else:
        orders = {r["order_id"] for r in repo.read("orders", store)}
        links = repo.read("event_order_links", store)
        for link in links:
            link["link_status"] = (
                "missing_order_id"
                if not link["order_id"]
                else ("matched" if link["order_id"] in orders else "pending")
            )
            link["updated_at"] = at
        repo.write({"event_order_links": links})
        checks.append(
            result(
                store,
                run_id,
                "analytics_facts",
                "order_id_without_order",
                "warning",
                failed=sum(r["link_status"] == "pending" for r in links),
                checked=sum(bool(r["order_id"]) for r in links),
            )
        )
        for table, name in [
            ("analytics_events", "facts"),
            ("orders", "orders"),
            ("customers", "customers"),
        ]:
            rows = repo.read(table, store)
            key = {"analytics_events": "fact_id", "orders": "order_id", "customers": "customer_id"}[
                table
            ]
            counts = Counter(r[key] for r in rows)
            checks.append(
                result(
                    store,
                    run_id,
                    rule_resource("duplicate_" + name, table),
                    "duplicate_" + name,
                    "alert",
                    failed=sum(n - 1 for n in counts.values()),
                    checked=len(rows),
                )
            )
        events = repo.read("analytics_events", store)
        for event_name in ("purchase", "purchase_item"):
            for severity, suffix in (("warning", "before_effective"), ("alert", "after_effective")):
                candidates = [
                    e
                    for e in events
                    if e["event_name"] == event_name
                    and purchase_severity(e["occurred_at"], cfg.purchase_order_id_effective_at)
                    == severity
                ]
                checks.append(
                    result(
                        store,
                        run_id,
                        "analytics_facts",
                        event_name + "_without_order_id_" + suffix,
                        severity,
                        failed=sum(e["order_id"] is None for e in candidates),
                        checked=len(candidates),
                    )
                )
        checks.append(
            result(
                store,
                run_id,
                "analytics_facts",
                "invalid_meta_parser",
                "warning",
                failed=sum(
                    e["parse_status"] in {"invalid_url", "invalid_id", "placeholder", "conflict"}
                    for e in events
                ),
                checked=len(events),
            )
        )
        counts = Counter(e["event_id"] for e in events)
        checks.append(
            result(
                store,
                run_id,
                "analytics_facts",
                "duplicate_event_ids",
                "warning",
                failed=sum(n - 1 for n in counts.values()),
                checked=len(events),
            )
        )
    store_runs = repo.read("sync_runs", store)
    for resource in ("customers", "orders", "analytics_facts"):
        runs = [
            r
            for r in store_runs
            if r["resource"] == resource and r["status"] == "completed" and r["mode"] != "replay"
        ]
        latest = max((r["finished_at"] for r in runs), default=None)
        checks.append(
            result(
                store,
                run_id,
                resource,
                "sync_delayed",
                "alert",
                failed=int(stale(latest, at, cfg.stale_after_minutes)),
            )
        )
    repo.write({"quality_results": checks})
    for check in checks:
        if check["failed_count"]:
            event(
                "data_quality",
                store_id=store,
                run_id=run_id,
                resource=check["resource"],
                rule_id=check["rule_id"],
                severity=check["severity"],
                failed_count=check["failed_count"],
                checked_count=check["checked_count"],
            )
    return checks
