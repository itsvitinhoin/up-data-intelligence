import time
import uuid
from datetime import datetime
from itertools import chain
from pathlib import Path
from typing import Any

from src import __version__
from src.bigquery.repository import Repository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.domain.models import Batch, SafeError
from src.ingestion import metrics
from src.ingestion.checkpoints import (
    CHECKPOINT_COMPLETE,
    CHECKPOINT_EXTRACTED,
    CHECKPOINT_NEEDS_REVIEW,
    CHECKPOINT_RECOVERED,
    CHECKPOINT_RUNNING,
)
from src.normalization.entities import VERSION, normalize
from src.normalization.identity import identity_evidence
from src.observability.logging import event
from src.quality.rules import purchase_severity, result
from src.security.sanitization import POLICY_VERSION, sanitize
from src.utils.data import digest, now, timestamp

TABLE_FOR = {"customers": "customers", "orders": "orders", "analytics_facts": "analytics_events"}
KEY_FOR = {"customers": "customer_id", "orders": "order_id", "analytics_events": "fact_id"}


def row_key(store: str, *parts: Any) -> str:
    return digest([store, *parts])


class Engine:
    def __init__(self, settings: Settings, repository: Repository, connector: UpZeroConnector):
        self.cfg, self.repo, self.connector = settings, repository, connector
        import hashlib

        self.spec_hash = hashlib.sha256(Path("docs/upzero-openapi.json").read_bytes()).hexdigest()

    def registry(self) -> None:
        c, at = self.cfg, now()
        existing = self.repo.read("stores", c.store_id, [row_key(c.store_id, "store")])
        connections = self.repo.read("source_connections", c.store_id)
        if any(
            r["connection_id"] != c.connection_id and r["status"] == "active" for r in connections
        ):
            raise SafeError("multiple_active_upzero_connections_not_supported")
        created = existing[0]["created_at"] if existing else at
        self.repo.write(
            {
                "stores": [
                    {
                        "row_key": row_key(c.store_id, "store"),
                        "store_id": c.store_id,
                        "store_name": c.store_name,
                        "store_slug": c.store_slug,
                        "timezone": c.timezone,
                        "status": "active",
                        "upzero_store_identifier": c.upzero_store_identifier,
                        "meta_ad_account_id": None,
                        "created_at": created,
                        "updated_at": at,
                    }
                ],
                "source_connections": [
                    {
                        "row_key": row_key(c.store_id, c.connection_id),
                        "store_id": c.store_id,
                        "connection_id": c.connection_id,
                        "source_system": "upzero",
                        "secret_resource_name": c.secret_resource_name,
                        "status": "active",
                        "created_at": connections[0]["created_at"] if connections else at,
                        "updated_at": at,
                    }
                ],
                "source_capabilities": [
                    {
                        "row_key": row_key(c.store_id, c.connection_id),
                        "store_id": c.store_id,
                        "connection_id": c.connection_id,
                        "purchase_order_id_effective_at": c.purchase_order_id_effective_at,
                        "updated_at": at,
                    }
                ],
            }
        )

    def transform(self, raw: dict[str, Any]) -> Batch:
        store, run, resource = raw["store_id"], raw["run_id"], raw["resource"]
        batch = Batch()

        def quality(rule: str, severity: str, record: str = "") -> None:
            batch.add("quality_results", result(store, run, resource, rule, severity, record))

        if not store:
            quality("fact_without_technical_store", "alert")
            batch.failed = len(raw["payload"]["data"])
            return batch
        table = TABLE_FOR[resource]
        keyfield = KEY_FOR[table]
        source_rows = raw["payload"]["data"]
        keys = [row_key(store, str(s.get("id"))) for s in source_rows if isinstance(s, dict)]
        current = {r["row_key"]: r for r in self.repo.read(table, store, keys)}
        old_item_keys = (
            [
                row_key(store, r["order_id"], i)
                for r in current.values()
                for i in (r.get("item_ids") or [])
            ]
            if resource == "orders"
            else []
        )
        old_item_rows = self.repo.read("order_items", store, old_item_keys) if old_item_keys else []
        seen: set[str] = set()
        for index, source in enumerate(source_rows):
            try:
                if not isinstance(source, dict):
                    raise ValueError("invalid_record")
                _, entity, items = normalize(resource, source)
                key = row_key(store, entity[keyfield])
                if key in seen:
                    quality(
                        "duplicate_" + ("facts" if resource == "analytics_facts" else resource),
                        "warning",
                        key,
                    )
                old = current.get(key)
                payload_hash = digest(source)
                if key in seen and old and old["payload_hash"] != payload_hash:
                    quality("conflicting_duplicate_in_page", "alert", key)
                    batch.failed += 1
                    continue
                seen.add(key)
                if (
                    old
                    and old["payload_hash"] == payload_hash
                    and old.get("transform_version") == VERSION
                ):
                    continue
                if old and datetime.fromisoformat(
                    timestamp(old["observed_at"])
                ) > datetime.fromisoformat(timestamp(raw["ingested_at"])):
                    quality("stale_observation", "warning", key)
                    continue
                source_updated = entity.get("updated_at")
                if old and source_updated and old.get("source_updated_at"):
                    old_time = datetime.fromisoformat(timestamp(old["source_updated_at"]))
                    new_time = datetime.fromisoformat(timestamp(source_updated))
                    if new_time < old_time:
                        quality("stale_source_version", "warning", key)
                        continue
                    if new_time == old_time and old["payload_hash"] != payload_hash:
                        quality("conflicting_source_version", "alert", key)
                        batch.failed += 1
                        continue
                version = digest([key, raw["raw_record_id"], payload_hash, VERSION])
                meta = {
                    "store_id": store,
                    "source_system": "upzero",
                    "raw_record_id": raw["raw_record_id"],
                    "run_id": run,
                    "observed_at": raw["ingested_at"],
                    "source_updated_at": source_updated,
                    "payload_hash": payload_hash,
                    "version_id": version,
                    "transform_version": VERSION,
                }
                row = {**entity, **meta, "row_key": key}
                batch.add(table, row)
                batch.add(table + "_versions", {**row, "row_key": version})
                current[key] = row
                batch.updated += int(old is not None)
                batch.written += int(old is None)
                if resource == "orders":
                    if row.get("customer_id"):
                        batch.add(
                            "identity_links",
                            identity_evidence(
                                meta,
                                entity_type="order",
                                entity_id=row["order_id"],
                                left="order_id",
                                left_id=row["order_id"],
                                right="customer_id",
                                right_id=row["customer_id"],
                                evidence_type="observed_order_customer",
                                occurred_at=row["created_at"],
                            ),
                        )
                    if not row.get("customer_id"):
                        quality("order_without_customer", "warning", key)
                    if items is not None:
                        # Stable item identity includes parent order, never SKU or product alone.
                        old_items = [i for i in old_item_rows if i["order_id"] == row["order_id"]]
                        new_ids = {i["item_id"] for i in items}
                        row["item_ids"] = sorted(new_ids)
                        batch.rows[table + "_versions"][-1]["item_ids"] = sorted(new_ids)
                        item_seen: set[str] = set()
                        for item in items + [
                            {k: v for k, v in i.items() if k not in meta and k != "row_key"}
                            | {"present_in_latest_snapshot": False}
                            for i in old_items
                            if i["item_id"] not in new_ids
                        ]:
                            ik = row_key(store, row["order_id"], item["item_id"])
                            if ik in item_seen:
                                quality("duplicate_order_items", "alert", ik)
                            item_seen.add(ik)
                            iv = digest([version, ik])
                            child = {
                                **item,
                                **meta,
                                "row_key": ik,
                                "version_id": iv,
                                "parent_order_version_id": version,
                            }
                            batch.add("order_items", child)
                            batch.add("order_items_versions", {**child, "row_key": iv})
                    else:
                        row["item_ids"] = (old or {}).get("item_ids", [])
                        batch.rows[table + "_versions"][-1]["item_ids"] = row["item_ids"]
                if resource == "analytics_facts":
                    if row["parse_status"] in {
                        "invalid_url",
                        "invalid_id",
                        "placeholder",
                        "conflict",
                    }:
                        quality("invalid_meta_parser", "warning", key)
                    if row["event_name"] in {"purchase", "purchase_item"} and not row["order_id"]:
                        quality(
                            row["event_name"] + "_without_order_id",
                            purchase_severity(
                                row["occurred_at"], self.cfg.purchase_order_id_effective_at
                            ),
                            key,
                        )
                    # One factual touchpoint per event; no attribution weights or inferred identity.
                    batch.add(
                        "touchpoints",
                        {**row, "touchpoint_id": key, "source_fact_id": row["fact_id"]},
                    )
                    batch.add(
                        "event_order_links",
                        {
                            "row_key": key,
                            "store_id": store,
                            "fact_id": row["fact_id"],
                            "order_id": row["order_id"],
                            "source_version_id": version,
                            "link_status": "pending" if row["order_id"] else "missing_order_id",
                            "updated_at": now(),
                        },
                    )
                    for left, right in [
                        ("anonymous_id", "visitor_id"),
                        ("visitor_id", "session_id"),
                        ("session_id", "user_id"),
                    ]:
                        if row[left] and row[right]:
                            batch.add(
                                "identity_links",
                                identity_evidence(
                                    meta,
                                    entity_type="analytics_fact",
                                    entity_id=row["fact_id"],
                                    left=left,
                                    left_id=row[left],
                                    right=right,
                                    right_id=row[right],
                                    evidence_type="observed_cooccurrence",
                                    occurred_at=row["occurred_at"],
                                ),
                            )
                    if row["order_id"]:
                        batch.add(
                            "identity_links",
                            identity_evidence(
                                meta,
                                entity_type="analytics_fact",
                                entity_id=row["fact_id"],
                                left="fact_id",
                                left_id=row["fact_id"],
                                right="order_id",
                                right_id=row["order_id"],
                                evidence_type="observed_fact_order",
                                occurred_at=row["occurred_at"],
                            ),
                        )
            except (ValueError, TypeError, KeyError):
                quality(
                    "invalid_transformation_or_monetary_value",
                    "alert",
                    digest([raw["raw_record_id"], index]),
                )
                batch.failed += 1
        return batch

    def advance(
        self,
        resource: str,
        filters: dict[str, Any],
        *,
        mode: str = "backfill",
        page_budget: int = 20,
        soft_time_budget_seconds: float = 600,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if (
            type(page_budget) is not int
            or page_budget < 1
            or not 0 < soft_time_budget_seconds <= 600
        ):
            raise SafeError("invalid_slice_budget")
        result = self.run(
            resource,
            filters,
            mode=mode,
            refresh=refresh,
            _page_budget=min(page_budget, self.connector.max_pages),
            _soft_time_budget_seconds=soft_time_budget_seconds,
        )
        return {
            **result,
            "complete": result.get("complete", result["status"] == "completed"),
            "yielded": result.get("yielded", False),
        }

    def run(
        self,
        resource: str,
        filters: dict[str, Any],
        *,
        mode: str = "backfill",
        refresh: bool = False,
        stop_at_id: int | None = None,
        _page_budget: int | None = None,
        _soft_time_budget_seconds: float | None = None,
    ) -> dict[str, Any]:
        if resource not in TABLE_FOR:
            raise SafeError("unsupported_resource")
        if self.cfg.page_limit is not None:
            filters = {
                **filters,
                "limit": min(self.cfg.page_limit, 1000 if resource == "analytics_facts" else 200),
            }
        store, at = self.cfg.store_id, now()
        if not store:
            raise SafeError("technical_store_required")
        plan = digest([store, self.cfg.connection_id, resource, filters, mode])
        saved = self.repo.read("sync_checkpoints", store, [plan])
        cp = saved[0] if saved and not refresh else {}
        if cp.get("status") == CHECKPOINT_COMPLETE:
            return self.repo.read("sync_runs", store, [cp["run_id"]])[0]
        resume_extracted = cp.get("status") == CHECKPOINT_EXTRACTED
        if cp.get("status") == CHECKPOINT_RECOVERED:
            raise SafeError("run_recovered_use_refresh")
        if cp.get("status") == CHECKPOINT_NEEDS_REVIEW:
            raise SafeError("run_needs_review_use_replay_or_refresh")
        slice_started = time.monotonic()
        slice_pages = 0
        retry_baseline = self.connector.retries
        run_id = cp.get("run_id") or str(uuid.uuid4())
        oldrun = self.repo.read("sync_runs", store, [run_id])
        run: dict[str, Any] = (
            oldrun[0]
            if oldrun
            else {
                **metrics.empty(),
                "row_key": run_id,
                "store_id": store,
                "run_id": run_id,
                "source": "upzero",
                "resource": resource,
                "started_at": at,
                "finished_at": None,
                "records_read": 0,
                "records_written": 0,
                "records_updated": 0,
                "records_failed": 0,
                "pages": 0,
                "retries": 0,
                "bytes": 0,
                "status": "running",
                "error_summary": None,
                "plan_key": plan,
                "mode": mode,
            }
        )
        if run.get("metrics_version") != metrics.VERSION:
            metrics.upgrade(
                run, self.repo.iter_find("upzero_" + resource, store, "run_id", [run_id])
            )
        run.update(status="running", error_summary=None, finished_at=None)
        cp = {
            "row_key": plan,
            "store_id": store,
            "resource": resource,
            "connection_id": self.cfg.connection_id,
            "plan_key": plan,
            "run_id": run_id,
            "status": CHECKPOINT_RUNNING,
            "pending_raw_id": cp.get("pending_raw_id"),
            "mode": mode,
            "filters": filters,
            "position": cp.get("position") or {},
            "updated_at": at,
            "completed_to": None,
            "high_id": cp.get("high_id"),
        }
        self.repo.write({"sync_runs": [run], "sync_checkpoints": [cp]})
        event("sync_started", run_id=run_id, store_id=store, resource=resource)

        def promote(raw: dict[str, Any]) -> bool:
            nonlocal slice_pages
            if raw.get("pagination_error"):
                self.repo.write(
                    {
                        "quality_results": [
                            result(store, run_id, resource, raw["pagination_error"], "alert")
                        ]
                    }
                )
                raise SafeError(raw["pagination_error"])
            batch = self.transform(raw)
            metrics.promoted(run, raw, batch)
            ids = [int(s["id"]) for s in raw["payload"]["data"]] if resource == "customers" else []
            if ids:
                cp["high_id"] = str(max(ids + [int(cp["high_id"] or 0)]))
            done = raw["next_position"] is None or (
                bool(ids) and stop_at_id is not None and min(ids) <= stop_at_id
            )
            cp.update(
                pending_raw_id=None,
                position=raw["next_position"] or {},
                updated_at=now(),
                status=CHECKPOINT_EXTRACTED if done else CHECKPOINT_RUNNING,
            )
            batch.add("sync_runs", run)
            batch.add("sync_checkpoints", cp)
            event(
                "page_persistence",
                phase="core_promotion",
                run_id=run_id,
                resource=resource,
                raw_record_id=raw["raw_record_id"],
                records=len(raw["payload"]["data"]),
                payload_bytes=raw["bytes_read"],
            )
            self.repo.write(batch.rows)
            slice_pages += 1
            return done

        def should_yield() -> bool:
            return (
                _page_budget is not None
                and slice_pages > 0
                and (
                    slice_pages >= _page_budget
                    or (
                        _soft_time_budget_seconds is not None
                        and time.monotonic() - slice_started >= _soft_time_budget_seconds
                    )
                )
            )

        def yielded() -> dict[str, Any]:
            run.update(
                status="running",
                finished_at=None,
                retries=run["retries"] + self.connector.retries - retry_baseline,
            )
            cp.update(status=CHECKPOINT_RUNNING, updated_at=now())
            self.repo.write({"sync_runs": [run], "sync_checkpoints": [cp]})
            return {**run, "complete": False, "yielded": True}

        try:
            done = resume_extracted
            if cp["pending_raw_id"]:
                pending = self.repo.read("upzero_" + resource, store, [cp["pending_raw_id"]])
                if not pending:
                    raise SafeError("pending_raw_not_found")
                done = promote(pending[0])
            if not done and should_yield():
                return yielded()
            if not done:
                for page in self.connector.pages(resource, filters, cp["position"]):
                    raw_id = page.request_id
                    raw = {
                        "row_key": raw_id,
                        "raw_record_id": raw_id,
                        "store_id": store,
                        "source_system": "upzero",
                        "resource": resource,
                        "source_connection_id": self.cfg.connection_id,
                        "run_id": run_id,
                        "request_id": page.request_id,
                        "ingested_at": now(),
                        "position": sanitize(page.position),
                        "next_position": sanitize(page.next_position),
                        "request_filters": sanitize(filters),
                        "payload": sanitize(page.payload),
                        "payload_hash": digest(sanitize(page.payload)),
                        "connector_version": __version__,
                        "spec_version": "1.0.0",
                        "spec_sha256": self.spec_hash,
                        "sanitization_version": POLICY_VERSION,
                        "bytes_read": page.bytes_read,
                        "pagination_error": page.pagination_error,
                    }
                    cp.update(pending_raw_id=raw_id, updated_at=now())
                    event(
                        "page_persistence",
                        phase="raw_capture",
                        run_id=run_id,
                        resource=resource,
                        raw_record_id=raw_id,
                        records=len(page.payload["data"]),
                        payload_bytes=page.bytes_read,
                    )
                    metrics.captured(run, raw)
                    self.repo.write(
                        {"upzero_" + resource: [raw], "sync_checkpoints": [cp], "sync_runs": [run]}
                    )
                    done = promote(raw)
                    if done:
                        break
                    if should_yield():
                        return yielded()
            run.update(
                status="completed_with_errors" if run["records_failed"] else "completed",
                finished_at=now(),
                retries=run["retries"] + self.connector.retries - retry_baseline,
            )
            cp.update(
                status=CHECKPOINT_COMPLETE
                if not run["records_failed"]
                else CHECKPOINT_NEEDS_REVIEW,
                completed_to=filters.get("to")
                or (
                    str(filters["end_date"]) + "T00:00:00+00:00"
                    if filters.get("end_date")
                    else now()
                ),
                updated_at=now(),
            )
            self.repo.write({"sync_runs": [run], "sync_checkpoints": [cp]})
            return run
        except Exception as exc:
            code = exc.code if isinstance(exc, SafeError) else "internal_failure"
            if code == "bigquery_write_outcome_unknown":
                raise SafeError(code) from None
            persisted = self.repo.read("sync_runs", store, [run_id])
            if persisted:
                run = persisted[0]
            run.update(
                status="failed",
                finished_at=now(),
                error_summary=code,
                retries=run["retries"] + self.connector.retries - retry_baseline,
            )
            self.repo.write(
                {
                    "sync_runs": [run],
                    "quality_results": [result(store, run_id, resource, code, "alert")],
                }
            )
            raise SafeError(code) from None

    def replay(self, resource: str, original_run_id: str) -> dict[str, Any]:
        store, run_id = self.cfg.store_id, str(uuid.uuid4())
        raws = self.repo.iter_find("upzero_" + resource, store, "run_id", [original_run_id])
        first = next(raws, None)
        if first is None:
            raise SafeError("replay_run_not_found")
        report: dict[str, Any] = {
            **metrics.empty(),
            "row_key": run_id,
            "store_id": store,
            "run_id": run_id,
            "source": "upzero",
            "resource": resource,
            "started_at": now(),
            "finished_at": None,
            "records_read": 0,
            "records_written": 0,
            "records_updated": 0,
            "records_failed": 0,
            "pages": 0,
            "retries": 0,
            "bytes": 0,
            "status": "running",
            "error_summary": None,
            "plan_key": original_run_id,
            "mode": "replay",
        }
        self.repo.write({"sync_runs": [report]})
        try:
            for raw in chain([first], raws):
                batch = self.transform({**raw, "run_id": run_id})
                metrics.promoted(report, raw, batch)
                batch.add("sync_runs", report)
                self.repo.write(batch.rows)
            report.update(
                status="completed_with_errors" if report["records_failed"] else "completed",
                finished_at=now(),
            )
            self.repo.write({"sync_runs": [report]})
            return report
        except Exception as exc:
            code = exc.code if isinstance(exc, SafeError) else "internal_failure"
            if code == "bigquery_write_outcome_unknown":
                raise SafeError(code) from None
            persisted = self.repo.read("sync_runs", store, [run_id])
            if persisted:
                report = persisted[0]
            report.update(status="failed", finished_at=now(), error_summary=code)
            self.repo.write({"sync_runs": [report]})
            raise SafeError(code) from None
