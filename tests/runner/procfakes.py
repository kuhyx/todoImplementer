"""A fake /proc for the watchdog tests: processes with a parent, CPU ticks, a wait channel, a stderr."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.runner import bgwait, deadwait

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

BTIME = 1_800_000_000
CLAUDE, SHELL, SLEEP = 100, 101, 102


def wrapped(script: str) -> str:
    """Return the cmdline of a zsh the Bash tool started for `script` (its `eval '...'` wrapper)."""
    quoted = script.replace("'", "'\\''")
    return f"/usr/bin/zsh\0-c\0source snap.sh && eval '{quoted}' < /dev/null\0"


@dataclass(frozen=True)
class Proc:
    """One fake /proc tree under `root`."""

    root: Path

    def boot(self) -> Proc:
        """Write /proc/stat (btime) and an empty /proc/locks."""
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "stat").write_text(f"cpu 1 2 3\nbtime {BTIME}\n")
        (self.root / "locks").write_text("")
        return self

    def add(
        self,
        pid: int,
        comm: str,
        *,
        ppid: int = 1,
        kids: tuple[int, ...] = (),
        cmd: str | None = None,
        wchan: str = "do_wait",
        cpu: int = 0,
        start: int = 0,
        cgroup: str = "",
    ) -> Path:
        """Write /proc/<pid>: children, comm, cmdline, stat (ppid, utime, starttime), wchan, cgroup, fd/2."""
        base = self.root / str(pid)
        task = base / "task" / str(pid)
        task.mkdir(parents=True, exist_ok=True)
        (task / "children").write_text(" ".join(map(str, kids)))
        (base / "comm").write_text(comm + "\n")
        (base / "cmdline").write_text(cmd if cmd is not None else comm + "\0")
        fields = ["S", str(ppid), *["0"] * 9, str(cpu), "0", "0", "0", *["0"] * 4, str(start), "0"]
        (base / "stat").write_text(f"{pid} ({comm}) {' '.join(fields)}\n")
        (base / "wchan").write_text(wchan)
        (base / "cgroup").write_text(f"0::{cgroup}\n")
        (base / "fd").mkdir(exist_ok=True)
        (base / "fd" / "2").touch()
        return base

    def cpu(self, pid: int, ticks: int) -> None:
        """Let `pid` use CPU: set its utime."""
        stat = self.root / str(pid) / "stat"
        head, _, tail = stat.read_text().partition(") ")
        fields = tail.split()
        fields[11] = str(ticks)
        stat.write_text(f"{head}) {' '.join(fields)}\n")


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Proc:
    """Boot a fake /proc with claude in it and point bgwait and deadwait at it."""
    found = Proc(tmp_path / "proc").boot()
    found.add(CLAUDE, "claude", kids=(SHELL,), cmd="claude\0-p\0override\0")
    monkeypatch.setattr(bgwait, "PROC", found.root)
    monkeypatch.setattr(deadwait, "CGROUP", tmp_path / "cgroup")
    return found


def card_dir(tmp_path: Path) -> Path:
    """Return the card's run dir in a run root holding the build lock."""
    found = tmp_path / "root" / "bcf6a474-0"
    (found / "wt").mkdir(parents=True)
    (tmp_path / "root" / "build.lock").touch()
    return found


def judge_of(run_dir: Path, clock: Clock | None = None) -> deadwait.Judge:
    """Return a judge of the card in `run_dir` on a hand-moved clock."""
    return deadwait.Judge(run_dir, run_dir.parent / "build.lock", clock or Clock())
