"""Authorized history requests prepare V2 work; never fetch a source synchronously."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from src.admin.contracts import AdminError, Principal, authorize, exact, identity
from src.analytics.cloud.transport import scalar
from src.connectors.meta.purchase_reporting import PurchaseCertificate, selected_reporting
from src.control_plane.model import StoreConfig, Window
from src.control_plane.preflight import Prerequisites
from src.dashboard.queries import Query
from src.domain.models import SafeError
from src.installation.extension_repository import ExtensionLedger
from src.installation.extensions import ExtensionPlanner
from src.installation.model import Row
from src.installation.progress import summarize
from src.installation.publication import available
from src.installation.repository import BigQueryLedger
from src.intelligence.live.runtime import reporting
from src.utils.data import now


class HistoryService:
    def __init__(
        self,
        ledger: ExtensionLedger,
        lease: Callable[[str], AbstractContextManager[None]],
        subject_key: bytes,
        clock: Callable[[], str] = now,
        *,
        purchase_certificates: tuple[PurchaseCertificate, ...] = (),
    ):
        self.ledger, self.lease, self.subject_key, self.clock = ledger, lease, subject_key, clock
        self.purchase_certificates = purchase_certificates

    def publication(self, config: StoreConfig) -> Row:
        ledger = self.ledger
        primary = BigQueryLedger(ledger.transport)
        plans = primary.plans(config.store_id)
        if len(plans) != 1 or plans[0]["status"] != "COMPLETE":
            raise AdminError("extension_primary_installation_required")
        units = primary.units(plans[0]["plan_id"])
        if not units or any(u["status"] != "COMPLETE" for u in units):
            raise AdminError("extension_primary_installation_required")

        class Reader:
            def query(self, query: Query, **kwargs: Any) -> list[Row]:
                rows, _ = ledger.transport.query(
                    query.sql,
                    [scalar(k, typ, value) for k, (typ, value) in query.parameters.items()],
                )
                return rows

        policy, published = available(
            Reader(),
            ledger.transport.config.project,
            config,
            units,
            self.clock(),
            "history-admission",
        )
        if policy is None or published is None:
            raise AdminError("extension_certified_publication_required")
        # Publication carries identity/window; coverage is separately certified by
        # available(). Preserve those flags when passing evidence to the planner.
        return {
            **asdict(published),
            "history_complete": policy.history_complete,
            "facts_complete": policy.facts_complete,
        }

    def prepare(
        self,
        binding: Row,
        provider: str,
        start: str,
        end: str,
        purpose: str,
        requested_by_hash: str,
    ) -> Row:
        # Caller already resolves an authenticated canonical binding. Locks serialize
        # admission against normal dispatch and source configuration changes.
        store = binding["store_id"]
        with (
            self.lease("store-dispatch-global"),
            self.lease("installation-orchestrator-global"),
            self.lease(store),
        ):
            config = self.ledger.config(store)
            sources = self.ledger.rows(
                "source_connections",
                "store_id=@store AND source_system=@system",
                [scalar("store", "STRING", store), scalar("system", "STRING", provider)],
                limit=3,
            )
            if len(sources) != 1:
                raise AdminError("extension_source_not_active")
            published = self.publication(config)
            checkpoints, runs = self.ledger.evidence(store)
            account = (
                Prerequisites(self.ledger.transport).account(config) if provider == "meta" else None
            )
            report = (
                reporting(
                    account,
                    config.policy(
                        Window(
                            published["report_from"],
                            published["report_to"],
                            published["as_of"],
                            self.clock(),
                            self.clock(),
                        )
                    ),
                )
                if account
                else None
            )
            if account and report and purpose in {"META_CREATIVE_COVERAGE", "META_PERIOD_REPORT"}:
                report = selected_reporting(account, report, self.purchase_certificates)
            plan, units = ExtensionPlanner().calculate(
                config,
                sources[0],
                purpose,
                start,
                end,
                self.clock(),
                requested_by_hash=requested_by_hash,
                checkpoints=checkpoints,
                runs=runs,
                publication=published,
                account=account,
                reporting=report,
            )
            # A second overlapping unfinished extension is not a safe replan.
            for existing in self.ledger.plans(store):
                if existing["plan_id"] != plan["plan_id"] and existing["status"] != "COMPLETE":
                    raise AdminError("extension_existing_work_requires_completion")
            self.ledger.create(config, plan, units)
            saved = [p for p in self.ledger.plans(store) if p["plan_id"] == plan["plan_id"]]
            if len(saved) != 1:
                raise SafeError("bigquery_write_outcome_unknown")
            return public_plan(saved[0], self.ledger.units(plan["plan_id"]))

    def create(self, principal: Principal, binding: Row, value: Any) -> Row:
        admin = authorize(principal)
        admin.authorize_tenant(binding["tenant_id"])
        payload = exact(value, {"provider", "from", "to"})
        provider = payload["provider"]
        if provider not in {"upzero", "meta"} or binding.get("operation") != "B2B":
            raise AdminError("extension_provider_unavailable", 400)
        try:
            # Browser uses inclusive local end; planner consistently uses exclusive.
            start = date.fromisoformat(payload["from"]).isoformat()
            end = (date.fromisoformat(payload["to"]) + timedelta(days=1)).isoformat()
        except (TypeError, ValueError):
            raise AdminError("extension_closed_range_required", 400) from None
        return self.prepare(
            binding,
            provider,
            start,
            end,
            "HISTORY_EXTENSION",
            identity(admin.subject, self.subject_key),
        )

    def list(self, principal: Principal, binding: Row) -> Row:
        admin = authorize(principal)
        admin.authorize_tenant(binding["tenant_id"])
        return {
            "data": [
                public_plan(p, self.ledger.units(p["plan_id"]))
                for p in self.ledger.plans(binding["store_id"])
            ]
        }


def public_plan(plan: Row, units: list[Row]) -> Row:
    extension = plan["adopted_coverage"]["extension"]
    summary = summarize(units)
    return dict(
        plan_id=plan["plan_id"],
        purpose=extension["purpose"],
        provider=extension["source"],
        status=plan["status"],
        requested_from=plan["requested_from"],
        target_as_of=plan["target_as_of"],
        requested_at=plan["created_at"],
        error_code=plan.get("error_code"),
        progress=summary["progress"],
        work=summary["work"],
        resources=[
            dict(
                resource=r,
                total=sum(u["resource"] == r for u in units),
                complete=sum(u["resource"] == r and u["status"] == "COMPLETE" for u in units),
            )
            for r in sorted({u["resource"] for u in units})
        ],
    )
