"""`make test` keeps its coverage data per run: two runs in one worktree cannot clobber it (T1920)."""

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAKES = REPO / "tests" / "fixtures" / "fakecov"
CHUNKS = "a b c"


def make_env() -> dict[str, str]:
    """Fake pytest/coverage first on PATH; a board build-lock shim on PATH runs `make` at once (T2002)."""
    env = {**os.environ, "PATH": f"{FAKES}:{os.environ['PATH']}", "FAKECOV_CHUNKS": "3", "MAKEFLAGS": ""}
    return {**env, "TODOIMPL_BUILD_LOCK_HELD": "1"}


def make_test(cwd: Path) -> subprocess.Popen[str]:
    """Start the real `test` recipe in cwd with fake pytest/coverage and no capped.sh (UV is plain `env`)."""
    shutil.copy(REPO / "Makefile", cwd / "Makefile")  # its sub-makes read ./Makefile
    env = make_env()
    argv = ["make", "-s", "-C", str(cwd), "test", f"CHUNKS={CHUNKS}", "UV=env"]
    return subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_t1920_two_overlapping_make_test_runs_both_see_all_their_chunks(tmp_path: Path) -> None:
    # The board restarted mid-check and ran `make test` again while the old one still ran (16:50, 49-53 %).
    first = make_test(tmp_path)
    second = make_test(tmp_path)
    outs = [p.communicate(timeout=30)[0] for p in (first, second)]
    assert [first.returncode, second.returncode] == [0, 0], outs
    assert all("chunks 3 of 3" in out for out in outs), outs


def test_a_run_leaves_no_coverage_data_in_the_worktree(tmp_path: Path) -> None:
    run = make_test(tmp_path)
    out = run.communicate(timeout=30)[0]
    assert run.returncode == 0, out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Makefile"]


def test_t2002_the_fake_make_runs_never_wait_on_the_board_build_lock() -> None:
    # Board gate run: the inner `make` went through the build-lock shim and waited 30 s on another card.
    assert make_env()["TODOIMPL_BUILD_LOCK_HELD"] == "1"
