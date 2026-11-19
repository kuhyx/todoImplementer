"""A silent turn's wait is judged healthy, dead or unknown from a few /proc reads (T2195, T2196, T2197)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from procfakes import CLAUDE, SHELL, SLEEP, Clock, Proc, card_dir, fake, judge_of, wrapped
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import deadwait, orphans

if TYPE_CHECKING:
    from pathlib import Path

PGREP = 'while pgrep -f "deployhost .*c96b7ce5" >/dev/null; do sleep 5; done'


@pytest.fixture
def proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Proc:
    return fake(tmp_path, monkeypatch)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return card_dir(tmp_path)


def test_t2195_a_pgrep_loop_whose_pattern_matches_only_its_own_command_line_is_dead(
    proc: Proc, run_dir: Path
) -> None:
    proc.add(SHELL, "zsh", ppid=CLAUDE, kids=(SLEEP,), cmd=wrapped(PGREP), wchan="sigsuspend.isra.0")
    proc.add(SLEEP, "sleep", ppid=SHELL, cmd="sleep\x005\0", wchan="hrtimer_nanosleep")
    proc.add(500, "python", cmd="python\0-m\0something.else\0")
    (found,) = judge_of(run_dir).look(CLAUDE)
    assert (found.verdict, found.rule, found.detail) == (deadwait.DEAD, "pgrep-self", "deployhost .*c96b7ce5")
    assert found.who.startswith("while pgrep -f")


def test_t2195_the_same_loop_is_no_dead_wait_while_the_process_it_names_runs(
    proc: Proc, run_dir: Path
) -> None:
    proc.add(SHELL, "zsh", ppid=CLAUDE, kids=(SLEEP,), cmd=wrapped(PGREP), wchan="sigsuspend.isra.0")
    proc.add(SLEEP, "sleep", ppid=SHELL, cmd="sleep\x005\0", wchan="hrtimer_nanosleep")
    proc.add(600, "python", cmd="python\0-m\0todoimpl.runner.deployhost\0/x\0c96b7ce5\0")
    assert deadwait.overall(judge_of(run_dir).look(CLAUDE)).verdict == deadwait.UNKNOWN


@pytest.mark.parametrize(
    "script",
    [
        "pgrep -u kuhy -f 'a(b' && sleep 1",  # not a regex Python reads: no verdict
        "pgrep zsh; sleep 9",  # no -f: process names, never its own command line
        "echo 'unbalanced",
        "pgrep -f",
    ],
)
def test_t2195_a_pgrep_that_cannot_be_read_is_never_called_dead(
    proc: Proc, run_dir: Path, script: str
) -> None:
    proc.add(SHELL, "zsh", ppid=CLAUDE, kids=(SLEEP,), cmd=wrapped(script), wchan="sigsuspend.isra.0")
    proc.add(SLEEP, "sleep", ppid=SHELL, wchan="hrtimer_nanosleep")
    assert judge_of(run_dir).look(CLAUDE)[0].verdict == deadwait.UNKNOWN


def test_t2196_a_tree_asleep_in_a_pipe_read_with_no_cpu_for_two_minutes_is_a_deadlock(
    proc: Proc, run_dir: Path
) -> None:
    proc.add(SHELL, "bash", ppid=CLAUDE, cmd="bash\0b11.sh\0", wchan="anon_pipe_read", cpu=3)
    clock = Clock()
    judge = judge_of(run_dir, clock)
    assert judge.look(CLAUDE)[0].verdict == deadwait.UNKNOWN
    clock.now += deadwait.STILL - 1
    assert judge.look(CLAUDE)[0].verdict == deadwait.UNKNOWN
    clock.now += 1
    (found,) = judge.look(CLAUDE)
    assert (found.verdict, found.rule) == (deadwait.DEAD, "deadlock")


def test_t2196_a_sleeping_poll_loop_and_a_working_child_are_no_deadlock(proc: Proc, run_dir: Path) -> None:
    proc.add(SHELL, "bash", ppid=CLAUDE, kids=(SLEEP, 103), cmd="bash\0x.sh\0", wchan="do_wait")
    proc.add(SLEEP, "sleep", ppid=SHELL, wchan="hrtimer_nanosleep")
    proc.add(103, "cc1", ppid=SHELL, wchan="anon_pipe_read", cpu=5)
    clock = Clock()
    judge = judge_of(run_dir, clock)
    judge.look(CLAUDE)
    clock.now += deadwait.STILL * 2
    assert judge.look(CLAUDE)[0].verdict == deadwait.UNKNOWN  # sleep: a poll loop, never a deadlock
    proc.cpu(103, 9)
    clock.now += 1
    assert judge.look(CLAUDE)[0].verdict == deadwait.HEALTHY


def test_t2196_a_job_in_the_build_lock_queue_is_healthy_even_when_it_looks_dead(
    proc: Proc, run_dir: Path
) -> None:
    proc.add(SHELL, "bash", ppid=CLAUDE, kids=(SLEEP,), cmd="bash\0b11.sh\0", wchan="anon_pipe_read")
    proc.add(SLEEP, "flock", ppid=SHELL, wchan="locks_lock_inode_wait")
    st = (run_dir.parent / "build.lock").stat()
    key = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    (proc.root / "locks").write_text(f"1:  -> FLOCK  ADVISORY  WRITE {SLEEP} {key} 0 EOF\n")
    clock = Clock()
    judge = judge_of(run_dir, clock)
    judge.look(CLAUDE)
    clock.now += deadwait.STILL * 2
    (found,) = judge.look(CLAUDE)
    assert (found.verdict, found.rule) == (deadwait.HEALTHY, "lock-queue")


@pytest.mark.parametrize(
    ("comm", "cmd"),
    [
        ("gh", "gh\0run\0watch\x0012\0"),
        ("systemd-run", "systemd-run\0--user\0--wait\0make\0"),
        ("inotifywait", ""),
    ],
)
def test_t2196_an_event_wait_is_healthy(proc: Proc, run_dir: Path, comm: str, cmd: str) -> None:
    proc.add(SHELL, "zsh", ppid=CLAUDE, kids=(SLEEP,), cmd=wrapped("x"), wchan="sigsuspend.isra.0")
    proc.add(SLEEP, comm, ppid=SHELL, cmd=cmd or None, wchan="futex_do_wait")
    (found,) = judge_of(run_dir).look(CLAUDE)
    assert (found.verdict, found.rule) == (deadwait.HEALTHY, "event-wait")


UNIT = "todoimpl-turn-c96b7ce5-0-implement-1.service"


def test_t2197_a_wait_on_a_card_that_already_shipped_is_dead(proc: Proc, run_dir: Path) -> None:
    other = run_dir.parent / "c96b7ce5-0"
    store.save(other, RunState(task_id="c96b7ce5-0", stage="shipped"))
    loop = f"until ! systemctl --user is-active {UNIT}; do sleep 10; done"
    proc.add(SHELL, "zsh", ppid=CLAUDE, kids=(SLEEP,), cmd=wrapped(loop), wchan="sigsuspend.isra.0")
    proc.add(SLEEP, "sleep", ppid=SHELL, wchan="hrtimer_nanosleep")
    (found,) = judge_of(run_dir).look(CLAUDE)
    assert (found.verdict, found.rule, found.detail) == (deadwait.DEAD, "cross-card", "c96b7ce5-0")


def test_t2197_a_wait_on_a_card_whose_turn_still_runs_or_that_ships_is_left_alone(
    proc: Proc, run_dir: Path
) -> None:
    other, shipping = run_dir.parent / "c96b7ce5-0", run_dir.parent / "d4ce7675-0"
    store.save(other, RunState(task_id="c96b7ce5-0", stage="implement"))
    store.save(shipping, RunState(task_id="d4ce7675-0", stage="shipping"))
    me = os.getpid()
    orphans.write(
        other, stem="implement-1", role="implement", pid=me, host_pid=me, host_start=orphans.start_of(me)
    )
    loop = f"while pgrep -f deployhost; do sleep 5; done # c96b7ce5 d4ce7675 bcf6a474 0badf00d {UNIT}"
    proc.add(SHELL, "zsh", ppid=CLAUDE, kids=(SLEEP,), cmd=wrapped(loop), wchan="sigsuspend.isra.0")
    proc.add(SLEEP, "sleep", ppid=SHELL, wchan="hrtimer_nanosleep")
    proc.add(700, "python", cmd="python\0deployhost\0")
    assert judge_of(run_dir).look(CLAUDE)[0].verdict == deadwait.UNKNOWN
