"""An idle turn names what it waits on: the build lock (and its holder) or a background job (T2124)."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import pytest
from todoimpl.board.card import current_line
from todoimpl.board.state import RunState
from todoimpl.board.status import WAITS_FOR, Status
from todoimpl.runner import bgwait

if TYPE_CHECKING:
    from pathlib import Path

CLAUDE, ZSH, SYSTEMD_RUN, WAITER = 100, 101, 102, 300
BTIME = 1_800_000_000
TCK = os.sysconf("SC_CLK_TCK")
BG = "/usr/bin/zsh\0-c\0source snap.sh && eval 'scripts/bg.sh gate2 . bash /tmp/gate2.sh' < /dev/null\0"
HELD = "d4ce7675-0 (pre-commit run --all-files) since 2026-11-19 15:28:12\n"


def _pid(
    proc: Path, pid: int, comm: str, *, kids: tuple[int, ...] = (), ticks: int = 0, **extra: str
) -> Path:
    """Write a fake /proc/<pid>: children, comm, cmdline, stat (starttime), optional environ and cwd link."""
    base = proc / str(pid)
    (base / "task" / str(pid)).mkdir(parents=True)
    (base / "task" / str(pid) / "children").write_text(" ".join(map(str, kids)))
    (base / "comm").write_text(comm + "\n")
    (base / "cmdline").write_text(extra.get("cmdline", comm + "\0"))
    fields = ["S", *["0"] * 18, str(ticks), "0"]
    (base / "stat").write_text(f"{pid} ({comm}) {' '.join(fields)}\n")
    if "environ" in extra:
        (base / "environ").write_text(extra["environ"])
    if "cwd" in extra:
        (base / "cwd").symlink_to(extra["cwd"])
    return base


@pytest.fixture
def fake_proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """Claude -> zsh (bg.sh) -> systemd-run; the lock root with build.lock; the card's run dir."""
    proc, root, run_dir = tmp_path / "proc", tmp_path / "root", tmp_path / "runs" / "e1fa3e99-0"
    (run_dir / "wt").mkdir(parents=True)
    root.mkdir()
    (root / "build.lock").touch()
    (proc / "stat").parent.mkdir(parents=True)
    (proc / "stat").write_text(f"cpu 1 2 3\nbtime {BTIME}\n")
    (proc / "locks").write_text("")
    _pid(proc, CLAUDE, "claude", kids=(ZSH,))
    _pid(proc, ZSH, "zsh", kids=(SYSTEMD_RUN,), ticks=50 * TCK, cmdline=BG)
    _pid(proc, SYSTEMD_RUN, "systemd-run")
    monkeypatch.setattr(bgwait, "PROC", proc)
    return proc, root / "build.lock", run_dir


def _wait_on_lock(proc: Path, lock: Path, pid: int = WAITER) -> None:
    st = lock.stat()
    key = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    holder = f"1: FLOCK  ADVISORY  WRITE 999 {key} 0 EOF\n"
    (proc / "locks").write_text(holder + f"1:  -> FLOCK  ADVISORY  WRITE {pid} {key} 0 EOF\n")


def _since(text: str) -> float:
    return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))


def test_t2124_a_job_waiting_on_the_lock_outside_claudes_tree_names_the_holder(
    fake_proc: tuple[Path, Path, Path],
) -> None:
    proc, lock, run_dir = fake_proc
    _pid(proc, WAITER, "flock", cwd=str(run_dir / "wt"))  # systemd-run's unit: no child of claude
    _wait_on_lock(proc, lock)
    lock.with_name("build.lock.holder").write_text(HELD)
    found = bgwait.scan(CLAUDE, run_dir, lock)
    assert found == {"lock": True, "who": "d4ce7675-0", "since": _since("2026-11-19 15:28:12")}
    run = RunState(task_id="e1fa3e99-0", stage="implement", extra={WAITS_FOR: found})
    assert current_line(Status.WORKING, run, None, 0.0) == "⏳🔒 d4ce7675-0 15:28"


def test_t2124_a_waiter_is_this_cards_by_its_card_variable_or_by_being_below_claude(
    fake_proc: tuple[Path, Path, Path],
) -> None:
    proc, lock, run_dir = fake_proc
    _pid(  # no cwd link (another user's view): the card variable alone ties it
        proc,
        WAITER,
        "flock",
        ticks=70 * TCK,
        environ="A=1\0TODOIMPL_BUILD_CARD=e1fa3e99-0\0",
    )
    _wait_on_lock(proc, lock)
    lock.with_name("build.lock.holder").write_text("? (dart analyze) since 2026-11-19 15:30:00\n")
    assert bgwait.scan(CLAUDE, run_dir, lock) == {
        "lock": True, "who": "dart analyze", "since": _since("2026-11-19 15:30:00"),
    }  # fmt: skip
    lock.with_name("build.lock.holder").write_text("")  # holder unknown: when this wait began
    assert bgwait.scan(CLAUDE, run_dir, lock) == {"lock": True, "who": "?", "since": BTIME + 70.0}
    _wait_on_lock(proc, lock, SYSTEMD_RUN)  # in claude's own tree
    assert bgwait.scan(CLAUDE, run_dir, lock) == {"lock": True, "who": "?", "since": BTIME + 0.0}


def test_t2124_with_no_wait_of_its_own_the_card_names_the_background_job(
    fake_proc: tuple[Path, Path, Path],
) -> None:
    proc, lock, run_dir = fake_proc
    _pid(
        proc,
        WAITER,
        "flock",
        cwd=str(fake_proc[0].parent / "elsewhere"),
        environ="TODOIMPL_BUILD_CARD=other-0\0",
    )  # another card's wait
    _wait_on_lock(proc, lock)
    assert (bgwait.scan(CLAUDE, run_dir, lock) or {})["lock"] is False
    link = proc / str(WAITER) / "cwd"
    link.unlink()
    link.symlink_to(run_dir / "children" / "e1fa3e99-1" / "wt")  # an umbrella child's wait is the child's
    found = bgwait.scan(CLAUDE, run_dir, lock)
    assert found == {"lock": False, "who": "scripts/bg.sh gate2 . bash /tmp/gate2.sh", "since": BTIME + 50.0}
    run = RunState(task_id="e1fa3e99-0", stage="implement", extra={WAITS_FOR: found})
    at = time.strftime("%H:%M", time.localtime(BTIME + 50.0))
    assert current_line(Status.WORKING, run, None, 0.0) == f"⏳ scripts/bg.sh gate2 . bash /tmp/gate2.sh {at}"


def test_t2124_no_shell_below_claude_means_no_wait(
    fake_proc: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    proc, lock, run_dir = fake_proc
    (proc / str(CLAUDE) / "task" / str(CLAUDE) / "children").write_text("")
    assert bgwait.scan(CLAUDE, run_dir, lock) is None
    assert bgwait.scan(None, run_dir, lock) is None
    (proc / "locks").unlink()
    assert bgwait.waiters(tmp_path / "no-such.lock") == []
    assert bgwait.waiters(lock) == []


def test_t2124_a_plain_command_and_an_unreadable_process_still_give_a_line(
    fake_proc: tuple[Path, Path, Path],
) -> None:
    proc, lock, run_dir = fake_proc
    (proc / str(ZSH) / "cmdline").write_text("bash\0-c\0sleep 600;\n  echo done\0")
    (proc / str(ZSH) / "stat").unlink()  # gone between the walk and the read
    assert bgwait.scan(CLAUDE, run_dir, lock) == {"lock": False, "who": "bash -c sleep 600;", "since": None}
    run = RunState(task_id="e1fa3e99-0", stage="implement", extra={WAITS_FOR: {"lock": False, "who": "x"}})
    assert current_line(Status.WORKING, run, None, 0.0) == "⏳ x"


def test_t2441_the_job_is_the_oldest_shell_and_its_script_is_whole(
    fake_proc: tuple[Path, Path, Path],
) -> None:
    assert bgwait.job(CLAUDE) == ZSH
    assert bgwait.script(ZSH) == "scripts/bg.sh gate2 . bash /tmp/gate2.sh"
    assert bgwait.job(None) is None
