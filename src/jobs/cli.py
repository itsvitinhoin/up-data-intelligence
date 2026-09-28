import argparse
import json
import os
import sys
import uuid
from contextlib import AbstractContextManager
from typing import Any

from src.bigquery.repository import BigQueryRepository, Repository, SQLiteRepository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.connectors.upzero.fixtures import transport
from src.domain.models import SafeError
from src.ingestion.engine import Engine
from src.ingestion.planning import incremental, open_order_windows, windows
from src.observability.logging import configure, event
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
    parser.add_argument("--fixture", default="tests/fixtures/pilot.json")
    parser.add_argument("--live", action="store_true", help="Explicitly allow UP Zero/GCP access.")
    parser.add_argument("--confirm-store", help="Must equal configured store_id for live mode.")
    parser.add_argument(
        "--refresh", action="store_true", help="Re-fetch completed windows; preserves versions."
    )
    args = parser.parse_args()
    configure()
    client: UpZeroConnector | None = None
    repo: Repository | None = None
    try:
        cfg = (
            Settings(**json.loads(os.environ["UP_CONFIG_JSON"]))
            if "UP_CONFIG_JSON" in os.environ
            else Settings.load(args.config)
        )
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
            if args.mode == "quality":
                reconcile(repo, cfg, str(uuid.uuid4()))
                return 0
            resources = (
                ["customers", "orders", "analytics_facts"]
                if args.resource == "all"
                else [args.resource]
            )
            at = args.end or now()
            summaries: list[dict[str, Any]] = []
            for resource in resources:
                if args.mode == "replay":
                    if not args.replay_run:
                        raise SafeError("replay_run_required")
                    summaries.append(engine.replay(resource, args.replay_run))
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
                        summaries.append(engine.run(resource, plan["filters"], mode="incremental"))
                    filters, stop = incremental(repo, cfg, resource, at)
                    summaries.append(
                        engine.run(
                            resource, filters, mode="incremental", refresh=True, stop_at_id=stop
                        )
                    )
                    if resource == "orders":
                        for filters in open_order_windows(repo, cfg):
                            summaries.append(
                                engine.run(resource, filters, mode="open_orders", refresh=True)
                            )
                else:
                    start = args.start or cfg.initial_from
                    if resource == "customers" and args.mode == "reconcile":
                        summaries.append(engine.run(resource, {}, mode="reconcile", refresh=True))
                    else:
                        for filters in windows(resource, start, at, cfg.timezone):
                            summaries.append(
                                engine.run(
                                    resource,
                                    filters,
                                    mode=args.mode,
                                    refresh=args.refresh or args.mode == "reconcile",
                                )
                            )
            reconcile(repo, cfg, str(uuid.uuid4()))
            for summary in summaries:
                event(
                    "sync_finished",
                    run_id=summary["run_id"],
                    store_id=cfg.store_id,
                    resource=summary["resource"],
                    status=summary["status"],
                    records=summary["records_read"],
                    pages=summary["pages"],
                )
            return int(any(s["status"] != "completed" for s in summaries))
    except Exception as exc:
        event(
            "job_failed",
            code=exc.code if isinstance(exc, SafeError) else "configuration_or_internal_failure",
        )
        return 1
    finally:
        if client:
            client.close()
        if isinstance(repo, SQLiteRepository):
            repo.close()


if __name__ == "__main__":
    sys.exit(main())
