import argparse
import json
import os
import sys
import uuid
from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Any

from src.bigquery.repository import BigQueryRepository, Repository, SQLiteRepository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.connectors.upzero.fixtures import transport
from src.domain.models import SafeError
from src.ingestion.engine import Engine
from src.ingestion.planning import incremental, open_order_windows, windows
from src.observability.logging import configure, event, execution_id
from src.quality.gate import evaluate
from src.quality.service import reconcile
from src.security.lease import cloud_lease, local_lease
from src.security.secrets import resolve_secret
from src.utils.data import now


def main(default_mode: str = "sync") -> int:
    parser = argparse.ArgumentParser(
        description="UP Data Foundation. Synthetic/offline by default."
    )
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument(
        "--resource", choices=["customers", "orders", "analytics_facts", "all"], default="all"
    )
    parser.add_argument(
        "--mode",
        choices=["sync", "backfill", "reconcile", "quality", "replay"],
        default=default_mode,
    )
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    parser.add_argument("--replay-run")
    parser.add_argument(
        "--page-limit",
        type=int,
        help="API page size (1..1000 for facts, capped at 200 for commerce).",
    )
    parser.add_argument("--fixture", default="tests/fixtures/pilot.json")
    parser.add_argument("--live", action="store_true", help="Explicitly allow UP Zero/GCP access.")
    parser.add_argument("--confirm-store", help="Must equal configured store_id for live mode.")
    parser.add_argument(
        "--refresh", action="store_true", help="Re-fetch completed windows; preserves versions."
    )
    args = parser.parse_args()
    configure()
    context_token = execution_id.set(str(uuid.uuid4()))
    summaries: list[dict[str, Any]] = []
    ingestion_status = "failed"
    client: UpZeroConnector | None = None
    repo: Repository | None = None
    try:
        cfg = (
            Settings(**json.loads(os.environ["UP_CONFIG_JSON"]))
            if "UP_CONFIG_JSON" in os.environ
            else Settings.load(args.config)
        )
        if args.page_limit is not None:
            cfg = replace(cfg, page_limit=args.page_limit)
        lease: AbstractContextManager[None]
        if args.live:
            if args.confirm_store != cfg.store_id or not all(
                (cfg.project_id, cfg.location, cfg.lease_bucket, cfg.secret_resource_name)
            ):
                raise SafeError("live_configuration_and_store_confirmation_required")
            repo = BigQueryRepository(cfg.project_id, cfg.location)
            lease = cloud_lease(cfg.lease_bucket, cfg.store_id)
        else:
            repo = SQLiteRepository(cfg.state_path)
            lease = local_lease(cfg.state_path + ".lock")
        with lease:
            # No credential resolution is needed to replay or check persisted records.
            needs_api = args.mode not in {"quality", "replay"}
            secret = (
                resolve_secret(cfg.secret_resource_name)
                if args.live and needs_api
                else "SYNTHETIC_TEST_KEY"
            )
            client = UpZeroConnector(
                secret, None if args.live else transport(args.fixture), max_pages=cfg.max_pages
            )
            engine = Engine(cfg, repo, client)
            engine.registry()
            event("execution_started", store_id=cfg.store_id, resource=args.resource)
            if args.mode == "quality":
                checks = reconcile(repo, cfg, str(uuid.uuid4()))
                decision = evaluate(args.resource, [], checks, [], quality_only=True)
                event(
                    "execution_finished", store_id=cfg.store_id, resource=args.resource, **decision
                )
                return int(decision["exit_code"])
            resources = (
                ["customers", "orders", "analytics_facts"]
                if args.resource == "all"
                else [args.resource]
            )
            at = args.end or now()

            def record(summary: dict[str, Any]) -> None:
                summaries.append(summary)
                event(
                    "sync_finished",
                    run_id=summary["run_id"],
                    store_id=cfg.store_id,
                    resource=summary["resource"],
                    status=summary["status"],
                    **{
                        k: summary.get(k)
                        for k in (
                            "source_records_read",
                            "raw_pages_written",
                            "core_records_processed",
                            "core_records_inserted",
                            "core_records_updated",
                            "core_records_failed",
                            "metrics_version",
                        )
                    },
                )

            for resource in resources:
                if args.mode == "replay":
                    if not args.replay_run:
                        raise SafeError("replay_run_required")
                    record(engine.replay(resource, args.replay_run))
                elif args.mode == "sync":
                    pending = [
                        c
                        for c in repo.read("sync_checkpoints", cfg.store_id)
                        if c["resource"] == resource
                        and c["mode"] == "incremental"
                        and c["status"] in {"running", "extracted"}
                    ]
                    if pending:
                        plan = min(pending, key=lambda c: c["updated_at"])
                        record(engine.run(resource, plan["filters"], mode="incremental"))
                    filters, stop = incremental(repo, cfg, resource, at)
                    record(
                        engine.run(
                            resource, filters, mode="incremental", refresh=True, stop_at_id=stop
                        )
                    )
                    if resource == "orders":
                        for filters in open_order_windows(repo, cfg):
                            record(engine.run(resource, filters, mode="open_orders", refresh=True))
                else:
                    start = args.start or cfg.initial_from
                    if resource == "customers" and args.mode == "reconcile":
                        record(engine.run(resource, {}, mode="reconcile", refresh=True))
                    else:
                        for filters in windows(resource, start, at, cfg.timezone):
                            record(
                                engine.run(
                                    resource,
                                    filters,
                                    mode=args.mode,
                                    refresh=args.refresh or args.mode == "reconcile",
                                )
                            )
            ingestion_status = (
                "completed"
                if summaries and all(s["status"] == "completed" for s in summaries)
                else "failed"
            )
            checks = reconcile(repo, cfg, str(uuid.uuid4()))
            unique = {s["run_id"]: s for s in summaries}
            child_checks = (
                repo.find("quality_results", cfg.store_id, "run_id", list(unique)) if unique else []
            )
            decision = evaluate(args.resource, summaries, checks, child_checks)
            event(
                "execution_finished",
                store_id=cfg.store_id,
                resource=args.resource,
                child_runs=len(unique),
                metrics_scope="cumulative_unique_child_runs",
                **{
                    k: sum(s.get(k, 0) or 0 for s in unique.values())
                    for k in (
                        "source_records_read",
                        "raw_pages_written",
                        "core_records_processed",
                        "core_records_inserted",
                        "core_records_updated",
                        "core_records_failed",
                    )
                },
                **decision,
            )
            return int(decision["exit_code"])
    except Exception as exc:
        event(
            "job_failed",
            code=exc.code if isinstance(exc, SafeError) else "configuration_or_internal_failure",
        )
        event(
            "execution_finished",
            resource=args.resource,
            ingestion_status=ingestion_status,
            resource_quality_status="unknown",
            global_quality_status="unknown",
            exit_code=1,
            child_runs=len({s["run_id"] for s in summaries}),
        )
        return 1
    finally:
        execution_id.reset(context_token)
        if client:
            client.close()
        if isinstance(repo, SQLiteRepository):
            repo.close()


if __name__ == "__main__":
    sys.exit(main())
