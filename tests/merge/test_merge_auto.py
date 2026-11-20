"""The board merges every valid suggestion by itself: no click, no page open (T2406)."""

import json
import threading
from typing import Any

import pytest
from mergefakes import Rig
from test_merge_service import Brain, Clock, make, seed
from todoimpl.http.backend import BackendError
from todoimpl.merge import auto
from todoimpl.merge.auto import AutoMerge
from todoimpl.merge.service import MergeService

TITLES = ["Make a text-free", "Make b text-free", "Other"]


def rigged(rig: Rig, brain: Brain | None = None) -> tuple[AutoMerge, MergeService, Clock]:
    clock = Clock()
    service = make(rig, brain or Brain(), clock)
    return AutoMerge(service, clock=clock), service, clock


def test_t2406_a_tick_classifies_and_merges_a_group_with_no_click(rig: Rig) -> None:
    seed(rig)
    robot, service, _ = rigged(rig)
    merged = robot.tick()
    assert len(merged) == 1
    assert rig.open_titles("kuhyx/a") == ["Other", "Both"]
    assert service.suggestions() == {"suggestions": []}


def test_t2406_a_page_get_never_classifies_or_merges(rig: Rig) -> None:
    seed(rig)
    brain = Brain()
    service = make(rig, brain, Clock())
    assert service.suggestions() == {"suggestions": []}
    assert brain.prompts == []
    assert rig.open_titles("kuhyx/a") == TITLES


def test_t2406_a_member_with_a_live_run_waits_and_merges_on_a_later_tick(rig: Rig) -> None:
    ids = seed(rig)
    rig.run(ids[0], "implement")
    robot, _, clock = rigged(rig)
    assert robot.tick() == []
    assert rig.open_titles("kuhyx/a") == TITLES  # kept, not dropped
    clock.now += 5
    assert robot.tick() == []  # still live: no backoff, it is simply asked again
    rig.run(ids[0], "shipped")
    assert len(robot.tick()) == 1
    assert rig.open_titles("kuhyx/a") == ["Other", "Both"]


def test_t2406_a_dismissed_group_stays_dismissed(rig: Rig) -> None:
    seed(rig)
    robot, service, _ = rigged(rig)
    robot.service.refresh_if_due()
    service.dismiss(service.suggestions()["suggestions"][0]["id"])
    assert robot.tick() == []
    assert rig.open_titles("kuhyx/a") == TITLES


def test_t2406_a_failed_merge_is_retried_with_a_growing_delay(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(rig)
    robot, service, clock = rigged(rig)
    attempts: list[str] = []
    real = service.merge

    def counted(group: str) -> dict[str, Any]:
        attempts.append(group)
        return real(group)

    monkeypatch.setattr(service, "merge", counted)
    rig.fake.fail_method("tools/call", 500)
    assert robot.tick() == []
    assert len(attempts) == 1
    assert robot.tick() == []  # no time passed: no second attempt
    assert len(attempts) == 1
    clock.now += auto.FIRST_DELAY + 1
    robot.tick()
    assert len(attempts) == 2
    clock.now += auto.FIRST_DELAY + 1  # the delay doubled: this is too early
    robot.tick()
    assert len(attempts) == 2
    clock.now += auto.FIRST_DELAY
    rig.fake.fail_method("tools/call", None)
    assert len(robot.tick()) == 1
    assert len(attempts) == 3


def test_the_delay_is_capped(rig: Rig) -> None:
    seed(rig)
    robot, _, clock = rigged(rig)
    rig.fake.fail_method("tools/call", 500)
    for _ in range(12):
        robot.tick()
        clock.now += auto.MAX_DELAY + 1
    assert max(wait for _, wait in robot._retry.values()) == auto.MAX_DELAY


def test_the_loop_ticks_survives_an_error_and_stops(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(rig)
    robot, _, _ = rigged(rig)
    robot.interval = 0.01
    seen = threading.Event()
    calls: list[int] = []

    def tick() -> list[str]:
        calls.append(1)
        if len(calls) == 1:
            msg = "boom"
            raise RuntimeError(msg)
        seen.set()
        return []

    monkeypatch.setattr(robot, "tick", tick)
    robot.start()
    assert seen.wait(5)
    robot.stop()
    assert len(calls) >= 2


def test_a_group_whose_members_closed_drops_its_retry_entry(rig: Rig) -> None:
    ids = seed(rig)
    brain = Brain()
    brain.answer = lambda found: json.dumps({"groups": [{"ids": found[:2], "title": "Both", "reason": "r"}]})
    robot, _, _ = rigged(rig, brain)
    rig.fake.fail_method("tools/call", 500)
    robot.tick()
    assert robot._retry
    rig.fake.fail_method("tools/call", None)
    for card in rig.cards(ids[:2]):
        rig.client.close_item(card.item, "by hand")
    rig.cache.refresh()
    robot.tick()
    assert robot._retry == {}


def test_a_run_that_starts_between_the_check_and_the_merge_is_not_a_failure(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(rig)
    robot, service, _ = rigged(rig)

    def refuse(_group: str) -> dict[str, object]:
        raise BackendError(auto.LIVE, "a member has a live run")

    monkeypatch.setattr(service, "merge", refuse)
    assert robot.tick() == []
    assert robot._retry == {}  # asked again next tick, no delay


def test_an_unexpected_error_is_logged_and_retried_later(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(rig)
    robot, service, _ = rigged(rig)

    def boom(_group: str) -> dict[str, object]:
        msg = "unexpected"
        raise RuntimeError(msg)

    monkeypatch.setattr(service, "merge", boom)
    assert robot.tick() == []
    assert len(robot._retry) == 1
