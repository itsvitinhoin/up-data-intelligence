"""Production Engine/connector/normalizer, compact synthetic storage for 350k rows."""

from collections import defaultdict
from contextlib import nullcontext
from copy import deepcopy

import httpx
import pytest

from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.domain.models import SafeError
from src.ingestion.engine import Engine
from src.installation.model import Limits
from src.installation.worker import Worker
from tests.installation.fakes import MemoryLedger
from tests.installation.test_planner import END, NOW, START, graph


class CompactRepository:
    """Full pending RAW + ledger; projected current rows, retained identity sets for CORE."""

    def __init__(self):
        self.rows = defaultdict(dict)
        self.keys = defaultdict(set)
        self.operations = []
        self.fail_core = False

    def read(self, table, store, keys=None):
        selected = (
            list(self.rows[table].values())
            if keys is None
            else [self.rows[table][k] for k in keys if k in self.rows[table]]
        )
        return deepcopy([r for r in selected if r["store_id"] == store])

    def write(self, tables):
        if "analytics_events" in tables and self.fail_core:
            self.fail_core = False
            raise SafeError("synthetic_definite_write_failure")
        for table, rows in tables.items():
            self.operations.append(table)
            for row in rows:
                key = row["row_key"]
                self.keys[table].add(key)
                if table in {"analytics_events", "customers"}:
                    self.rows[table][key] = {
                        k: v
                        for k, v in row.items()
                        if k
                        in {
                            "row_key",
                            "store_id",
                            "payload_hash",
                            "transform_version",
                            "observed_at",
                            "source_updated_at",
                        }
                    }
                elif table in {
                    "upzero_analytics_facts",
                    "sync_runs",
                    "sync_checkpoints",
                    "upzero_customers",
                }:
                    self.rows[table][key] = deepcopy(row)
        # A previous page remains logically durable; drop synthetic payload only after
        # the transaction cleared pending. History metrics v2 never rescan old RAW.
        for cp in tables.get("sync_checkpoints", []):
            if cp.get("pending_raw_id") is None:
                for raw in self.rows["upzero_analytics_facts"].values():
                    if raw["run_id"] == cp["run_id"]:
                        raw["payload"] = {"data": []}

    def find(self, table, store, field, values):
        return [r for r in self.read(table, store) if r.get(field) in values]

    def iter_find(self, table, store, field, values):
        yield from self.find(table, store, field, values)


def connector(pages=350, size=1000):
    calls = []

    def response(request):
        index = int(request.url.params.get("cursor") or 0)
        calls.append(index)
        payload = {
            "data": [
                {
                    "id": index * size + i + 1,
                    "event_id": f"synthetic-event-{index * size + i}",
                    "event_name": "page_view",
                    "occurred_at": START,
                }
                for i in range(size)
            ],
            "next_cursor": str(index + 1) if index + 1 < pages else None,
        }
        return httpx.Response(200, json=payload)

    return UpZeroConnector(
        "SYNTHETIC-NOT-A-CREDENTIAL", httpx.MockTransport(response), max_pages=20
    ), calls


def test_350_pages_350k_facts_18_slices_same_logical_unit_checkpoint_no_duplicates():
    c, plan, rows = graph(1)
    row = next(r for r in rows if r["resource"] == "analytics_facts")
    row["dependencies"] = []
    ledger = MemoryLedger(c, plan, [row])
    repo = CompactRepository()
    client, calls = connector()
    cfg = Settings(
        c.store_id, "Synthetic", "synthetic", "America/Sao_Paulo", c.upzero_connection_id, START
    )
    runs = set()

    def advance(config, unit, limits):
        result = Engine(cfg, repo, client).advance(
            "analytics_facts",
            unit["filters"],
            mode=unit["mode"],
            page_budget=limits.page_budget,
            soft_time_budget_seconds=limits.soft_time_budget_seconds,
        )
        runs.add(result["run_id"])
        return {
            **result,
            "records_processed": result["core_records_processed"],
            "pages_processed": result["core_pages_processed"],
            "checkpoint_plan_key": result["plan_key"],
        }

    for index in range(18):
        current = ledger.units()[0]
        reserved = ledger.reserve(current, f"synthetic-token-{index}", NOW, Limits())
        # Newly constructed worker models process replacement after slice 5 as well.
        worker = Worker(ledger, advance, lambda key: nullcontext(), clock=lambda: NOW)
        result = worker.execute(
            c.store_id,
            row["work_unit_id"],
            reserved["revision"],
            reserved["dispatch_token"],
            "upzero",
        )
        cp = repo.read("sync_checkpoints", c.store_id)[0]
        assert cp["pending_raw_id"] is None
        if index < 17:
            assert result["status"] == "PENDING" and cp["status"] == "running"
            assert repo.read("sync_runs", c.store_id)[0]["finished_at"] is None
            assert cp["position"]["cursor"] == str((index + 1) * 20)
    assert (
        result["status"] == "COMPLETE"
        and result["attempt_count"] == 18
        and result["failure_count"] == 0
    )
    assert result["records_processed"] == 350000 and result["pages_processed"] == 350
    assert len(runs) == 1 and len(ledger.units()) == 1
    assert calls == list(range(350))
    assert len(repo.keys["upzero_analytics_facts"]) == 350
    assert len(repo.keys["analytics_events"]) == 350000
    assert len(repo.keys["analytics_events_versions"]) == 350000
    assert cp["status"] == "complete" and cp["position"] == {}
    again = Engine(cfg, repo, client).advance("analytics_facts", row["filters"], mode=row["mode"])
    assert again["complete"] and len(calls) == 350 and again["run_id"] == result["run_id"]
    client.close()


def test_pending_raw_promoted_before_next_api_page():
    repo = CompactRepository()
    client, calls = connector(pages=2, size=3)
    cfg = Settings(
        "synthetic", "Synthetic", "synthetic", "America/Sao_Paulo", "synthetic-conn", START
    )
    engine = Engine(cfg, repo, client)
    filters = {"from": START, "to": END, "limit": 1000}
    repo.fail_core = True
    with pytest.raises(SafeError):
        engine.advance("analytics_facts", filters, page_budget=1)
    assert calls == [0]
    cp = repo.read("sync_checkpoints", "synthetic")[0]
    assert cp["pending_raw_id"] is not None
    yielded = engine.advance("analytics_facts", filters, page_budget=1)
    assert yielded["yielded"] and calls == [0]
    assert repo.read("sync_checkpoints", "synthetic")[0]["pending_raw_id"] is None
    final = engine.advance("analytics_facts", filters, page_budget=1)
    assert final["complete"] and calls == [0, 1] and len(repo.keys["analytics_events"]) == 6
    client.close()


@pytest.mark.parametrize("budget", [0, -1, float("nan"), float("inf"), 601])
def test_invalid_soft_budget_fails_before_fetch(budget):
    repo = CompactRepository()
    client, calls = connector(1, 1)
    cfg = Settings("synthetic", "Synthetic", "synthetic", "UTC", "synthetic-conn", START)
    with pytest.raises(SafeError):
        Engine(cfg, repo, client).advance("analytics_facts", {}, soft_time_budget_seconds=budget)
    assert not calls
    client.close()


def test_soft_time_boundary_yields_after_promoted_page(monkeypatch):
    from itertools import count

    ticks = count(step=10)
    monkeypatch.setattr("src.ingestion.engine.time.monotonic", lambda: next(ticks))
    repo = CompactRepository()
    client, calls = connector(pages=2, size=2)
    cfg = Settings("synthetic", "Synthetic", "synthetic", "UTC", "synthetic-conn", START)
    filters = {"from": START, "to": END, "limit": 1000}
    result = Engine(cfg, repo, client).advance(
        "analytics_facts", filters, page_budget=20, soft_time_budget_seconds=1
    )
    assert result["yielded"] and calls == [0]
    cp = repo.read("sync_checkpoints", "synthetic")[0]
    assert cp["pending_raw_id"] is None and cp["position"] == {"cursor": "1"}
    assert len(repo.keys["analytics_events"]) == 2
    final = Engine(cfg, repo, client).advance(
        "analytics_facts", filters, page_budget=20, soft_time_budget_seconds=1
    )
    assert final["complete"] and len(repo.keys["analytics_events"]) == 4
    client.close()
