"""Proof against the existing Engine, not the proposed synthetic transaction oracle."""

from src.bigquery.repository import SQLiteRepository
from src.config.settings import Settings
from src.connectors.upzero.client import UpZeroConnector
from src.connectors.upzero.fixtures import transport
from src.ingestion.engine import Engine


def setup(tmp_path):
    cfg = Settings("A", "Synthetic", "a", "America/Sao_Paulo", "conn-a", "2026-09-01T00:00:00Z")
    repo = SQLiteRepository(str(tmp_path / "audit.sqlite"))
    client = UpZeroConnector("synthetic", transport("tests/fixtures/pilot.json"))
    return Engine(cfg, repo, client), repo


def test_identical_refresh_adds_raw_but_not_core_versions(tmp_path):
    engine, repo = setup(tmp_path)
    filters = {"from": "2026-09-01T00:00:00Z", "to": "2026-10-01T00:00:00Z"}
    first = engine.run("analytics_facts", filters)
    raw = repo.read("upzero_analytics_facts", "A")
    core = repo.read("analytics_events", "A")
    versions = repo.read("analytics_events_versions", "A")
    assert engine.run("analytics_facts", filters)["run_id"] == first["run_id"]
    assert len(repo.read("upzero_analytics_facts", "A")) == len(raw)
    engine.run("analytics_facts", filters, refresh=True)
    assert len(repo.read("upzero_analytics_facts", "A")) == 2 * len(raw)
    assert repo.read("analytics_events", "A") == core
    assert repo.read("analytics_events_versions", "A") == versions
