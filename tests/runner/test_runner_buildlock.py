"""The build lock on the server side: the turn env that installs the shims, and checks that queue untimed."""

from __future__ import annotations

import fcntl
import os
import subprocess
import threading
from typing import TYPE_CHECKING

import pytest
from runnerfakes import Env
from todoimpl.runner import buildlock, cardslice, checks, claude

if TYPE_CHECKING:
    from pathlib import Path


def _hold_for(seconds: float, holder: str | None) -> None:
    """Take the lock now, as another build would, and let it go after `seconds`."""
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    if holder is not None:
        (base / buildlock.HOLDER).write_text(holder)
    lock = (base / buildlock.LOCK).open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    timer = threading.Timer(seconds, lock.close)
    timer.daemon = True
    timer.start()


def test_turn_env_points_claude_at_an_env_file_that_puts_the_shims_first(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(buildlock.HELD_VAR, "1")  # a server started under a held lock must not pass it on
    (tmp_path / "card1").mkdir()
    env = claude.build("implement", "go", tmp_path / "card1" / "wt").env
    assert buildlock.HELD_VAR not in env
    assert env[buildlock.CARD_VAR] == "card1"
    assert env["GRADLE_OPTS"] == buildlock.TUNING["GRADLE_OPTS"]
    assert env["CARGO_BUILD_JOBS"] == "4"
    assert "MAKEFLAGS" not in buildlock.TUNING  # make defaults to one job; -j4 would raise it
    shims = buildlock.root() / buildlock.SHIM_DIR
    tools = (*buildlock.TOOLS, *buildlock.GUARDS, cardslice.SHIM)  # the slice shim rides along (T2401)
    assert sorted(p.name for p in shims.iterdir()) == sorted(tools)
    assert all(os.access(shims / t, os.X_OK) for t in tools)
    script = f'PATH=/usr/bin:{shims}:/bin; . "$1"; . "$1"; echo "$PATH"'
    path = subprocess.run(
        ["bash", "-c", script, "_", env["CLAUDE_ENV_FILE"]], capture_output=True, text=True, check=True
    )
    assert path.stdout == f"{shims}:/usr/bin:{shims}:/bin\n"


def test_ensure_leaves_unchanged_files_alone(tmp_path: Path) -> None:
    shims = buildlock.ensure(tmp_path)
    before = (shims / "make").stat().st_ino
    buildlock.ensure(tmp_path)
    assert (shims / "make").stat().st_ino == before


def test_a_check_waits_for_the_lock_outside_its_timeout(world: Env, tmp_path: Path) -> None:
    run_dir = tmp_path / "card9"
    _hold_for(0.8, "card-x (make test) since 12:00")
    result = checks.run_check("tests", 'echo "held=$TODOIMPL_BUILD_LOCK_HELD"', tmp_path, run_dir, 0.5)
    assert result.passed
    log = (run_dir / result.log).read_text()
    assert log.startswith("waiting for build lock held by card-x (make test) since 12:00; 0 ahead\n")
    assert "held=1" in log
    assert (buildlock.root() / buildlock.HOLDER).read_text() == ""


def test_a_check_without_a_log_waits_too(world: Env, tmp_path: Path) -> None:
    _hold_for(0.4, None)
    assert checks.run_capped("true", tmp_path, 0.3) == 0


def test_a_check_under_a_held_lock_runs_at_once(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(buildlock.HELD_VAR, "1")
    _hold_for(30, None)
    assert checks.run_capped("true", tmp_path, 5) == 0


def test_the_lock_defaults_to_the_run_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(buildlock.ROOT_VAR)
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path))
    assert buildlock.root() == tmp_path
