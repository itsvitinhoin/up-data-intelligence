import json
import sys
from dataclasses import asdict

from src.config.settings import Settings
from src.jobs.cli import main


def test_offline_cli_no_network(tmp_path, monkeypatch):
    cfg = Settings(
        "A",
        "Synthetic",
        "a",
        "UTC",
        "conn",
        "2026-09-01T00:00:00Z",
        state_path=str(tmp_path / "db"),
    )
    p = tmp_path / "config.json"
    p.write_text(json.dumps(asdict(cfg)))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "job",
            "--config",
            str(p),
            "--mode",
            "backfill",
            "--from",
            "2026-09-01",
            "--to",
            "2026-09-02",
        ],
    )
    assert main() == 0


def test_live_requires_confirmation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["job", "--live"])
    assert main() == 1


def test_cli_page_limit_configures_api_without_cloud(tmp_path, monkeypatch):
    from src.ingestion.engine import Engine

    monkeypatch.setenv(
        "UP_CONFIG_JSON",
        json.dumps(
            asdict(
                Settings(
                    "A",
                    "Synthetic",
                    "a",
                    "UTC",
                    "c",
                    "2026-09-01T00:00:00Z",
                    state_path=str(tmp_path / "db"),
                )
            )
        ),
    )
    monkeypatch.setattr(sys, "argv", ["job", "--mode", "quality", "--page-limit", "1000"])
    original = Engine.registry

    def registry(self):
        assert self.cfg.page_limit == 1000
        original(self)

    monkeypatch.setattr(Engine, "registry", registry)
    assert main() == 0
    monkeypatch.setattr(sys, "argv", ["job", "--page-limit", "1001"])
    assert main() == 1
