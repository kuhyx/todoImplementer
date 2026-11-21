"""A passing test run leaves (almost) nothing in pytest's basetemp (T2412)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIMIT = 60  # session-wide fixtures only (shim dirs, git templates); a test dir or scratch dir is a leak


def test_t2412_a_green_run_leaves_few_files_in_its_basetemp(tmp_path: Path) -> None:
    # A parallel run of 6000 tests once left 190k files in /tmp/pytest-of-*, filling the inode table: every
    # autouse fixture made its own dir per test and every passing test kept its tmp_path.
    base = tmp_path / "bt"
    argv = [sys.executable, "-m", "pytest", "tests/usage", "tests/credits", "--no-cov", "-q"]
    run = subprocess.run(
        [*argv, f"--basetemp={base}", "-p", "no:cacheprovider"],
        cwd=REPO,
        env={k: v for k, v in os.environ.items() if k != "TODOIMPL_TEST_SHARD"},  # the whole set, not a shard
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout[-2000:]
    left = sum(1 for _ in base.rglob("*"))
    assert left <= LIMIT, f"{left} files left in the basetemp of a green run"


def test_t2435_the_footprint_run_drops_the_shard_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Under `make test-shard` the inner run must see the whole set, never an empty shard (pytest exit 5)."""
    monkeypatch.setenv("TODOIMPL_TEST_SHARD", "999/1000")  # a shard with no usage or credits file
    test_t2412_a_green_run_leaves_few_files_in_its_basetemp(tmp_path)
