"""Stopping a dead wait, units beside the turn, and the waits that must never count as dead (T2195-T2197)."""

from __future__ import annotations

import os
import signal
from typing import TYPE_CHECKING

import pytest
from procfakes import CLAUDE, SHELL, SLEEP, Clock, Proc, card_dir, fake, judge_of, wrapped
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import bgwait, deadwait

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Proc:
    return fake(tmp_path, monkeypatch)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return card_dir(tmp_path)


def test_t2197_a_card_unit_outside_claude_is_judged_and_stopped_as_a_unit(
    proc: Proc, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slice_dir = tmp_path / "cgroup" / "user.slice" / "todoimpl.slice"
    (slice_dir / "run-u7.service").mkdir(parents=True)
    (slice_dir / "run-u7.service" / "cgroup.procs").write_text("800\n")
    (slice_dir / "todoimpl-turn-bcf6a474-0-x.service").mkdir()
    (slice_dir / "todoimpl-turn-bcf6a474-0-x.service" / "cgroup.procs").write_text(f"{CLAUDE}\n")
    (slice_dir / "run-u8.service").mkdir()
    (slice_dir / "run-u8.service" / "cgroup.procs").write_text("900\n")  # another card's job
    proc.add(CLAUDE, "claude", cgroup="/user.slice/todoimpl.slice/todoimpl-turn-bcf6a474-0-x.service")
    proc.add(800, "bash", cmd="bash\0b11.sh\0", wchan="anon_pipe_read")
    (proc.root / "800" / "environ").write_text("TODOIMPL_BUILD_CARD=bcf6a474-0\0")
    proc.add(900, "bash", cmd="bash\0other.sh\0", wchan="anon_pipe_read")
    clock = Clock()
    judge = judge_of(run_dir, clock)
    judge.look(CLAUDE)
    clock.now += deadwait.STILL
    (found,) = judge.look(CLAUDE)
    assert found.job is not None
    assert (found.verdict, found.rule, found.job.unit) == (deadwait.DEAD, "deadlock", "run-u7.service")
    stopped: list[str] = []
    monkeypatch.setattr(deadwait, "STOP_UNIT", stopped.append)
    deadwait.stop(found, "(runner) killed\n")
    assert stopped == ["run-u7.service"]


def test_t2196_stopping_a_dead_job_tells_its_output_and_kills_only_pids_that_are_still_it(
    proc: Proc, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc.add(SHELL, "bash", ppid=CLAUDE, kids=(SLEEP,), cmd="bash\0b11.sh\0", wchan="anon_pipe_read")
    proc.add(SLEEP, "cat", ppid=SHELL, wchan="anon_pipe_read")
    clock = Clock()
    judge = judge_of(run_dir, clock)
    judge.look(CLAUDE)
    clock.now += deadwait.STILL
    (found,) = judge.look(CLAUDE)
    proc.add(SLEEP, "cat", ppid=SHELL, wchan="anon_pipe_read", start=77)  # the pid was reused since
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(deadwait, "KILL", lambda pid, sig: killed.append((pid, sig)))
    deadwait.stop(found, "(runner) killed your dead wait\n")
    assert killed == [(SHELL, signal.SIGTERM)]
    assert (proc.root / str(SHELL) / "fd" / "2").read_text() == "(runner) killed your dead wait\n"


def test_no_job_and_a_vanished_shell_give_no_verdict(proc: Proc, run_dir: Path) -> None:
    assert judge_of(run_dir).look(CLAUDE) == []
    assert judge_of(run_dir).look(None) == []
    assert deadwait.overall([]).verdict == deadwait.UNKNOWN


def test_t2196_a_job_with_no_output_left_or_a_full_pipe_is_still_stopped(
    proc: Proc, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc.add(SHELL, "bash", ppid=CLAUDE)
    job = deadwait.Job(SHELL, (SHELL,), (bgwait.started(SHELL),))
    killed: list[int] = []
    monkeypatch.setattr(deadwait, "KILL", lambda pid, _sig: killed.append(pid))
    deadwait.stop(deadwait.Verdict(deadwait.DEAD, "deadlock", "x"), "note\n")  # no job: nothing to stop
    (proc.root / str(SHELL) / "fd" / "2").unlink()
    deadwait.stop(deadwait.Verdict(deadwait.DEAD, "deadlock", "x", job), "note\n")
    (proc.root / str(SHELL) / "fd" / "2").touch()

    def full(_fd: int, _data: bytes) -> int:
        raise BlockingIOError

    monkeypatch.setattr(os, "write", full)
    deadwait.stop(deadwait.Verdict(deadwait.DEAD, "deadlock", "x", job), "note\n")
    assert killed == [SHELL, SHELL]


def test_t2195_a_one_off_pgrep_or_a_card_id_in_a_job_that_waits_on_the_network_is_never_dead(
    proc: Proc, run_dir: Path
) -> None:
    store.save(run_dir.parent / "c96b7ce5-0", RunState(task_id="c96b7ce5-0", stage="shipped"))
    for script, kid in (
        ("pgrep -f foo || start_it; curl -o x https://h/x", "curl"),
        ("deploy c96b7ce5", "python"),
    ):
        proc.add(SHELL, "zsh", ppid=CLAUDE, kids=(SLEEP,), cmd=wrapped(script), wchan="sigsuspend.isra.0")
        proc.add(SLEEP, kid, ppid=SHELL, wchan="do_epoll_wait")
        assert judge_of(run_dir).look(CLAUDE)[0].verdict == deadwait.UNKNOWN, script


def test_t2196_a_program_whose_main_thread_sleeps_in_a_futex_but_another_waits_on_io_is_no_deadlock(
    proc: Proc, run_dir: Path
) -> None:
    proc.add(SHELL, "bash", ppid=CLAUDE, kids=(SLEEP,), cmd="bash\0x.sh\0", wchan="do_wait")
    base = proc.add(SLEEP, "gradle", ppid=SHELL, wchan="futex_do_wait")
    (base / "task" / str(SLEEP) / "wchan").write_text("futex_do_wait")
    (base / "task" / "103").mkdir()
    (base / "task" / "103" / "wchan").write_text("do_epoll_wait")
    clock = Clock()
    judge = judge_of(run_dir, clock)
    judge.look(CLAUDE)
    clock.now += deadwait.STILL * 2
    assert judge.look(CLAUDE)[0].verdict == deadwait.UNKNOWN


def test_t2390_a_unit_whose_child_works_in_a_capped_scope_is_no_deadlock(
    proc: Proc, run_dir: Path, tmp_path: Path
) -> None:
    slice_dir = tmp_path / "cgroup" / "user.slice" / "todoimpl.slice"
    (slice_dir / "gate.service").mkdir(parents=True)
    (slice_dir / "gate.service" / "cgroup.procs").write_text("800\n801\n")  # make and its shell; pytest left
    (slice_dir / "todoimpl-turn-bcf6a474-0-x.service").mkdir()
    (slice_dir / "todoimpl-turn-bcf6a474-0-x.service" / "cgroup.procs").write_text(f"{CLAUDE}\n")
    proc.add(CLAUDE, "claude", cgroup="/user.slice/todoimpl.slice/todoimpl-turn-bcf6a474-0-x.service")
    proc.add(800, "bash", kids=(801,), cmd="bash\0gate.sh\0")
    (proc.root / "800" / "environ").write_text("TODOIMPL_BUILD_CARD=bcf6a474-0\0")
    proc.add(801, "make", ppid=800, kids=(802,))
    proc.add(802, "pytest", ppid=801, wchan="0", cgroup="/user.slice/capped.slice/capped-1.scope")
    clock = Clock()
    judge = judge_of(run_dir, clock)
    judge.look(CLAUDE)
    clock.now += deadwait.STILL
    proc.cpu(802, 50)
    (found,) = judge.look(CLAUDE)
    assert (found.verdict, found.rule) == (deadwait.HEALTHY, "working")
