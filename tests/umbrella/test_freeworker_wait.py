"""`freeworker wait`: code, not the manager's model, waits for the workers of a round."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import pytest
from todoimpl.prompts import PromptContext, build
from todoimpl.runner import freeworker, workerwait


def finished(log: Path, code: int, text: str = "") -> None:
    log.write_text(text, encoding="utf-8")
    workerwait.mark_exit(log, code)


def test_t1898_a_worker_leaves_its_exit_code_beside_its_log(tmp_path: Path) -> None:
    log = tmp_path / "w1.log"
    workerwait.mark_exit(log, 0)
    assert workerwait.exit_of(log) == 0
    workerwait.mark_exit(log, 3)
    assert workerwait.exit_of(log) == 3
    assert workerwait.exit_of(tmp_path / "other.log") is None


def test_t1898_a_worker_started_again_on_its_log_drops_the_old_exit_record(tmp_path: Path) -> None:
    log = tmp_path / "w.log"
    workerwait.mark_exit(log, 0)
    workerwait.mark_started(log)
    assert workerwait.exit_of(log) is None


def test_t1898_wait_returns_one_compact_line_per_worker_once_all_have_exited(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = tmp_path / "a.log", tmp_path / "b.log"
    finished(a, 0, "Warning: startup\nedited the files\n")
    finished(b, 3, "No changes needed.\n")
    assert freeworker.main(["wait", str(a), str(b), "--timeout", "5"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"{a.name}: exit=0 edited the files"
    assert out[1] == f"{b.name}: exit=3 No changes needed."
    assert out[-1] == "all 2 workers finished"


def test_t1898_wait_reports_the_workers_still_running_when_its_time_is_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    done, slow = tmp_path / "done.log", tmp_path / "slow.log"
    finished(done, 0)
    workerwait.mark_started(slow)  # this very process stands in for a worker that is still alive
    started = time.monotonic()
    assert freeworker.main(["wait", str(done), str(slow), "--timeout", "0.3"]) == workerwait.STILL_RUNNING
    assert time.monotonic() - started < 5
    out = capsys.readouterr().out
    assert f"{slow.name}: running" in out
    assert "1 of 2 still running: call wait again" in out


def test_t1898_a_worker_that_died_without_an_exit_record_is_lost_not_waited_for(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "gone.log"
    dead = subprocess.Popen(["true"])
    dead.wait()
    (tmp_path / "gone.log.pid").write_text(str(dead.pid), encoding="utf-8")
    assert freeworker.main(["wait", str(log), "--timeout", "5"]) == 0
    assert f"{log.name}: lost" in capsys.readouterr().out


def test_t1898_a_worker_that_has_not_started_yet_is_waited_for_only_for_a_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "later.log"  # no pid file and no exit record: the worker may still come up
    assert workerwait.wait([log], timeout=0.2, poll=0.05) == {log: "running"}
    monkeypatch.setattr(workerwait, "START_GRACE", 0.1)  # a typo in the command: it never starts
    assert freeworker.main(["wait", str(log), "--timeout", "5"]) == 0
    assert f"{log.name}: not started" in capsys.readouterr().out


def test_t1898_wait_wakes_as_soon_as_the_last_worker_exits(tmp_path: Path) -> None:
    log = tmp_path / "w.log"
    workerwait.mark_started(log)
    threading.Timer(0.3, workerwait.mark_exit, args=(log, 0)).start()
    started = time.monotonic()
    assert workerwait.wait([log], timeout=10, poll=0.05) == {}
    assert time.monotonic() - started < 5


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "wt"
    repo.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@x"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (tmp_path / "p.md").write_text("task", encoding="utf-8")
    return repo


def test_t1898_a_worker_without_its_tool_still_leaves_an_exit_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "no-bin"))  # no claude-free: nothing real is ever started
    log = tmp_path / "w.log"
    assert freeworker.main([str(repo), str(tmp_path / "p.md"), str(log)]) == freeworker.NO_TOOL
    assert workerwait.exit_of(log) == freeworker.NO_TOOL
    assert not Path(f"{log}.pid").exists()


def test_t1898_a_worker_that_edits_leaves_exit_zero_and_a_pid_only_while_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shim = tmp_path / "bin" / "claude-free"
    shim.parent.mkdir()
    shim.write_text('#!/bin/sh\ntest -f "$PIDFILE" && cp "$PIDFILE" seen-pid\necho edited > made.txt\n')
    shim.chmod(0o755)
    log = tmp_path / "w.log"
    monkeypatch.setenv("PATH", f"{shim.parent}:/usr/bin:/bin")
    monkeypatch.setenv("PIDFILE", f"{log}.pid")
    repo = _git_repo(tmp_path)
    assert freeworker.main([str(repo), str(tmp_path / "p.md"), str(log)]) == 0
    assert workerwait.exit_of(log) == 0
    assert (repo / "seen-pid").read_text(encoding="utf-8") == str(os.getpid())  # alive while claude-free ran
    assert not Path(f"{log}.pid").exists()


def test_t1898_the_manager_prompt_waits_with_one_command_not_with_polling() -> None:
    ctx = PromptContext("t", "b", "kuhyx/x", Path("/wt"), Path("/run"))
    text = build("manager", ctx)
    assert "wait <log>" in text
    assert "timeout set to 600000" in text
    assert "sleep loop" in text  # named as forbidden
    assert "never use Monitor" in text
    assert "never end your turn" in text
