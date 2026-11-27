"""`make test` runs the suite as its shards, one build ticket each, so no ticket holds a slot 60 s (T2487).

2026-11-22: one `uv run ... pytest` for the whole suite held a build slot 75 s (`heavy-uv-env`), and the
pre-commit fallback to `make test` did the same.
"""

import shutil
import subprocess
from pathlib import Path

from test_makefile_coverage import REPO, SHARDS, copy_make, make_env


def test_t2487_make_test_runs_one_capped_pytest_per_shard(tmp_path: Path) -> None:
    copy_make(tmp_path)
    log = tmp_path / "capped.log"
    cap = f"TESTCAP=tee -a {log} >/dev/null <<< x; env"  # one `x` per capped pytest run
    argv = ["make", "-s", "-C", str(tmp_path), "test", cap, "UV=env"]
    env = {**make_env(), "FAKECOV_SLEEP": "0"}
    run = subprocess.run(argv, env=env, capture_output=True, text=True, check=False, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert f"chunks {SHARDS} of {SHARDS}" in run.stdout
    assert log.read_text().count("x") == int(SHARDS)  # one capped pytest run (one ticket) per shard


def test_t2496_a_failing_shard_exits_non_zero_and_is_not_stamped(tmp_path: Path) -> None:
    # A failed shard ran `&& [[ -z k ]] || fast_stamp.py mark`: the mark branch exited 0 and stamped it green.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=30)
    copy_make(tmp_path)
    shutil.copy(REPO / "scripts" / "fast_stamp.py", tmp_path / "scripts" / "fast_stamp.py")
    argv = ["make", "-s", "-C", str(tmp_path), "test-shard", "SHARD=1", f"COV_DIR={tmp_path / 'cov'}"]
    env = {**make_env(), "FAKECOV_SLEEP": "0", "FAKECOV_FAIL": "1"}
    run = subprocess.run(
        [*argv, "TESTCAP=env", "UV=env"], env=env, capture_output=True, text=True, check=False, timeout=30
    )
    assert run.returncode != 0, run.stdout + run.stderr
