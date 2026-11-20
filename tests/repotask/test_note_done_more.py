"""The watcher's edges: a refusing scheduler, an unanswered todo app, the budget, its thread (T2065)."""

from __future__ import annotations

from typing import Any

import pytest
from repofakes import Rig
from test_note_done import _close_in_todo, _stage, _watcher
from todoimpl.board.state import RunState, save
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.scheduler import RunnerError
from todoimpl.service import notedone
from todoimpl.service.notedone import NoteDoneWatcher


class Refuser:
    """A scheduler that always refuses: the card is shipping or already done."""

    def done_manually(self, card: str, **_: Any) -> None:
        raise RunnerError("shipping cannot be stopped", "disabled")


def test_t2065_a_refusing_scheduler_leaves_the_card_alone(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    watcher = NoteDoneWatcher(rig.cache, rig.client, Refuser(), rig.world.root)  # type: ignore[arg-type]
    watcher.tick()
    _close_in_todo(rig, note)
    watcher.tick()
    assert _stage(rig, repo_card_id(repo)) is None


def test_t2065_an_unanswered_todo_app_is_asked_again_at_the_next_snapshot(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    watcher = _watcher(rig)
    watcher.tick()
    _close_in_todo(rig, note)
    rig.fake.fail_method("tools/call", 500)
    watcher.tick()  # the snapshot is good, the todo app then fails on get_task
    assert _stage(rig, repo_card_id(repo)) is None
    rig.fake.fail_method("tools/call", None)
    rig.cache.refresh()
    watcher.tick()
    assert _stage(rig, repo_card_id(repo)) == "done_manually"


def test_t2065_more_cards_than_the_budget_wait_for_the_next_snapshot(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notedone, "BUDGET", 1)
    repos = [rig.repo("one"), rig.repo("two")]
    notes = [rig.note(r, "a note", "x") for r in repos]
    watcher = _watcher(rig)
    watcher.tick()
    for note in notes:
        _close_in_todo(rig, note)
    watcher.tick()
    done = [_stage(rig, repo_card_id(r)) for r in repos]
    assert done.count("done_manually") == 1
    rig.cache.refresh()
    watcher.tick()
    assert [_stage(rig, repo_card_id(r)) for r in repos] == ["done_manually"] * 2


def test_t2065_a_card_whose_note_is_still_open_is_asked_again_only_after_a_minute(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    ghost = f"{note}-1"  # a section that does not exist: its run is not on the board, its note is open
    save(rig.run_dir(ghost), RunState(task_id=ghost, stage="implement", repo=repo))
    save(rig.run_dir("deadbeef-0"), RunState(task_id="deadbeef-0", stage="implement", repo=repo))
    rig.run_dir("deadbeef-0").joinpath("state.json").write_text("{bad json")
    watcher = _watcher(rig)
    watcher.tick()
    rig.cache.refresh()
    watcher.tick()  # the ghost is quiet now: not asked again
    assert _stage(rig, ghost) == "implement"
    _close_in_todo(rig, note)
    rig.cache.refresh()
    watcher.tick()
    assert _stage(rig, ghost) == "implement"  # still within the minute


def test_t2065_a_repo_run_without_part_keys_is_skipped(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="implement", repo=repo, extra={"repotask": True}))
    _close_in_todo(rig, note)
    _watcher(rig).tick()
    assert _stage(rig, card) == "implement"  # no parts.json: nothing says which notes it covers


def test_t2065_the_thread_looks_by_itself_and_survives_a_bad_tick(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    watcher = NoteDoneWatcher(rig.cache, rig.client, rig.sched, rig.world.root, interval=0.05)
    NoteDoneWatcher(rig.cache, rig.client, rig.sched, rig.world.root).stop()  # never started: nothing to join
    real, calls = watcher.tick, []

    def flaky() -> None:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        real()

    monkeypatch.setattr(watcher, "tick", flaky)
    watcher.start()
    watcher.start()  # idempotent
    rig.until(lambda: len(calls) >= 1)
    _close_in_todo(rig, note)
    rig.until(lambda: _stage(rig, repo_card_id(repo)) == "done_manually")
    watcher.stop()
    assert len(calls) >= 3


def test_t2398_a_run_whose_note_was_deleted_is_asked_about_once_a_minute_not_every_tick(rig: Rig) -> None:
    repo = rig.repo()
    save(rig.run_dir("deadbeef-0"), RunState(task_id="deadbeef-0", stage="spec_wait", repo=repo))
    now = [1000.0]
    watcher = NoteDoneWatcher(rig.cache, rig.client, rig.sched, rig.world.root, clock=lambda: now[0])

    def asks() -> int:
        return sum(1 for name, args in rig.fake.calls if name == "get_task" and "deadbeef" in str(args))

    for _ in range(5):  # used to ask (and log a warning) at every snapshot, every 2 s for ever
        rig.cache.refresh()
        watcher.tick()
    assert asks() == 2  # one retry at the next snapshot, then it waits
    now[0] += notedone.QUIET + 1
    rig.cache.refresh()
    watcher.tick()
    assert asks() == 3
    assert _stage(rig, "deadbeef-0") == "spec_wait"  # a missing note changes nothing
