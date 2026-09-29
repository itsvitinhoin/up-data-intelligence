"""Offline evaluation of the Git-compatible rules used by .gcloudignore."""

import subprocess
from pathlib import Path


def test_cloud_build_includes_only_approved_config_policy(tmp_path):
    rules = Path(".gcloudignore").read_text()
    # No SDK-specific includes: Git can evaluate this allowlist without running gcloud.
    assert "#!include:" not in rules
    (tmp_path / ".gitignore").write_text(rules)
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    approved = "config/analytics/mx-fashion.dev.json"
    excluded = [
        "config/other.json",
        "config/.env",
        "config/credentials.json",
        "config/analytics/other.dev.json",
        "config/analytics/mx-fashion.prod.json",
        "config/analytics/mx-fashion.dev.json.bak",
        "config/analytics/nested/mx-fashion.dev.json",
        "config/other/mx-fashion.dev.json",
    ]
    for name in [approved, *excluded]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic packaging fixture\n")
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.excludesFile=/dev/null",
                "check-ignore",
                "--no-index",
                "--quiet",
                name,
            ],
            cwd=tmp_path,
            check=False,
        )
        assert result.returncode == (0 if name in excluded else 1), name
    assert Path(approved).is_file()
