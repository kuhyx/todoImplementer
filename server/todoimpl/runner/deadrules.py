"""The /proc reads and the two pattern rules of `deadwait`: a self-matching `pgrep -f` (a), a gone card (c).

Split from `deadwait` to keep each file short; `bgwait.PROC` stays the one /proc seam.
"""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.actions import FINAL_STAGES

from . import bgwait, orphans
from .files import root_of

if TYPE_CHECKING:
    from pathlib import Path

PPID, UTIME, CSTIME = 1, 11, 14  # stat fields after the `)`: ppid, utime, stime, cutime, cstime
ID8 = re.compile(r"\b[0-9a-f]{8}\b")
VALUED = frozenset({"-u", "-U", "-g", "-G", "-P", "-s", "-t", "-F", "--signal", "--pidfile", "--ns"})


def stat(pid: int) -> list[str]:
    """Return the stat fields after the command name; empty when the process is gone."""
    return bgwait.read(bgwait.PROC / str(pid) / "stat").rpartition(")")[2].split()


def ticks(pid: int, last: int = CSTIME) -> int:
    """Return the CPU ticks from utime up to field `last` (cstime: with reaped children)."""
    fields = stat(pid)
    return sum(int(f) for f in fields[UTIME : last + 1]) if len(fields) > CSTIME else 0


def cmdline(pid: int) -> str:
    """Return the command line as pgrep -f sees it: arguments joined by spaces."""
    return bgwait.read(bgwait.PROC / str(pid) / "cmdline").replace("\0", " ").strip()


def subtree(top: int) -> list[int]:
    """Return `top` and every process below it, `top` first."""
    found, todo = [], [top]
    while todo:
        pid = todo.pop()
        found.append(pid)
        todo.extend(bgwait.children(pid))
    return found


def wchans(pid: int) -> list[str]:
    """Return where each thread of `pid` sleeps (a Go main thread in a futex may have one in epoll)."""
    found = [bgwait.read(task / "wchan") for task in sorted((bgwait.PROC / str(pid) / "task").glob("*"))]
    return [w for w in found if w] or [bgwait.read(bgwait.PROC / str(pid) / "wchan")]


def ancestors(pid: int) -> set[int]:
    """Return the processes above `pid`, up to (not with) init."""
    found: set[int] = set()
    while (fields := stat(pid)) and (pid := int(fields[PPID])) > 1 and pid not in found:
        found.add(pid)
    return found


def pgrep_pattern(script: str) -> str | None:
    """Return the pattern of the first `pgrep -f` in `script`, None if none or unreadable."""
    lex = shlex.shlex(script, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        words = list(lex)
    except ValueError:
        return None
    for at, word in enumerate(words):
        if word.rpartition("/")[2] != "pgrep":
            continue
        full, skip = False, False
        for arg in words[at + 1 :]:
            if skip or arg == "--":
                skip = False
            elif arg in VALUED:
                skip = True
            elif arg.startswith("-"):
                full = full or arg == "--full" or (not arg.startswith("--") and "f" in arg)
            else:
                return arg if full else None
    return None


def self_only(pattern: str, top: int, pids: tuple[int, ...]) -> bool:
    """Say whether `pattern` matches no command line but the job's own and its ancestors'."""
    try:
        found = re.compile(pattern)
    except re.error:
        return False
    own = set(pids) | ancestors(top)
    others = (int(d.name) for d in bgwait.PROC.glob("[0-9]*"))
    return not any(found.search(cmdline(pid)) for pid in others if pid not in own)


def gone_card(script: str, run_dir: Path) -> str | None:
    """Return another card the script names that is done, or whose turn is gone and that is not shipping."""
    mine = run_dir.name.partition("-")[0]
    for token in dict.fromkeys(ID8.findall(script)):
        for other in sorted(root_of(run_dir).glob(f"{token}-*")) if token != mine else ():
            st = store.load(other)
            rec = orphans.read(other)
            live = rec is not None and orphans.alive(rec.host_pid, rec.host_start)
            if st is not None and (st.stage in FINAL_STAGES or (st.stage != "shipping" and not live)):
                return other.name
    return None
