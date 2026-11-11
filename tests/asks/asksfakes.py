"""Fakes for the ask service: a task cache, a recording scheduler, a command runner."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from todoimpl.asks.service import AskService

BODY = """Do it
```ask
choice c1: Colour | red | *blue | risk=reversible
choice c2: Wipe the disk | *no | yes | risk=reversible
command k1: make fast
screenshot s1: Looks fine? | shots/a.png
```
"""


@dataclass
class PartBody:
    body: str


@dataclass
class Task:
    id: str
    body: str
    parts: tuple[Any, ...] = ()


@dataclass
class Snap:
    tasks: list[Task]


class Cache:
    def __init__(self, *tasks: Task) -> None:
        self.tasks = list(tasks)

    def snapshot(self) -> Snap:
        return Snap(self.tasks)


@dataclass
class Sched:
    sent: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False

    def send(self, id8: str, text: str) -> None:
        if self.fail:
            raise RuntimeError("busy")
        self.sent.append((id8, text))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def runner(calls: list[tuple[str, Path | None]]) -> Any:
    def run(command: str, cwd: Path | None) -> dict[str, Any]:
        calls.append((command, cwd))
        return {"exit": 0, "tail": "ok", "capped": False}

    return run


ID = "abcd1234-0"


class Rig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cache = Cache(Task(ID, BODY))
        self.sched = Sched()
        self.clock = Clock()
        self.calls: list[tuple[str, Path | None]] = []
        self.svc = AskService(self.cache, self.sched, root, clock=self.clock, runner=runner(self.calls))  # type: ignore[arg-type]
        self.dir = root / ID
