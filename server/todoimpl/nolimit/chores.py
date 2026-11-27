"""The board-wide chores: one per tick, in turn, after the tick's repo visit (DOCS-nolimit.md, "Chores").

`prune` (ended cards' worktrees and branches), `rebase` (waiting cards onto origin), `context` (each waiting
card's next-turn context) and `visibility` (the free route's public-repo cache). Each one stops after its
own 45 s budget, every command in it a capped step under 60 s, and asks `still()` before each card. The
report of each lands in `<run root>/nolimit.json` under `chores`, beside the repo cycle.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

from . import context, prune, rebase, status, visibility

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

NAMES = ("prune", "rebase", "context", "visibility")


def run_one(root: Path, name: str, still: Callable[[], bool], now: float) -> dict[str, Any]:
    """Run the chore `name` now; return its report."""
    if name == "prune":
        return prune.run(root, still)
    if name == "rebase":
        return rebase.run(root, still, now)
    if name == "context":
        return context.run(root, still, now)
    return visibility.run(still, now)


def _record(root: Path, name: str, report: dict[str, Any], now: float) -> None:
    data = status.load(root)
    found = data.get("chores")
    done: dict[str, Any] = found if isinstance(found, dict) else {}
    done[name] = {"at": now, "report": report}
    data.update(chores=done, chore_next=NAMES[(NAMES.index(name) + 1) % len(NAMES)])
    root.mkdir(parents=True, exist_ok=True)
    atomic.write_text(root / status.FILE, json.dumps(data, sort_keys=True) + "\n")


def next_name(root: Path) -> str:
    """Return the chore whose turn it is (the first one when none ran yet)."""
    name = status.load(root).get("chore_next")
    return name if name in NAMES else NAMES[0]


def tick(
    root: Path, still: Callable[[], bool], name: str | None = None, clock: Callable[[], float] = time.time
) -> tuple[str, dict[str, Any]]:
    """Run the next chore (or `name`), record it and return (name, report)."""
    name = name or next_name(root)
    report = run_one(root, name, still, clock())
    _record(root, name, report, clock())
    return name, report
