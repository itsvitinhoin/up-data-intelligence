"""Central DEV orchestrator; approved explicit window or previous closed local day."""

import argparse
import json
from dataclasses import asdict
from threading import Lock
from typing import Any

from src.control_plane.cli import clients, common, gated
from src.control_plane.dispatcher import Dispatcher
from src.control_plane.gateway import RunGateway
from src.control_plane.model import PIPELINES, StoreConfig, Window
from src.control_plane.preflight import Prerequisites
from src.control_plane.repository import BigQueryRegistry
from src.domain.models import SafeError
from src.observability.logging import configure, event
from src.security.lease import cloud_lease
from src.utils.data import now


def main() -> int:
    parser = argparse.ArgumentParser(description="Shared dispatcher; no implicit live execution")
    common(parser)
    parser.add_argument("--project-number", default=None)
    parser.add_argument("--pipeline", choices=PIPELINES, required=True)
    parser.add_argument("--max-parallel-stores", type=int, default=2)
    parser.add_argument("--window-mode", choices=("explicit", "previous-closed-day"), required=True)
    for key in ("report-from", "report-to", "as-of", "source-snapshot-at", "calculated-at"):
        parser.add_argument("--" + key)
    args = parser.parse_args()
    configure()
    try:
        gated(args)
        if not 1 <= args.max_parallel_stores <= 10:
            raise ValueError("invalid_parallel_store_limit")
        at = now()
        fixed = (
            Window(
                args.report_from,
                args.report_to,
                args.as_of,
                args.source_snapshot_at,
                args.calculated_at,
            )
            if args.window_mode == "explicit"
            else None
        )
        transport, _ = clients(args)
        # Access token is discovered only after all DEV confirmations. Kept server-side.
        import google.auth
        import httpx
        from google.auth.transport.requests import Request

        credentials: Any
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        refresh_lock = Lock()

        def authorize(request: httpx.Request) -> None:
            with refresh_lock:
                if not credentials.valid:
                    credentials.refresh(Request())
                request.headers["Authorization"] = "Bearer " + credentials.token

        with httpx.Client(
            timeout=30,
            trust_env=False,
            follow_redirects=False,
            event_hooks={"request": [authorize]},
        ) as client:
            gateway = RunGateway(
                client,
                args.project,
                args.location,
                args.lease_bucket,
                project_number=args.project_number,
                maximum_bytes_billed=args.maximum_bytes_billed,
                maximum_total_bytes_billed=args.maximum_total_bytes_billed,
            )

            def check(config: StoreConfig, pipeline: str, window: Window) -> None:
                # Separate bounded client/transport per store, not one limitless shared reader.
                reader, meter = clients(args)
                status = "failed"
                try:
                    Prerequisites(reader).check(config, pipeline, window)
                    status = "completed"
                finally:
                    event(
                        "store_dispatch_preflight_finished",
                        store_id=config.store_id,
                        pipeline=pipeline,
                        status=status,
                        query_count=meter.query_count,
                        query_duration_ms=meter.duration_ms,
                        bytes_processed=meter.bytes_processed,
                        **meter.query_budget.metrics(),
                    )

            dispatcher = Dispatcher(
                BigQueryRegistry(transport),
                gateway,
                check,
                lambda store: cloud_lease(args.lease_bucket, store),
                args.max_parallel_stores,
            )

            def window(config: StoreConfig) -> Window:
                daily = fixed or Window.previous_closed_day(config.timezone or "", at)
                reader, _ = clients(args)
                return Prerequisites(reader).recurring_window(config, args.pipeline, daily)

            results = dispatcher.run(
                args.pipeline,
                window,
            )
            print(json.dumps([asdict(result) for result in results]))
            return int(any(r.status != "completed" for r in results))
    except Exception as exc:
        event(
            "job_failed",
            pipeline=args.pipeline,
            code=exc.code if isinstance(exc, SafeError) else "store_dispatch_failed",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
