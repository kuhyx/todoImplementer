"""The repo task's two files in its run dir.

`parts.json` is written only by the server (the parts of this drive, in work order). `parts-done.json` is
written only by Claude, through `python -m todoimpl.repotask.tick` (which part is finished, the steps a part
was split into), so the two writers never race. The board overlays the second onto the first. The server
writes it in one case, under the same lock: Ship unticks a part no live row proved (`untick`, T2467).
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from todoimpl.board.parts import TICKS
from todoimpl.runner.files import read_json, write_json

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item

    from .model import Part

PARTS = "parts.json"
DONE = "parts-done.json"
LOCK = ".parts-done.lock"


class PartError(Exception):
    """A tick that cannot be accepted; the message says why and is printed by the CLI."""


@dataclass(frozen=True)
class Ticks:
    """What Claude recorded: finished part keys and, per part, the steps it was split into."""

    done: tuple[str, ...] = ()
    steps: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def progress(self, key: str) -> dict[str, int] | None:
        """Return `{done, total}` of a part's steps, None when it was not split."""
        found = self.steps.get(key)
        if not found:
            return None
        return {"done": sum(1 for step in found if step["done"]), "total": len(found)}


def snapshot(run_dir: Path, item: Item) -> None:
    """Write the drive's parts in work order, so the tick command can check keys against them."""
    rows = [{"key": p.key, "title": p.title, "human": p.human, "held": p.held} for p in item.parts]
    write_json(run_dir / PARTS, rows)


def known(run_dir: Path) -> set[str]:
    """Return the keys of the parts the run may tick (actionable ones of the latest snapshot)."""
    rows = read_json(run_dir / PARTS) or []
    return {str(row["key"]) for row in rows if not (row["human"] or row["held"])}


def read(run_dir: Path) -> Ticks:
    """Return the ticks Claude recorded; none when the file is missing or unreadable."""
    data = read_json(run_dir / DONE)
    if not isinstance(data, dict):
        return Ticks()
    return Ticks(tuple(data.get("done", [])), dict(data.get("steps", {})))


@contextmanager
def _locked(run_dir: Path) -> Iterator[Ticks]:
    """Hold the file lock while a tick is read, changed and written (two ticks may come at once)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / LOCK).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield read(run_dir)


def _write(run_dir: Path, ticks: Ticks) -> None:
    write_json(run_dir / DONE, {"done": list(ticks.done), "steps": ticks.steps})


def _check_key(run_dir: Path, key: str) -> None:
    if key not in known(run_dir):
        msg = f"{key} is not a part of this run (see {run_dir / PARTS})"
        raise PartError(msg)


def mark_done(run_dir: Path, key: str) -> None:
    """Tick a part; refused while it has unfinished steps."""
    _check_key(run_dir, key)
    with _locked(run_dir) as ticks:
        open_steps = [s["title"] for s in ticks.steps.get(key, []) if not s["done"]]
        if open_steps:
            msg = f"{key} still has open steps: {', '.join(open_steps)}"
            raise PartError(msg)
        if key not in ticks.done:
            _write(run_dir, Ticks((*ticks.done, key), ticks.steps))


def split(run_dir: Path, key: str, titles: list[str]) -> None:
    """Record the steps a part was split into (appended; a title already there is kept once)."""
    _check_key(run_dir, key)
    with _locked(run_dir) as ticks:
        steps = {**ticks.steps}
        have = steps.setdefault(key, [])
        have += [{"title": t, "done": False} for t in titles if t not in {s["title"] for s in have}]
        _write(run_dir, Ticks(ticks.done, steps))


def step_done(run_dir: Path, key: str, number: int) -> None:
    """Tick step `number` (1-based) of a split part."""
    _check_key(run_dir, key)
    with _locked(run_dir) as ticks:
        have = ticks.steps.get(key, [])
        if not 1 <= number <= len(have):
            msg = f"{key} has {len(have)} steps, no step {number}"
            raise PartError(msg)
        have[number - 1]["done"] = True
        _write(run_dir, ticks)


def reset(run_dir: Path) -> None:
    """Forget the ticks: a new cycle starts with every part open."""
    (run_dir / DONE).unlink(missing_ok=True)


def untick(run_dir: Path, keys: list[str]) -> None:
    """Take parts off the done list: Ship leaves a part with no live proof open (T2467)."""
    with _locked(run_dir) as ticks:
        _write(run_dir, Ticks(tuple(key for key in ticks.done if key not in keys), ticks.steps))


def ticked(run_dir: Path, item: Item) -> list[Part]:
    """Return the item's parts Claude has ticked, in work order."""
    done = set(read(run_dir).done)
    return [part for part in item.parts if part.actionable and part.key in done]


def keyed(item: Item) -> bool:
    """Return True when the run works on several parts: then every criterion names its part (T2460)."""
    return sum(part.actionable for part in item.parts) > 1


def unproven(run_dir: Path, item: Item, rows: list[dict[str, object]]) -> list[Part]:
    """Return the ticked parts of a keyed item no done, non-deferred live row names: Ship refuses them."""
    if not keyed(item):
        return []
    proven = {row["part"] for row in rows if row["done"] and not row["deferred"]}
    return [part for part in ticked(run_dir, item) if part.key not in proven]


def commit_identity(item: Item, run_dir: Path) -> tuple[str, list[str]]:
    """Return the commit subject title and the note ids for the `Todo:` trailers (the ticked parts' notes)."""
    done = ticked(run_dir, item) if item.parts else []
    if not done:
        return item.title, [item.note_id]
    return done[0].title, list(dict.fromkeys(part.note_id for part in done))


def unticked(run_dir: Path, item: Item) -> list[Part]:
    """Return the item's parts the run still owes, in work order."""
    done = set(read(run_dir).done)
    return [part for part in item.parts if part.actionable and part.key not in done]


def overlay(run_dir: Path, run: RunState) -> RunState:
    """Return the repo task's run with the ticks attached for the card (not saved); other runs unchanged."""
    if not run.extra.get("repotask"):
        return run
    ticks = read(run_dir)
    progress = {key: found for key in ticks.steps if (found := ticks.progress(key))}
    return replace(run, extra={**run.extra, TICKS: {"done": list(ticks.done), "progress": progress}})
