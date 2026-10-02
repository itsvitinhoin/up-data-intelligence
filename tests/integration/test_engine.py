import json

import httpx
import pytest

from src.bigquery.repository import SQLiteRepository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.connectors.upzero.fixtures import transport
from src.domain.models import SafeError
from src.ingestion.engine import Engine


def setup(tmp_path, store="A", effective=None):
    settings = Settings(
        store,
        "Synthetic",
        store.lower(),
        "America/Sao_Paulo",
        "conn-" + store,
        "2026-09-01T00:00:00Z",
        purchase_order_id_effective_at=effective,
    )
    repo = SQLiteRepository(str(tmp_path / "test.sqlite"))
    client = UpZeroConnector("SYNTHETIC_SECRET", transport("tests/fixtures/pilot.json"))
    engine = Engine(settings, repo, client)
    engine.registry()
    return engine, repo


@pytest.mark.parametrize("resource", ["customers", "orders", "analytics_facts"])
def test_replay_and_tenant_isolation(tmp_path, resource):
    e, r = setup(tmp_path)
    filters = (
        {"from": "2026-09-01T00:00:00Z", "to": "2026-10-01T00:00:00Z"}
        if resource == "analytics_facts"
        else {}
    )
    a = e.run(resource, filters)
    assert a["status"] == "completed"
    assert e.run(resource, filters)["run_id"] == a["run_id"]
    e.run(resource, filters, refresh=True)
    other, _ = setup(tmp_path, "B")
    other.run(resource, filters)
    table = "analytics_events" if resource == "analytics_facts" else resource
    assert len(r.read(table, "A")) == len(r.read(table, "B"))
    assert len(r.read(table + "_versions", "A")) == len(r.read(table, "A"))
    assert not {x["row_key"] for x in r.read(table, "A")} & {
        x["row_key"] for x in r.read(table, "B")
    }


def test_orders_fields_removed_and_versions(tmp_path):
    e, r = setup(tmp_path)
    e.run("orders", {})
    order = r.read("orders", "A")[0]
    assert order["total"] == "25.00" and order["requested_total"] == "35.00"
    assert len(r.read("order_items", "A")) == 2
    assert any(i["status"] == "removed" for i in r.read("order_items", "A"))
    payload = json.load(open("tests/fixtures/pilot.json"))["orders"][0]
    payload["updated_at"] = "2026-09-03T10:00:00Z"
    payload["payment_status"] = "canceled"
    e.connector = UpZeroConnector(
        "fake",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [payload], "page": 1, "total_pages": 1})
        ),
    )
    e.run("orders", {}, refresh=True)
    assert len(r.read("orders_versions", "A")) == 2
    assert r.read("orders", "A")[0]["payment_status"] == "canceled"


def test_sanitized_raw(tmp_path):
    e, r = setup(tmp_path)
    e.run("customers", {})
    text = json.dumps(r.read("upzero_customers", "A"))
    assert "SYNTHETIC_FORBIDDEN" not in text and "SYNTHETIC_SECRET" not in text
    assert "00000000000100" in text
    assert r.read("customers", "A")[0]["cnpj"] == "00000000000100"


def test_purchase_null_and_correction(tmp_path):
    e, r = setup(tmp_path, effective="2026-09-01T00:00:00Z")
    filters = {"from": "2026-09-01T00:00:00Z", "to": "2026-10-01T00:00:00Z"}
    e.run("analytics_facts", filters)
    assert any(
        x["severity"] == "alert" and x["rule_id"] == "purchase_without_order_id"
        for x in r.read("quality_results", "A")
    )
    events = json.load(open("tests/fixtures/pilot.json"))["analytics_facts"]
    events[0]["order_id"] = 1
    e.connector = UpZeroConnector(
        "fake", httpx.MockTransport(lambda _: httpx.Response(200, json={"data": events}))
    )
    e.run("analytics_facts", filters, refresh=True)
    assert len(r.read("analytics_events", "A")) == 2
    assert len(r.read("analytics_events_versions", "A")) == 3
    assert (
        next(x for x in r.read("touchpoints", "A") if x["source_fact_id"] == "1")[
            "meta_campaign_id"
        ]
        == "001"
    )
    assert all(x["right_namespace"] != "customer_id" for x in r.read("identity_links", "A"))


def test_resume_pending_raw_without_refetch(tmp_path, monkeypatch):
    e, r = setup(tmp_path)
    original = e.transform
    monkeypatch.setattr(e, "transform", lambda _: (_ for _ in ()).throw(RuntimeError("secret")))
    with pytest.raises(SafeError, match="internal_failure"):
        e.run("orders", {})
    assert len(r.read("upzero_orders", "A")) == 1
    monkeypatch.setattr(e, "transform", original)
    e.connector = UpZeroConnector(
        "fake", httpx.MockTransport(lambda _: pytest.fail("must replay RAW"))
    )
    assert e.run("orders", {})["status"] == "completed"
    assert len(r.read("orders", "A")) == 1


def test_bad_money_keeps_raw(tmp_path):
    e, r = setup(tmp_path)
    payload = json.load(open("tests/fixtures/pilot.json"))["orders"][0]
    payload["total"] = "not-money"
    e.connector = UpZeroConnector(
        "fake",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [payload], "page": 1, "total_pages": 1})
        ),
    )
    assert e.run("orders", {})["status"] == "completed_with_errors"
    assert len(r.read("upzero_orders", "A")) == 1 and not r.read("orders", "A")


def test_deterministic_links_resolve_only_same_store(tmp_path):
    from src.quality.service import reconcile

    e, r = setup(tmp_path)
    e.run("analytics_facts", {"from": "2026-09-01T00:00:00Z", "to": "2026-09-02T00:00:00Z"})
    other, _ = setup(tmp_path, "B")
    other.run("orders", {})
    reconcile(r, e.cfg, "quality-before")
    assert any(x["link_status"] == "pending" for x in r.read("event_order_links", "A"))
    e.run("orders", {})
    reconcile(r, e.cfg, "quality-after")
    assert any(x["link_status"] == "matched" for x in r.read("event_order_links", "A"))
    assert any(x["link_status"] == "missing_order_id" for x in r.read("event_order_links", "A"))


def test_duplicate_customer_on_page_warns_no_duplicate_current(tmp_path):
    e, r = setup(tmp_path)

    def handler(req):
        return httpx.Response(
            200,
            json={"data": [{"id": "1"}, {"id": "1"}] if "after_id" not in req.url.params else []},
        )

    e.connector = UpZeroConnector("fake", httpx.MockTransport(handler))
    e.run("customers", {})
    assert len(r.read("customers", "A")) == 1
    assert any(q["rule_id"] == "duplicate_customers" for q in r.read("quality_results", "A"))


def test_older_order_cannot_overwrite_current(tmp_path):
    e, r = setup(tmp_path)
    e.run("orders", {})
    p = json.load(open("tests/fixtures/pilot.json"))["orders"][0]
    p["updated_at"] = "2026-09-01T00:00:00Z"
    p["payment_status"] = "unpaid"
    e.connector = UpZeroConnector(
        "fake",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [p], "page": 1, "total_pages": 1})
        ),
    )
    e.run("orders", {}, refresh=True)
    assert r.read("orders", "A")[0]["payment_status"] == "paid"


def test_missing_items_does_not_delete_known_items(tmp_path):
    e, r = setup(tmp_path)
    e.run("orders", {})
    p = json.load(open("tests/fixtures/pilot.json"))["orders"][0]
    p["updated_at"] = "2026-09-04T00:00:00Z"
    del p["items"]
    e.connector = UpZeroConnector(
        "fake",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [p], "page": 1, "total_pages": 1})
        ),
    )
    e.run("orders", {}, refresh=True)
    assert len(r.read("order_items", "A")) == 2


def test_missing_technical_store_quality(tmp_path):
    e, r = setup(tmp_path)
    batch = e.transform(
        {"store_id": "", "run_id": "x", "resource": "analytics_facts", "payload": {"data": [{}]}}
    )
    assert batch.failed == 1
    assert batch.rows["quality_results"][0]["rule_id"] == "fact_without_technical_store"


def test_old_raw_replay_does_not_undo_event_correction(tmp_path):
    e, r = setup(tmp_path)
    filters = {"from": "2026-09-01T00:00:00Z", "to": "2026-09-02T00:00:00Z"}
    original = e.run("analytics_facts", filters)
    events = json.load(open("tests/fixtures/pilot.json"))["analytics_facts"]
    events[0]["order_id"] = 1
    e.connector = UpZeroConnector(
        "fake", httpx.MockTransport(lambda _: httpx.Response(200, json={"data": events}))
    )
    e.run("analytics_facts", filters, refresh=True)
    e.replay("analytics_facts", original["run_id"])
    assert (
        next(x for x in r.read("analytics_events", "A") if x["fact_id"] == "1")["order_id"] == "1"
    )


def test_cutover_rechecks_unchanged_events(tmp_path):
    from dataclasses import replace

    from src.quality.service import reconcile

    e, r = setup(tmp_path)
    e.run("analytics_facts", {"from": "2026-09-01T00:00:00Z", "to": "2026-09-02T00:00:00Z"})
    reconcile(r, replace(e.cfg, purchase_order_id_effective_at="2026-09-01T00:00:00Z"), "cutover")
    assert any(
        q["rule_id"] == "purchase_without_order_id_after_effective" and q["failed_count"] == 1
        for q in r.read("quality_results", "A")
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        ("complete", None),
        ("needs_review", "run_needs_review_use_replay_or_refresh"),
        ("recovered", "run_recovered_use_refresh"),
    ],
)
def test_terminal_checkpoint_recovery_never_relabels_original_as_success(
    tmp_path, status, expected
):
    engine, repo = setup(tmp_path)
    original = engine.run("customers", {})
    checkpoints = repo.read("sync_checkpoints", "A")
    checkpoints[0]["status"] = status
    if status != "complete":
        original["status"] = "completed_with_errors"
        repo.write({"sync_runs": [original]})
    repo.write({"sync_checkpoints": checkpoints})
    before = repo.read("sync_runs", "A")
    engine.connector = UpZeroConnector(
        "SYNTHETIC", httpx.MockTransport(lambda _: pytest.fail("must not recollect source"))
    )
    if expected:
        with pytest.raises(SafeError, match=expected):
            engine.run("customers", {})
    else:
        assert engine.run("customers", {}) == original
    assert repo.read("sync_runs", "A") == before
    assert repo.read("sync_checkpoints", "A") == checkpoints
