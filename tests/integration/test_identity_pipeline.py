import json
import logging

from src.bigquery.repository import SQLiteRepository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.connectors.upzero.fixtures import transport
from src.ingestion.engine import Engine
from src.normalization.identity import resolve_customer


def test_identity_end_to_end_replay_raw_and_logs(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="upzero")
    fixture = json.load(open("tests/fixtures/pilot.json"))
    fixture["orders"][0]["customer"] = fixture["customers"][0]
    fixture["orders"][0]["shipping_address"] = {"full_address": "Synthetic private address"}
    fixture["customers"][0]["wholesale_profile"]["meta"] = {
        "business": "preserve",
        "api_key": "SYNTHETIC_FORBIDDEN",
    }
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(fixture))
    cfg = Settings("A", "Synthetic", "a", "America/Sao_Paulo", "conn-A", "2026-09-01T00:00:00Z")
    repo = SQLiteRepository(str(tmp_path / "identity.sqlite"))
    engine = Engine(cfg, repo, UpZeroConnector("SYNTHETIC_SECRET", transport(str(path))))
    engine.registry()
    run = engine.run(
        "analytics_facts", {"from": "2026-09-01T00:00:00Z", "to": "2026-09-02T00:00:00Z"}
    )
    events = repo.read("analytics_events", "A")
    linked = next(e for e in events if e["order_id"])
    assert resolve_customer(linked, [], [])["customer_id"] is None
    order_run = engine.run("orders", {})
    customer_run = engine.run("customers", {})
    orders, customers = repo.read("orders", "A"), repo.read("customers", "A")
    for table in ("analytics_events", "touchpoints"):
        for row in repo.read(table, "A"):
            assert (
                not {"cnpj", "cpf", "email", "phone", "company_name", "customer_snapshot"}
                & row.keys()
            )
            resolved = resolve_customer(row, orders, customers)
            assert resolved["customer_id"] == ("1" if row["order_id"] else None)
            if resolved["customer_id"]:
                assert customers[0]["cnpj_digits"] == "00000000000100"
        first = next(e for e in repo.read(table, "A") if e["fact_id"] == "1")
        assert (first["meta_campaign_id"], first["meta_adset_id"], first["meta_ad_id"]) == (
            "001",
            "002",
            "003",
        )
        assert all(first[k] for k in ("fbclid", "fbc", "fbp", "gclid", "landing_url"))
    raw_before = repo.read("upzero_orders", "A")
    payload = raw_before[0]["payload"]["data"][0]
    assert payload["customer"]["wholesale_profile"]["meta"]["business"] == "preserve"
    assert payload["shipping_address"] == fixture["orders"][0]["shipping_address"]
    tables = (
        "orders",
        "orders_versions",
        "customers",
        "customers_versions",
        "analytics_events",
        "analytics_events_versions",
        "touchpoints",
        "identity_links",
    )
    before = {t: repo.read(t, "A") for t in tables}
    for resource, result in (
        ("customers", customer_run),
        ("orders", order_run),
        ("analytics_facts", run),
    ):
        engine.replay(resource, result["run_id"])
    assert {t: repo.read(t, "A") for t in tables} == before
    assert repo.read("upzero_orders", "A") == raw_before
    links = before["identity_links"]
    assert {e["evidence_type"] for e in links} == {
        "observed_order_customer",
        "observed_fact_order",
        "observed_cooccurrence",
    }
    for edge in links:
        assert edge["confidence_type"] == "DETERMINISTIC"
        assert edge["identifier_type_from"] == edge["left_namespace"]
        assert edge["identifier_value_to"] == edge["right_id"]
        assert edge["first_seen_at"] == edge["last_seen_at"] == edge["observed_at"]
        if edge["source_entity_type"] == "order":
            assert edge["source_fact_id"] is None
    persisted = json.dumps(before) + json.dumps(raw_before)
    assert "SYNTHETIC_FORBIDDEN" not in persisted and "SYNTHETIC_SECRET" not in persisted
    for forbidden in (
        "SYNTHETIC_FORBIDDEN",
        "SYNTHETIC_SECRET",
        "test@example.invalid",
        "Synthetic private address",
    ):
        assert forbidden not in caplog.text


def test_transform_upgrade_preserves_versions_and_corrected_edges(tmp_path, monkeypatch):
    import src.ingestion.engine as engine_module

    fixture = json.load(open("tests/fixtures/pilot.json"))
    path = tmp_path / "synthetic-upgrade.json"
    path.write_text(json.dumps(fixture))
    cfg = Settings("A", "Synthetic", "a", "America/Sao_Paulo", "conn-A", "2026-09-01T00:00:00Z")
    repo = SQLiteRepository(str(tmp_path / "upgrade.sqlite"))
    engine = Engine(cfg, repo, UpZeroConnector("fake", transport(str(path))))
    engine.registry()
    # Simulate a prior transform identity; the test exercises version transition,
    # not the historical deployed schema or a live BigQuery migration.
    monkeypatch.setattr(engine_module, "VERSION", "1.0.0")
    first = engine.run("orders", {})
    old = repo.read("orders", "A")[0]
    monkeypatch.setattr(engine_module, "VERSION", "1.1.0")
    engine.replay("orders", first["run_id"])
    upgraded = repo.read("orders", "A")[0]
    assert upgraded["version_id"] != old["version_id"]
    assert len(repo.read("orders_versions", "A")) == 2
    assert upgraded["customer_snapshot"] == old["customer_snapshot"]
    fixture["orders"][0]["customer"]["id"] = "202"
    fixture["orders"][0]["updated_at"] = "2026-09-03T10:00:00Z"
    path.write_text(json.dumps(fixture))
    engine.connector = UpZeroConnector("fake", transport(str(path)))
    engine.run("orders", {}, refresh=True)
    current = repo.read("orders", "A")[0]
    edges = repo.read("identity_links", "A")
    active = [
        x
        for x in edges
        if x["source_entity_type"] == "order" and x["source_version_id"] == current["version_id"]
    ]
    assert len(active) == 1 and active[0]["identifier_value_to"] == "202"
    assert len(edges) == 3  # Old evidence retained, not an active union of identities.
    engine.replay("orders", first["run_id"])
    assert repo.read("orders", "A")[0] == current
    assert len(repo.read("identity_links", "A")) == 3
