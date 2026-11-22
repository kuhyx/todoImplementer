"""`make test` runs the suite as its shards, one build ticket each, so no ticket holds a slot 60 s (T2487).

2026-11-22: one `uv run ... pytest` for the whole suite held a build slot 75 s (`heavy-uv-env`), and the
pre-commit fallback to `make test` did the same.
"""

import subprocess
from pathlib import Path

from test_makefile_coverage import copy_make, make_env


def test_t2487_make_test_runs_one_capped_pytest_per_shard(tmp_path: Path) -> None:
    copy_make(tmp_path)
    log = tmp_path / "capped.log"
    cap = f"TESTCAP=tee -a {log} >/dev/null <<< x; env"  # one `x` per capped pytest run
    argv = ["make", "-s", "-C", str(tmp_path), "test", cap, "UV=env"]
    env = {**make_env(), "FAKECOV_SLEEP": "0"}
    run = subprocess.run(argv, env=env, capture_output=True, text=True, check=False, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "chunks 6 of 6" in run.stdout
    assert log.read_text().count("x") == 6  # six capped pytest runs: six tickets
