"""The loop's thread: start, stop and a tick that crashes."""

from __future__ import annotations

import pytest
from errfakes import kartka_entry
from loopfakes import KEY, World


def test_start_stop_runs_a_thread(world: World) -> None:
    world.loop.interval = 0.01
    world.entries(kartka_entry())
    world.loop.start()
    world.loop.start()
    world.loop.stop()
    assert world.ledger()[KEY]["state"] == "ticket"


def test_a_crashing_tick_is_logged_and_the_thread_goes_on(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def boom() -> None:
        calls.append(1)
        raise ValueError

    monkeypatch.setattr(world.loop, "tick", boom)
    world.loop.interval = 0.01
    world.loop.start()
    while len(calls) < 2:
        world.loop._stop.wait(0.01)
    world.loop.stop()


def test_stopping_a_loop_that_never_started_is_fine(world: World) -> None:
    world.loop.stop()
