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
