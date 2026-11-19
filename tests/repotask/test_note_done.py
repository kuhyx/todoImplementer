"""A note marked done in the todo app puts its card in Done manually and stops its session (T2065)."""

from __future__ import annotations

from repofakes import Rig
from todoimpl.board.state import RunState, load, save
from todoimpl.repotask.ids import repo_card_id
from todoimpl.service.notedone import NoteDoneWatcher


def _watcher(rig: Rig) -> NoteDoneWatcher:
    return NoteDoneWatcher(rig.cache, rig.client, rig.sched, rig.world.root)


def _close_in_todo(rig: Rig, note8: str, status: str = "done") -> None:
    """Do to the note what kuhy's click in the todo app does, and let the board see it."""
    found = next(n for k, n in rig.fake.store.notes.items() if k.startswith(note8))
    found.status = status
    found.evidence = "ticked in the app"
    rig.cache.refresh()


def _stage(rig: Rig, card: str) -> str | None:
    run = load(rig.run_dir(card))
    return None if run is None else run.stage


def test_t2065_a_backlog_card_whose_note_is_done_in_todo_shows_in_done_manually(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    watcher = _watcher(rig)
    watcher.tick()  # learns the card
    _close_in_todo(rig, note)
    assert all(c["id"] != card for c in rig.backend.board()["tasks"])  # today: it just vanishes
    watcher.tick()
    rig.cache.refresh()
    shown = rig.card(repo)
    assert (shown["status"], shown["column"], _stage(rig, card)) == ("done_manually", "done", "done_manually")
    assert rig.world.calls() == []


def test_t2065_a_live_session_is_stopped_and_the_card_is_done_manually(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    rig.script(card, ({"_fake": "sleep", "sec": 30},))
    rig.sched.start(card)
    rig.until(lambda: card in rig.sched.running())
    rig.until(lambda: bool(rig.world.calls()))
    watcher = _watcher(rig)
    watcher.tick()
    _close_in_todo(rig, note)
    watcher.tick()
    rig.until(lambda: card not in rig.sched.running())
    rig.until(lambda: _stage(rig, card) == "done_manually")
    assert len(rig.world.calls()) == 1
    rig.cache.refresh()
    assert rig.card(repo)["status"] == "done_manually"


def test_t2065_a_card_with_parts_moves_to_done_once_every_part_is_done(rig: Rig) -> None:
    repo = rig.repo()
    first = rig.note(repo, "first note", "x")
    second = rig.note(repo, "second note", "y")
    card = repo_card_id(repo)
    watcher = _watcher(rig)
    watcher.tick()
    _close_in_todo(rig, first)
    watcher.tick()
    shown = rig.card(repo)
    assert (shown["status"], [p["title"] for p in shown["parts"]]) == ("backlog", ["second note"])
    assert _stage(rig, card) is None
    _close_in_todo(rig, second)
    watcher.tick()
    rig.cache.refresh()
    assert (rig.card(repo)["status"], _stage(rig, card)) == ("done_manually", "done_manually")


def test_t2065_a_restart_still_notices_a_run_whose_note_was_done_meanwhile(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="implement", repo=repo, extra={"repotask": True}))
    rig.run_dir(card).joinpath("parts.json").write_text(
        f'[{{"key":"{note}-0","title":"a","human":false,"held":false}}]'
    )
    _close_in_todo(rig, note)
    _watcher(rig).tick()  # a fresh watcher: no memory of the card, only the run dir
    assert _stage(rig, card) == "done_manually"


def test_t2065_the_boards_own_close_is_not_a_manual_one(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    watcher = _watcher(rig)
    watcher.tick()
    rig.client.close_task(note, "merged into 2d0704cd")  # what merge, migrate and Ship do
    rig.cache.refresh()
    watcher.tick()
    assert _stage(rig, repo_card_id(repo)) is None


def test_t2065_a_push_in_flight_is_left_alone(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="shipping", repo=repo, extra={"repotask": True}))
    watcher = _watcher(rig)
    watcher.tick()
    _close_in_todo(rig, note)  # Ship closes the note before it saves `shipped`
    watcher.tick()
    assert _stage(rig, card) == "shipping"


def test_t2065_an_abandoned_note_is_not_done(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    watcher = _watcher(rig)
    watcher.tick()
    _close_in_todo(rig, note, "abandoned")
    watcher.tick()
    assert _stage(rig, repo_card_id(repo)) is None


def test_t2065_an_older_run_folded_into_the_repo_card_is_left_alone(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "held note", "## one\nx\n\n## two\ny")
    old = f"{note}-0"
    save(rig.run_dir(old), RunState(task_id=old, stage="failed", repo=repo, error="boom"))
    rig.cache.refresh()
    watcher = _watcher(rig)
    watcher.tick()
    watcher.tick()
    assert _stage(rig, old) == "failed"


def test_t2065_a_failed_refresh_changes_nothing(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    watcher = _watcher(rig)
    watcher.tick()
    _close_in_todo(rig, note)
    rig.fake.fail_method("tools/call", 500)
    rig.cache.refresh()
    watcher.tick()
    assert _stage(rig, repo_card_id(repo)) is None


def test_t2065_the_last_parts_of_a_repo_task_whose_cycle_shipped_are_done_by_hand(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "later note", "y")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="shipped", repo=repo, extra={"repotask": True}))
    rig.cache.refresh()
    watcher = _watcher(rig)
    watcher.tick()
    _close_in_todo(rig, note)  # the Done twin of the shipped run replaces the open card
    watcher.tick()
    assert _stage(rig, card) == "done_manually"
