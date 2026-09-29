"""Execute shell wrapper only with a fake Python command: zero cloud calls."""

import os
import subprocess
from pathlib import Path

import pytest

WRAPPER = Path("scripts/analytics_dry_runs.sh").resolve()


@pytest.mark.parametrize("failure", ["none", "python", "tee"])
def test_pipeline_status_and_seven_models(tmp_path, failure):
    fake_python = tmp_path / "python-fake"
    fake_python.write_text("""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$CALLS"
model=unknown
while (( $# > 0 )); do
  if [[ "$1" == --model ]]; then model="$2"; shift; fi
  shift
done
printf 'synthetic result for %s\\n' "$model"
if [[ "$FAILURE" == python && "$model" != analytics_funnel_daily ]]; then
  printf 'synthetic query failure\\n' >&2
  exit 17
fi
exit 0
""")
    fake_python.chmod(0o700)
    env = os.environ | {
        "PYTHON_BIN": str(fake_python),
        "CALLS": str(tmp_path / "calls"),
        "FAILURE": failure,
        "ANALYTICS_VALIDATION_DIR": str(tmp_path / "results"),
    }
    if failure == "tee":
        tee = tmp_path / "tee"
        tee.write_text("#!/usr/bin/env bash\ncat\nexit 9\n")
        tee.chmod(0o700)
        env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    result = subprocess.run(["bash", str(WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == {"none": 0, "python": 17, "tee": 9}[failure]
    calls = (tmp_path / "calls").read_text().splitlines()
    assert len(calls) == 7
    assert all(
        "src.analytics.parity dry-run" in c and "--confirm-project up-data-intelligence-dev" in c
        for c in calls
    )
    summary = (tmp_path / "results/dry-run-summary.tsv").read_text().splitlines()
    assert len(summary) == 8
    if failure == "python":
        assert all(line.endswith("\t17\t0\tFALHOU") for line in summary[1:7])
        assert summary[7].endswith("\t0\t0\tPASSOU")
        assert (
            "synthetic query failure"
            in (tmp_path / "results/analytics_store_daily.log").read_text()
        )
    elif failure == "tee":
        assert all(line.endswith("\t0\t9\tFALHOU") for line in summary[1:])
    else:
        assert all(line.endswith("\t0\t0\tPASSOU") for line in summary[1:])


def test_refuses_source_without_terminating_parent_shell():
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; rc=$?; printf "parent-alive:%s" "$rc"', "test", str(WRAPPER)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "parent-alive:2" in result.stdout
