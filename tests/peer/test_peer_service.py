"""The peer service: which cards take messages now, the pump thread, the server's startup wiring."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import RunState, save
from todoimpl.peer import service

if TYPE_CHECKING:
    from pathlib import Path

CARD = "abcd1234-0"


class Sched:
    def __init__(self, running: set[str]) -> None:
        self.live = running
        self.bus = self
        self.seen: list[tuple[str, dict[str, Any]]] = []

    def running(self) -> set[str]:
        return self.live

    def publish(self, card: str, event: dict[str, Any]) -> None:
        self.seen.append((card, event))


def _run(root: Path, stage: str, **fields: Any) -> None:
    save(root / CARD, RunState(task_id=CARD, stage=stage, **fields))


def test_liveness(tmp_path: Path) -> None:
    sched = Sched({CARD})
    live = service.liveness(tmp_path, sched.running)
    assert live(CARD) is None  # no run yet
    _run(tmp_path, "implement")
    assert live(CARD) == "live"
    _run(tmp_path, "shipping")
    assert live(CARD) == "held"
    _run(tmp_path, "implement", auto_start={"by": "done_check"})
    assert live(CARD) is None  # a closing run takes no notes
    (tmp_path / CARD / "state.json").write_text("{bad", encoding="utf-8")
    assert live(CARD) is None
    sched.live = set()
    assert live(CARD) is None


def test_start_wires_a_hub_and_pumps(tmp_path: Path, monkeypatch: Any) -> None:
    ticked = threading.Event()
    monkeypatch.setattr(service, "TICK", 0.01)
    sched = Sched(set())
    hub = service.start(tmp_path, sched)
    original = hub.tick
    monkeypatch.setattr(hub, "tick", lambda: (original(), ticked.set()))
    assert ticked.wait(5)
    assert (tmp_path / "peer.token").stat().st_mode & 0o777 == 0o600
    assert hub.token_ok((tmp_path / "peer.token").read_text().strip())


def test_pump_survives_a_failing_tick(tmp_path: Path) -> None:
    calls: list[int] = []
    stop = threading.Event()

    def boom() -> None:
        calls.append(1)
        if len(calls) >= 3:
            stop.set()
        raise RuntimeError

    service.pump(boom, stop, 0.0)
    assert len(calls) == 3


def test_scheduler_without_bus_publishes_nowhere(tmp_path: Path) -> None:
    class Bare:
        def running(self) -> set[str]:
            return set()

    service.start(tmp_path, Bare()).tick()
