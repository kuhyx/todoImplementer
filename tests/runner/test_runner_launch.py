"""The launcher: systemd-run argv, direct host, stopping a turn by its unit or its process group."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from launchfakes import STEM
from launchfakes import calls as _calls
from launchfakes import gone as _gone
from launchfakes import rig as _rig
from runnerfakes import Env
from schedfakes import wait
from todoimpl.runner import files, launch, orphans


def test_t1817_production_launch_is_a_systemd_unit_with_the_env_only_in_a_private_file(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(launch.LAUNCH_VAR)
    seen = _calls(monkeypatch)
    run_dir, inv = _rig(world, tmp_path)
    rec = launch.start(run_dir, STEM, "implement", inv)
    unit = "todoimpl-turn-abcd1234-0-implement-1.000"
    assert seen == [
        [
            "systemd-run", "--user", "--collect", "--quiet", f"--unit={unit}",
            "-p", "KillMode=control-group", "-p", "TimeoutStopSec=10",
            "-E", f"PYTHONPATH={launch.SERVER_DIR}",
            "--", sys.executable, "-m", "todoimpl.runner.turnhost", str(run_dir), STEM,
        ]
    ]  # fmt: skip
    assert (rec.unit, rec.stem, rec.role) == (unit, STEM, "implement")
    assert orphans.read(run_dir) == rec
    invoke = run_dir / f"{STEM}.invoke.json"
    assert invoke.stat().st_mode & 0o777 == 0o600
    body = json.loads(invoke.read_text(encoding="utf-8"))
    assert body["argv"] == list(inv.argv)
    assert body["cwd"] == str(inv.cwd)
    assert body["env"]["CLAUDE_AUTO_CONTINUE"] == "0"
    assert not any("CLAUDE_AUTO_CONTINUE" in part for part in seen[0])  # the env never rides in argv


def test_a_unit_that_cannot_start_is_reported_and_leaves_no_secret_behind(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(launch.LAUNCH_VAR)
    _calls(monkeypatch, code=1, err="Failed to connect to bus\n")
    run_dir, inv = _rig(world, tmp_path)
    with pytest.raises(files.NeedsYouError, match=r"could not start the turn unit .*Failed to connect"):
        launch.start(run_dir, STEM, "implement", inv)
    assert not (run_dir / f"{STEM}.invoke.json").exists()
    assert orphans.read(run_dir) is None


def test_unit_names_keep_only_what_systemd_allows() -> None:
    assert launch.unit_name("abcd1234-0", "plan-1.5 x/y") == "todoimpl-turn-abcd1234-0-plan-1.5_x_y"


def test_stopping_a_unit_turn_runs_systemctl_stop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen = _calls(monkeypatch)
    rec = orphans.Record(stem=STEM, role="plan", unit="todoimpl-turn-x")
    launch.handle_for(tmp_path, rec).stop()
    assert seen == [["systemctl", "--user", "stop", "todoimpl-turn-x"]]


def test_t1817_a_direct_launch_runs_claude_detached_and_stop_kills_its_whole_group(
    world: Env, tmp_path: Path
) -> None:
    pidfile = tmp_path / "grandchild.pid"
    world.script(
        "abcd1234", {"_fake": "spawn_sleeper", "pidfile": str(pidfile)}, {"_fake": "sleep", "sec": 30}
    )
    run_dir, inv = _rig(world, tmp_path)
    rec = launch.start(run_dir, STEM, "implement", inv)
    assert rec.unit is None
    wait(pidfile.exists)
    grandchild = int(pidfile.read_text(encoding="utf-8"))
    live = orphans.read(run_dir)
    assert live is not None
    assert live.pid is not None
    assert os.getpgid(grandchild) == live.pid  # claude leads its own group, apart from the host's
    assert live.host_pid is not None
    assert os.getpgid(live.host_pid) != live.pid
    launch.handle_for(run_dir, live).stop(grace=2.0)
    wait(lambda: files.read_json(run_dir / f"{STEM}.exit.json") is not None)
    wait(lambda: _gone(grandchild))
    assert files.read_json(run_dir / f"{STEM}.exit.json")["code"] == -signal.SIGTERM
    assert not (run_dir / f"{STEM}.invoke.json").exists()


def test_stop_before_the_host_recorded_claude_waits_a_moment_then_gives_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launch, "START_WAIT", 0.1)
    rec = orphans.begin(tmp_path, STEM, "plan", None)
    launch.handle_for(tmp_path, rec).stop()  # no pid ever arrives: nothing to signal, no hang
    (tmp_path / orphans.RECORD).unlink()
    launch.handle_for(tmp_path, rec).stop()  # the record is gone: nothing to do either


def test_a_failed_unit_stop_falls_back_to_the_recorded_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _calls(monkeypatch, code=5)
    mine = subprocess.Popen(["sleep", "30"], start_new_session=True)
    orphans.begin(tmp_path, STEM, "plan", "todoimpl-turn-x")
    orphans.write(tmp_path, pid=mine.pid, start=orphans.start_of(mine.pid))
    rec = orphans.read(tmp_path)
    assert rec is not None
    launch.handle_for(tmp_path, rec).stop(grace=1.0)
    assert mine.wait(timeout=10) == -signal.SIGTERM
    assert seen == [["systemctl", "--user", "stop", "todoimpl-turn-x"]]
