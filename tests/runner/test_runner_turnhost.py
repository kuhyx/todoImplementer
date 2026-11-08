"""The turn host, run in-process: stream and exit record, bad invocations, stop handling, main."""

from __future__ import annotations

import json
import os
import runpy
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from launchfakes import STEM
from launchfakes import invoke as _invoke
from launchfakes import rig as _rig
from runnerfakes import Env
from schedfakes import wait
from todoimpl.runner import claude, files, orphans, turnhost


def test_host_runs_claude_into_the_stream_file_and_records_how_it_ended(world: Env, tmp_path: Path) -> None:
    run_dir, inv = _rig(world, tmp_path)
    orphans.begin(run_dir, STEM, "implement", None)
    _invoke(run_dir, inv)
    assert turnhost.run(run_dir, STEM, turnhost.Stop()) == 0
    stream = (run_dir / f"{STEM}.stream.jsonl").read_text(encoding="utf-8")
    assert '"type": "result"' in stream
    done = files.read_json(run_dir / f"{STEM}.exit.json")
    rec = orphans.read(run_dir)
    assert rec is not None
    assert done["code"] == 0
    assert done["pid"] == rec.pid
    assert rec.host_pid == os.getpid()
    assert (run_dir / f"{STEM}.stderr.log").exists()
    assert not (run_dir / f"{STEM}.invoke.json").exists()


def test_a_host_the_server_gave_up_on_does_not_start_claude_beside_its_successor(
    world: Env, tmp_path: Path
) -> None:
    run_dir, inv = _rig(world, tmp_path)
    orphans.begin(run_dir, "implement-2.000", "implement", None)  # the replacement turn owns the record
    _invoke(run_dir, inv)
    turnhost.run(run_dir, STEM, turnhost.Stop())
    assert files.read_json(run_dir / f"{STEM}.exit.json")["code"] == turnhost.SUPERSEDED
    assert world.calls() == []
    assert (orphans.read(run_dir) or orphans.Record()).stem == "implement-2.000"  # its record is untouched
    (run_dir / orphans.RECORD).unlink()
    _invoke(run_dir, inv)  # no record at all: the turn was consumed or abandoned meanwhile
    (run_dir / f"{STEM}.exit.json").unlink()
    turnhost.run(run_dir, STEM, turnhost.Stop())
    assert files.read_json(run_dir / f"{STEM}.exit.json")["code"] == turnhost.SUPERSEDED


def test_host_without_a_usable_invocation_records_a_failed_turn(tmp_path: Path) -> None:
    assert turnhost.run(tmp_path, STEM, turnhost.Stop()) == 0
    done = files.read_json(tmp_path / f"{STEM}.exit.json")
    assert done["code"] == turnhost.BAD_INVOCATION
    assert "invocation" in done["error"]


def test_host_records_a_claude_that_cannot_be_started(world: Env, tmp_path: Path) -> None:
    run_dir, inv = _rig(world, tmp_path)
    broken = claude.Invocation((str(tmp_path / "no-such-claude"),), inv.env, inv.cwd)
    orphans.begin(run_dir, STEM, "implement", None)
    _invoke(run_dir, broken)
    turnhost.run(run_dir, STEM, turnhost.Stop())
    done = files.read_json(run_dir / f"{STEM}.exit.json")
    assert done["code"] == turnhost.SPAWN_FAILED
    assert "no-such-claude" in done["error"]


def _spawn(script: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(["sh", "-c", script], start_new_session=True)


def test_stop_handler_passes_sigterm_once_and_escalates_only_after_the_grace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stop = turnhost.Stop()
    stop(signal.SIGTERM, None)  # no claude yet: nothing to pass on
    assert stop.at is None
    stop.escalate()
    ready = tmp_path / "ready"
    proc = _spawn(f"trap '' TERM; touch {ready}; while :; do sleep 0.05; done")
    try:
        wait(ready.exists)  # the trap is set once the file exists
        stop.proc = proc
        stop.escalate()  # nothing was signalled yet
        stop(signal.SIGTERM, None)
        first = stop.at
        stop(signal.SIGTERM, None)
        assert stop.at == first  # only the first signal counts
        stop.escalate()  # still inside the grace
        assert proc.poll() is None
        monkeypatch.setattr(turnhost, "GRACE", 0.0)
        stop.escalate()
        assert proc.wait(timeout=10) == -signal.SIGKILL
    finally:
        proc.kill()
        proc.wait()


def test_a_stopped_host_still_writes_an_exit_record_even_for_a_claude_that_ignores_sigterm(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(turnhost, "GRACE", 0.2)
    monkeypatch.setattr(turnhost, "TICK", 0.05)
    run_dir, inv = _rig(world, tmp_path)
    ready = tmp_path / "ready"
    script = f"trap '' TERM; touch {ready}; while :; do sleep 0.05; done"
    stubborn = claude.Invocation(("sh", "-c", script), inv.env, inv.cwd)
    orphans.begin(run_dir, STEM, "implement", None)
    _invoke(run_dir, stubborn)
    stop = turnhost.Stop()
    host = threading.Thread(target=turnhost.run, args=(run_dir, STEM, stop))
    host.start()
    wait(ready.exists)
    stop(signal.SIGTERM, None)
    host.join(timeout=15)
    assert not host.is_alive()
    assert files.read_json(run_dir / f"{STEM}.exit.json")["code"] == -signal.SIGKILL


def test_main_installs_the_handlers_and_runs_the_named_turn(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, inv = _rig(world, tmp_path)
    handlers: dict[int, Any] = {}

    def install(num: int, handler: Any) -> None:
        handlers[num] = handler

    monkeypatch.setattr(signal, "signal", install)
    orphans.begin(run_dir, STEM, "implement", None)
    _invoke(run_dir, inv)
    assert turnhost.main([str(run_dir), STEM]) == 0
    assert set(handlers) == {signal.SIGTERM, signal.SIGINT}
    assert files.read_json(run_dir / f"{STEM}.exit.json")["code"] == 0
    (run_dir / f"{STEM}.exit.json").unlink()
    _invoke(run_dir, inv)
    monkeypatch.setattr(sys, "argv", ["turnhost", str(run_dir), STEM])
    assert turnhost.main() == 0
    assert files.read_json(run_dir / f"{STEM}.exit.json")["code"] == 0


def test_t1817_module_entry_point_runs_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["turnhost", str(tmp_path), "s1"])
    monkeypatch.delitem(sys.modules, "todoimpl.runner.turnhost")
    with pytest.raises(SystemExit) as done:
        runpy.run_module("todoimpl.runner.turnhost", run_name="__main__", alter_sys=False)
    assert done.value.code == 0
    record = json.loads((tmp_path / "s1.exit.json").read_text(encoding="utf-8"))
    assert record["code"] == turnhost.BAD_INVOCATION
