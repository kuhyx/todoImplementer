"""A turn's wall clock stands still while its only live work waits on the build lock (T2270)."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import pytest
from launchfakes import STEM, invoke, rig
from runnerfakes import Env
from todoimpl.runner import bgwait, buildlock, claude, files, launch, orphans, turnclock, turnhost

if TYPE_CHECKING:
    from pathlib import Path

LOCKED = {"lock": True, "who": "f00dcafe-0", "since": 1.0}


def test_t2270_the_invocation_names_the_build_lock(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(buildlock.ROOT_VAR, str(tmp_path / "locks"))
    _, inv = rig(world, tmp_path)
    assert json.loads(launch._invocation(inv))["lock"] == str(tmp_path / "locks" / buildlock.LOCK)


def test_t2270_a_turn_waiting_on_the_build_lock_outlives_its_limit(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(launch.TIMEOUT_VAR, "0.5")
    monkeypatch.setattr(turnclock, "LOOK_EVERY", 0.1)
    seen: list[Any] = []

    def scan(pid: int | None, run_dir: Path, lock: Path) -> dict[str, Any]:
        seen.append((pid, run_dir, lock))
        return LOCKED

    monkeypatch.setattr(bgwait, "scan", scan)
    run_dir, inv = rig(world, tmp_path)
    queued = claude.Invocation(("sh", "-c", "sleep 1.5"), inv.env, inv.cwd)  # silent: it waits on the lock
    orphans.begin(run_dir, STEM, "implement", None)
    invoke(run_dir, queued)
    turnhost.run(run_dir, STEM, turnhost.Stop())
    done = files.read_json(run_dir / f"{STEM}.exit.json")
    assert done["code"] == 0
    assert "timeout" not in done
    assert seen
    assert seen[0][1] == run_dir
    assert seen[0][2] == buildlock.root() / buildlock.LOCK


def test_t2270_the_clock_runs_while_the_stream_grows_or_no_lock_wait_is_found() -> None:
    found: list[bool] = [True]
    clock = turnclock.Deadline(10.0, 0.0, lambda: found[0])
    assert not clock.passed(0.5)  # no look within LOOK_EVERY
    assert not clock.passed(9.0)  # waited 0..9 on the lock: the deadline moves to 19
    assert clock.at == 19.0
    found[0] = False
    assert not clock.passed(18.0)
    assert clock.passed(19.0)
    assert not turnclock.Deadline(None, 0.0, lambda: False).passed(1e9)


def test_t2270_lock_wait_needs_a_silent_stream_and_a_lock_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = tmp_path / "s.jsonl"
    answers: list[dict[str, Any] | None] = [
        LOCKED,
        {"lock": False, "who": "sleep 9", "since": 1.0},
        None,
        LOCKED,
    ]
    monkeypatch.setattr(bgwait, "scan", lambda *_a: answers.pop(0))
    wait = turnclock.LockWait(42, tmp_path, tmp_path / "build.lock", stream)  # no stream yet: size 0
    assert not turnclock.LockWait(42, tmp_path, None, stream)()  # no lock named: never a lock wait
    assert wait()
    assert not wait()  # a job runs, but not on the lock
    assert not wait()  # nothing runs
    stream.write_text("{}\n", encoding="utf-8")
    assert not wait()  # claude spoke since the last look: it works
    assert answers == [LOCKED]  # a growing stream needs no /proc look
    assert wait()


def test_t2270_a_host_from_an_older_server_has_no_lock_to_watch(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(launch.TIMEOUT_VAR, "0.3")
    monkeypatch.setattr(bgwait, "scan", lambda *_a: pytest.fail("no lock named: nothing to scan"))
    run_dir, inv = rig(world, tmp_path)
    slow = claude.Invocation(("sh", "-c", "sleep 30"), inv.env, inv.cwd)
    orphans.begin(run_dir, STEM, "implement", None)
    body = json.loads(launch._invocation(slow))
    body.pop("lock")
    launch._write_private(run_dir / f"{STEM}.invoke.json", json.dumps(body))
    started = time.monotonic()
    turnhost.run(run_dir, STEM, turnhost.Stop())
    assert time.monotonic() - started < 10
    assert files.read_json(run_dir / f"{STEM}.exit.json")["timeout"] is True
