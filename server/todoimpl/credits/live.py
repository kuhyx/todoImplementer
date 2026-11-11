"""Credit turns that are running right now: how many, what each has cost so far, and how to stop them.

A start reserves money for every running credit turn (`pacing`), and the hard stop sums their live cost with
the ledger's spend (`route.watch`). Keyed by run root and card: a card has one turn at a time. Memory only:
a restart finds its turns again when `runner.turn` adopts them and the stream replays into the meter.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

LOCK = threading.RLock()


@dataclass
class Entry:
    """One running credit turn: its live cost at list price and the hooks that stop it."""

    usd: float = 0.0
    hit: Callable[[], None] | None = None  # tells the driver the cap stopped the turn
    stop: Callable[[], None] | None = None  # kills the turn


@dataclass
class Running:
    """The running credit turns of one run root."""

    by_card: dict[str, Entry] = field(default_factory=dict)


_ROOTS: dict[Path, Running] = {}


def _entries(root: Path) -> dict[str, Entry]:
    return _ROOTS.setdefault(root, Running()).by_card


def reset() -> None:
    """Forget every running turn (tests)."""
    with LOCK:
        _ROOTS.clear()


def begin(root: Path, card: str) -> None:
    """Note that `card` has a credit turn starting or running (idempotent)."""
    with LOCK:
        _entries(root).setdefault(card, Entry())


def attach(root: Path, card: str, hit: Callable[[], None], stop: Callable[[], None]) -> None:
    """Give a running turn its stop hooks."""
    with LOCK:
        entry = _entries(root).setdefault(card, Entry())
        entry.hit, entry.stop = hit, stop


def end(root: Path, card: str) -> None:
    """Note that `card`'s credit turn is over (idempotent)."""
    with LOCK:
        _entries(root).pop(card, None)


def set_cost(root: Path, card: str, usd: float) -> None:
    """Record what the running turn of `card` has cost so far (list price)."""
    with LOCK:
        _entries(root).setdefault(card, Entry()).usd = usd


def costs(root: Path) -> list[float]:
    """Return the live cost of every running credit turn."""
    with LOCK:
        return [e.usd for e in _entries(root).values()]


def running(root: Path) -> int:
    """Return how many credit turns are running."""
    with LOCK:
        return len(_entries(root))


def stoppers(root: Path) -> list[tuple[Callable[[], None], Callable[[], None]]]:
    """Return (hit, stop) of every running turn that can be stopped."""
    with LOCK:
        return [(e.hit, e.stop) for e in _entries(root).values() if e.hit is not None and e.stop is not None]
