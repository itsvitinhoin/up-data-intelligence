"""Offline inspection by default; every SDK/ADC/network path requires explicit DEV gates."""

import argparse
import json
import os
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from src.control_plane.model import StoreConfig, instant
from src.domain.models import SafeError
from src.installation.model import Limits, Row, require_creatable_plan
from src.installation.planner import Planner
from src.installation.progress import summarize
from src.utils.data import now


def inspection(
    payload: Row, target: str, *, adopt: bool = False, limits: Limits | None = None
) -> Row:
    _, plan, units = Planner(limits or Limits()).calculate(
        StoreConfig.from_row(payload["registry"]),
        target,
        payload.get("now", now()),
        operation=payload.get("onboarding"),
        adopt=adopt,
        checkpoints=payload.get("checkpoints", []),
        runs=payload.get("runs", []),
        certified_publication=payload.get("certified_publication"),
    )
    return {
        "plan": plan,
        "existing_coverage": plan["adopted_coverage"],
        "pending_legacy_units": [r for r in units if r["unit_kind"] == "LEGACY_RESUME"],
        "skipped_completed_windows": {
            resource: plan["adopted_coverage"].get(resource, [])
            for resource in ("orders", "analytics_facts")
        },
        "new_planned_units": units,
        "publication_milestones": [
            r["filters"] for r in units if r["unit_kind"] == "PUBLISH_ANALYTICS"
        ],
        **summarize(units),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Installation V2: explicit plan, one work unit, or bounded dispatch"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan-only", "create-plan", "dispatch", "worker"):
        mode.add_argument("--" + name, action="store_true")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--adopt", action="store_true")
    parser.add_argument("--target-as-of")
    parser.add_argument("--store-id")
    parser.add_argument("--all-stores", action="store_true")
    parser.add_argument("--auto-activate", action="store_true")
    parser.add_argument("--confirm-store")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--project")
    parser.add_argument("--confirm-project")
    parser.add_argument("--project-number")
    parser.add_argument("--location", default="southamerica-east1")
    parser.add_argument("--lease-bucket")
    parser.add_argument("--maximum-bytes-billed", type=int, default=1073741824)
    parser.add_argument("--maximum-total-bytes-billed", type=int, default=137438953472)
    parser.add_argument("--work-unit-id")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--dispatch-token")
    parser.add_argument("--pipeline", choices=("upzero", "meta", "analytics"))
    parser.add_argument("--page-budget", type=int, default=20)
    parser.add_argument("--soft-time-budget-seconds", type=float, default=600)
    parser.add_argument("--max-parallel-stores", type=int, default=2)
    parser.add_argument("--max-stores", type=int, default=10)
    parser.add_argument("--max-dispatches", type=int, default=20)
    args = parser.parse_args(argv)
    from src.observability.logging import configure, execution_id

    configure()
    execution_id.set(os.environ.get("CLOUD_RUN_EXECUTION"))
    try:
        if args.all_stores and (not args.dispatch or args.store_id or args.confirm_store):
            raise SafeError("invalid_global_installation_scope")
        if args.auto_activate and not (args.dispatch and args.all_stores):
            raise SafeError("invalid_global_installation_scope")
        if not args.all_stores and not args.store_id:
            raise SafeError("store_confirmation_required")
        limits = Limits(
            page_budget=args.page_budget,
            soft_time_budget_seconds=args.soft_time_budget_seconds,
            global_parallel_store_limit=args.max_parallel_stores,
            max_stores=args.max_stores,
            max_dispatches=args.max_dispatches,
        )
        if args.fixture:
            if args.live or not args.plan_only or not args.target_as_of:
                raise SafeError("offline_plan_only_required")
            payload = json.loads(args.fixture.read_text())
            if payload["registry"]["store_id"] != args.store_id:
                raise SafeError("store_confirmation_required")
            print(
                json.dumps(inspection(payload, args.target_as_of, adopt=args.adopt, limits=limits))
            )
            return 0
        from src.control_plane.cli import clients, gated

        gated(args)  # before imports that discover credentials or perform any IO
        from src.analytics.cloud.transport import scalar
        from src.control_plane.preflight import Prerequisites
        from src.control_plane.worker import Actions
        from src.dashboard.queries import Query
        from src.installation.adapters import InstallationActions
        from src.installation.gateway import InstallationGateway
        from src.installation.orchestrator import Orchestrator
        from src.installation.publication import available
        from src.installation.repository import BigQueryLedger
        from src.installation.worker import Worker
        from src.security.lease import cloud_lease

        transport, _ = clients(args)
        ledger = BigQueryLedger(transport)
        c = ledger.config(args.store_id) if args.store_id else None

        def lease(key: str) -> AbstractContextManager[None]:
            return cloud_lease(args.lease_bucket, key)

        def source(config: StoreConfig, system: str) -> Row:
            cid = getattr(config, system + "_connection_id")
            rows = ledger.rows(
                "source_connections",
                "store_id=@store AND connection_id=@connection AND source_system=@system",
                [
                    scalar("store", "STRING", config.store_id),
                    scalar("connection", "STRING", cid),
                    scalar("system", "STRING", system),
                ],
                limit=3,
            )
            if len(rows) != 1 or rows[0]["status"] not in {"active", "pending"}:
                raise SafeError("source_verification_required")
            return rows[0]

        class ReadTransport:
            def query(self, query: Query, **kwargs: Any) -> list[Row]:
                rows, _ = transport.query(
                    query.sql,
                    [scalar(k, typ, value) for k, (typ, value) in query.parameters.items()],
                )
                return rows

        if args.plan_only or args.create_plan:
            assert c is not None
            # Discovery and persistence share canonical leases for create-plan.
            # Inspection remains read-only and never acquires a lease.
            from contextlib import nullcontext

            with (
                lease("installation-orchestrator-global") if args.create_plan else nullcontext(),
                lease(c.store_id) if args.create_plan else nullcontext(),
            ):
                c = ledger.config(args.store_id)
                if not args.target_as_of:
                    raise SafeError("installation_target_required")
                for system in ("upzero", "meta"):
                    if getattr(c, system + "_enabled"):
                        source(c, system)  # Metadata only; no secret value or source probe.
                ops = ledger.rows(
                    "onboarding_operations",
                    "store_id=@store AND status='INSTALLING'",
                    [scalar("store", "STRING", c.store_id)],
                    limit=3,
                )
                cp = ledger.rows(
                    "sync_checkpoints", "store_id=@store", [scalar("store", "STRING", c.store_id)]
                )
                runs = ledger.rows(
                    "sync_runs", "store_id=@store", [scalar("store", "STRING", c.store_id)]
                )
                if not args.adopt and len(ops) != 1:
                    raise SafeError("installation_onboarding_required")
                configured, plan, units = Planner(limits).calculate(
                    c,
                    args.target_as_of,
                    now(),
                    operation=ops[0] if len(ops) == 1 else None,
                    adopt=args.adopt,
                    checkpoints=cp,
                    runs=runs,
                )
                if args.adopt and configured.operation_b2b and units:
                    from dataclasses import asdict

                    _, published = available(
                        ReadTransport(),
                        args.project,
                        configured,
                        units,
                        now(),
                        "installation-adoption",
                    )
                    if published:
                        configured, plan, units = Planner(limits).calculate(
                            c,
                            args.target_as_of,
                            now(),
                            operation=ops[0] if len(ops) == 1 else None,
                            adopt=True,
                            checkpoints=cp,
                            runs=runs,
                            certified_publication=asdict(published),
                        )
                if args.create_plan:
                    require_creatable_plan(plan)
                    ledger.create(configured, plan, units)
                    saved = ledger.plans(c.store_id)
                    if len(saved) != 1 or saved[0]["plan_id"] != plan["plan_id"]:
                        raise SafeError("installation_plan_conflict")
                    plan, units = saved[0], ledger.units(plan["plan_id"])
                print(json.dumps({"plan": plan, "units": units, **summarize(units)}, default=str))
                return 0

        def publications(plan: Row, units: list[Row]) -> tuple[bool, bool]:
            config = ledger.config(plan["store_id"])
            policy, publication = available(
                ReadTransport(), args.project, config, units, now(), "installation"
            )
            if not config.operation_b2b:
                return False, all(r["status"] == "COMPLETE" for r in units if r["required"])
            final = bool(
                publication and instant(publication.as_of) == instant(plan["target_as_of"])
            )
            if final:
                cp = ledger.rows(
                    "sync_checkpoints",
                    "store_id=@store AND (status NOT IN ('complete','recovered') OR pending_raw_id IS NOT NULL)",
                    [scalar("store", "STRING", config.store_id)],
                )
                final = not cp
            return publication is not None, final

        if args.worker:
            if not all(
                (args.work_unit_id, args.expected_revision, args.dispatch_token, args.pipeline)
            ):
                raise SafeError("installation_work_identity_required")

            def certify(config: StoreConfig, row: Row) -> None:
                units = ledger.units(row["plan_id"])
                if not set(row["dependencies"]) <= {
                    r["work_unit_id"] for r in units if r["status"] == "COMPLETE"
                }:
                    raise SafeError("installation_dependencies")

            actions = InstallationActions(
                Actions(
                    transport,
                    Prerequisites(transport),
                    lease_bucket=args.lease_bucket,
                    meta_secret_reference=os.environ.get("UP_META_SECRET_REFERENCE"),
                ),
                source,
                certify,
            )
            Worker(ledger, actions, lease, limits=limits, verification_source=source).execute(
                args.store_id,
                args.work_unit_id,
                args.expected_revision,
                args.dispatch_token,
                args.pipeline,
            )
            return 0

        from src.installation.automation import AutoPrepare

        prepare = AutoPrepare(ledger, source, lease, limits)

        import google.auth
        import httpx
        from google.auth.transport.requests import Request

        credentials: Any
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        def headers(request: httpx.Request) -> None:
            credentials.refresh(Request())
            request.headers["Authorization"] = "Bearer " + str(credentials.token)

        with httpx.Client(timeout=30, trust_env=False, event_hooks={"request": [headers]}) as http:
            gateway = InstallationGateway(
                http,
                args.project,
                args.location,
                args.lease_bucket,
                project_number=args.project_number,
                maximum_bytes_billed=args.maximum_bytes_billed,
                maximum_total_bytes_billed=args.maximum_total_bytes_billed,
                limits=limits,
            )
            dispatched = Orchestrator(
                ledger,
                gateway,
                lease,
                publications,
                limits=limits,
                prepare=prepare,
                auto_activate=args.auto_activate,
                activation=Prerequisites(transport).activation,
            ).dispatch(args.store_id)
            print(
                json.dumps(
                    {"status": "completed", "dispatches": dispatched, "all_stores": args.all_stores}
                )
            )
        return 0
    except Exception as exc:
        from src.observability.logging import event

        event(
            "job_failed",
            store_id=args.store_id,
            code=exc.code if isinstance(exc, SafeError) else "installation_blocked",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
