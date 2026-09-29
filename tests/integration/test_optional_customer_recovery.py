import copy

import httpx
import pytest

import src.ingestion.engine as engine_module
from src.bigquery.repository import SQLiteRepository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.ingestion.engine import Engine
from src.normalization.entities import VERSION, normalize
from src.normalization.identity import resolve_customer


def test_four_synthetic_failed_windows_recover_without_raw_or_checkpoint_mutation(
    tmp_path, monkeypatch
):
    cfg = Settings("A", "Synthetic", "a", "UTC", "conn-A", "2026-09-01T00:00:00Z")
    repo = SQLiteRepository(str(tmp_path / "recovery.sqlite"))
    cases = ["", "   ", "", ""]
    sources = {}
    for day, value in enumerate(cases, 1):
        sources[f"2026-09-{day:02d}"] = [
            {
                "id": str(100 + day),
                "customer_type": "WHOLESALE",
                "wholesale_profile": {"address_state": value, "address_city": value},
            },
            {
                "id": str(200 + day),
                "customer_type": "WHOLESALE",
                "wholesale_profile": {"address_state": "SP", "address_city": "Synthetic city"},
            },
        ]

    def handler(request):
        data = [] if "after_id" in request.url.params else sources[request.url.params["start_date"]]
        return httpx.Response(
            200, json={"data": sorted(data, key=lambda r: int(r["id"]), reverse=True)}
        )

    engine = Engine(cfg, repo, UpZeroConnector("SYNTHETIC", httpx.MockTransport(handler)))
    engine.registry()

    # Reproduce the confirmed historical failure without importing live data:
    # the legacy STRING converter rejects optional blank geography.
    def legacy(resource, source):
        if resource == "customers":
            profile = source.get("wholesale_profile", {})
            if any(
                isinstance(profile.get(f), str) and not profile[f].strip()
                for f in ("address_state", "address_city")
            ):
                raise ValueError("invalid_id")
        return normalize(resource, source)

    monkeypatch.setattr(engine_module, "normalize", legacy)
    monkeypatch.setattr(engine_module, "VERSION", "1.1.0")
    originals = []
    for date in sources:
        result = engine.run("customers", {"start_date": date, "end_date": date, "limit": 200})
        assert result["status"] == "completed_with_errors" and result["core_records_failed"] == 1
        originals.append(result)
    raw_before = copy.deepcopy(repo.read("upzero_customers", "A"))
    checkpoints_before = copy.deepcopy(repo.read("sync_checkpoints", "A"))
    assert all(cp["status"] == "needs_review" for cp in checkpoints_before)
    for raw in raw_before:
        if raw["payload"]["data"]:
            date = raw["request_filters"]["start_date"]
            assert raw["payload"]["data"] == sorted(
                sources[date], key=lambda r: int(r["id"]), reverse=True
            )

    monkeypatch.setattr(engine_module, "normalize", normalize)
    monkeypatch.setattr(engine_module, "VERSION", VERSION)
    engine.connector = UpZeroConnector(
        "SYNTHETIC", httpx.MockTransport(lambda _: pytest.fail("recovery must use persisted RAW"))
    )
    for original in originals:
        report = engine.replay("customers", original["run_id"])
        assert report["status"] == "completed"
        assert report["core_records_inserted"] == 1 and report["core_records_updated"] == 1
        assert report["core_records_failed"] == 0 and report["replay_records_read"] == 2
        assert report["source_records_read"] == report["raw_pages_written"] == 0
    customers = repo.read("customers", "A")
    assert len(customers) == len({c["customer_id"] for c in customers}) == 8
    assert all(
        c["state"] is None and c["city"] is None for c in customers if int(c["customer_id"]) < 200
    )
    customer = next(c for c in customers if c["customer_id"] == "101")
    assert customer["wholesale_profile"]["address_state"] == ""
    order = {
        "store_id": "A",
        "source_system": "upzero",
        "order_id": "9001",
        "customer_id": "101",
        "version_id": "synthetic-order",
    }
    event = {"store_id": "A", "source_system": "upzero", "order_id": "9001"}
    assert resolve_customer(event, [order], customers)["customer_id"] == "101"
    versions_before = repo.read("customers_versions", "A")
    for original in originals:
        report = engine.replay("customers", original["run_id"])
        assert report["status"] == "completed"
        assert report["core_records_inserted"] == report["core_records_updated"] == 0
    assert repo.read("customers", "A") == customers
    assert repo.read("customers_versions", "A") == versions_before
    assert repo.read("upzero_customers", "A") == raw_before
    assert repo.read("sync_checkpoints", "A") == checkpoints_before
    assert all(
        repo.read("sync_runs", "A", [r["run_id"]])[0]["status"] == "completed_with_errors"
        for r in originals
    )
