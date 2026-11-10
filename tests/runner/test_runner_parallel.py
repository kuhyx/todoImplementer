"""No cap on parallel runs: every Start drives at once, none waits behind a run of another repo."""

import threading

import pytest
from runnerfakes import Env, FakeClient, task
from schedfakes import wait
from todoimpl.runner.scheduler import Scheduler


def test_five_starts_while_four_run_all_run_at_once(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(Scheduler, "_drive", lambda _self, _card: release.wait(20))
    cards = [f"abcd{i:04d}-0" for i in range(9)]
    client = FakeClient(
        {card[:8]: task(card[:8], repo=f"kuhyx/r{n}", body="done: ok") for n, card in enumerate(cards)}
    )
    sched = Scheduler(client, world.root, check_timeout=20)
    try:
        for card in cards[:4]:
            sched.start(card)
        wait(lambda: len(sched.running()) == 4)
        for card in cards[4:]:
            sched.start(card)
        wait(lambda: sched.running() == set(cards))
    finally:
        threading.Timer(0.3, release.set).start()  # close() waits for the live drives to end
        sched.close()
    assert sched.running() == set()
