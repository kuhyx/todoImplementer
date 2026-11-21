"""Fakes for the peer hub: a clock, a liveness table and a pipe that records what a task session would read."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from todoimpl.peer.hub import Hub

if TYPE_CHECKING:
    from pathlib import Path

CARD = "abcd1234-0"
OTHER = "efgh5678-0"


@dataclass
class Clock:
    now: float = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class FakePipe:
    """A task session's stdin: `open` cards accept lines; `echo` lists the uuids the session replayed."""

    open: set[str] = field(default_factory=set)
    lines: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    echo: set[str] = field(default_factory=set)
    auto_echo: bool = True

    def write(self, card: str, line: dict[str, Any]) -> tuple[str, int] | None:
        if card not in self.open:
            return None
        self.lines.setdefault(card, []).append(line)
        if self.auto_echo:
            self.echo.add(str(line["uuid"]))
        return (f"{card}.stream.jsonl", 0)

    def echoed(self, card: str, mark: tuple[str, int], uuid: str) -> bool:
        return uuid in self.echo

    def is_open(self, card: str) -> bool:
        return card in self.open


@dataclass
class World:
    hub: Hub
    clock: Clock
    pipe: FakePipe
    live: dict[str, str]
    events: list[tuple[str, dict[str, Any]]]


def make_world(root: Path, *, live: dict[str, str] | None = None) -> World:
    clock, pipe = Clock(), FakePipe(open={CARD, OTHER})
    table = {CARD: "live", OTHER: "live"} if live is None else live
    for card in (CARD, OTHER):
        (root / card).mkdir(parents=True, exist_ok=True)
    events: list[tuple[str, dict[str, Any]]] = []
    hub = Hub(
        root, "secret-token", clock=clock, live=table.get, pipe=pipe, publish=lambda c, e: events.append((c, e))
    )
    return World(hub, clock, pipe, table, events)
