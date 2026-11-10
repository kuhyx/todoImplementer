"""The move from per-section runs to the repo task: nothing is lost, nothing starts per section (T1914)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from repofakes import Rig
from todoimpl.board.state import RunState, save
from todoimpl.merge.service import MergeService
from todoimpl.repotask import files, legacy, prompt
from todoimpl.repotask.ids import repo_card_id
from todoimpl.repotask.legacy import Older
from todoimpl.runner.files import write_json
from todoimpl.runner.scheduler import RunnerError
from todoimpl.service import ItemView
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from pathlib import Path


def older_run(rig: Rig, card: str, stage: str) -> None:
    save(rig.world.root / card, RunState(task_id=card, stage=stage, repo="kuhyx/demo", cost_usd=1.0))
    rig.cache.refresh()


def test_t1914_a_section_run_in_flight_keeps_its_card_and_leaves_the_repo_run(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\n\n## beta\nMake beta.")
    older_run(rig, f"{note}-0", "gate")
    cards = {c["id"]: c for c in rig.backend.board()["tasks"]}
    assert set(cards) == {f"{note}-0", repo_card_id(repo)}
    assert cards[f"{note}-0"]["status"] == "ready_to_ship"  # the old run still waits for its Ship click
    parts = cards[repo_card_id(repo)]["parts"]
    assert sorted((p["id"], p["state"]) for p in parts) == [(f"{note}-0", "held"), (f"{note}-1", "todo")]
    task = rig.backend.task(repo_card_id(repo))
    assert task is not None
    assert "alpha" not in task["body"]
    assert "beta" in task["body"]


def test_the_item_view_rebuilds_the_repo_task_around_a_held_section(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\n\n## beta\nMake beta.")
    older_run(rig, f"{note}-0", "gate")
    view = ItemView(rig.client, rig.cache, rig.world.root)
    task = view.get_task(repo_card_id(repo))
    assert sorted((p.key, p.held) for p in task.parts) == [(f"{note}-0", True), (f"{note}-1", False)]


def test_no_new_section_run_starts(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\n\n## beta\nMake beta.")
    with pytest.raises(RunnerError) as refused:
        rig.sched.start(f"{note}-1")
    assert refused.value.code == "not_found"


def test_a_cancelled_or_shipped_older_run_gives_its_section_back_to_the_repo_run(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\n\n## beta\nMake beta.")
    older_run(rig, f"{note}-0", "gate")
    assert len(rig.backend.board()["tasks"]) == 2
    rig.sched.cancel(f"{note}-0")
    rig.cache.refresh()
    (card,) = rig.backend.board()["tasks"]
    assert [p["state"] for p in card["parts"]] == ["todo", "todo"]
    assert legacy.in_flight(rig.world.root, f"{note}-1") is False  # never started


def test_an_unreadable_older_run_counts_as_in_flight(rig: Rig) -> None:
    write_json(rig.world.root / "abcd1234-0" / "state.json", {"not": "a state"})
    assert legacy.in_flight(rig.world.root, "abcd1234-0") is True
    assert legacy.in_flight(rig.world.root, "nope0000-0") is False


def test_a_shipped_repo_run_is_a_done_card_until_the_repo_has_open_parts_again(rig: Rig) -> None:
    repo = rig.repo()
    card = repo_card_id(repo)
    save(
        rig.world.root / card,
        RunState(
            task_id=card, stage="shipped", repo=repo, extra={"repotask": True, "repotask_title": "demo"}
        ),
    )
    (rig.world.root / "stray-dir").mkdir()
    rig.cache.refresh()
    (done,) = rig.backend.board()["tasks"]
    assert (done["id"], done["title"], done["status"], done["column"]) == (card, "demo", "done", "done")
    rig.note(repo, "new work", "## fresh\nMake it.")
    (open_card,) = rig.backend.board()["tasks"]
    assert (open_card["id"], open_card["status"], open_card["stage"]) == (card, "backlog", None)


def test_the_item_view_serves_a_repo_task_from_its_notes_as_they_are_now(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.")
    card = repo_card_id(repo)
    view = ItemView(rig.client, rig.cache, rig.world.root)
    assert [p.key for p in view.get_task(card).parts] == [f"{note}-0"]
    second = rig.fake.seed(repo, "late note", "Make late.")  # not on the board yet, but in the todo app
    assert {p.note_id for p in view.get_task(card).parts} == {note, second[:8]}
    assert view.abandon(card) is False
    with pytest.raises(TodoError, match="spans several notes"):
        view.update_task(card, status="in progress")
    with pytest.raises(TodoError, match="no part is ticked"):
        view.close_task(card, "ran: ok")
    for key in rig.fake.store.notes:
        rig.fake.store.notes[key].status = "done"
    with pytest.raises(TodoError, match="no open part left"):
        view.get_task(card)


def test_closing_skips_a_ticked_part_whose_section_is_already_gone_and_needs_a_root(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\n\n## beta\nMake beta.")
    card = repo_card_id(repo)
    view = ItemView(rig.client, rig.cache, rig.world.root)
    write_json(rig.run_dir(card) / files.DONE, {"done": [f"{note}-0", f"{note}-1"], "steps": {}})
    full = next(key for key in rig.fake.store.notes if key.startswith(note))
    rig.fake.store.notes[full].text = "demo todos\n\n## alpha\nMake alpha."  # beta vanished after the plan
    view.close_task(card, "ran: ok")
    assert "## [x] alpha" in rig.fake.store.notes[full].text
    rootless = ItemView(rig.client, rig.cache)
    with pytest.raises(TodoError, match=r"no open part left|no part is ticked"):
        rootless.close_task(card, "ran: ok")


def test_merge_suggestions_work_on_sections_not_on_the_repo_card(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\n\n## beta\nMake beta.")
    service = MergeService(rig.client, rig.cache, rig.world.root)
    assert sorted(card.id for card in service.eligible()) == [f"{note}-0", f"{note}-1"]


def test_the_board_context_carries_who_a_queued_run_waits_on(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "demo todos", "## alpha\nMake alpha.")
    card = repo_card_id(repo)
    save(rig.world.root / card, RunState(task_id=card, stage="plan", repo=repo, extra={"repotask": True}))
    rig.sched.locks.acquire(repo, "2d0704cd-7")
    assert rig.sched._admit(card) is False
    assert rig.card(repo)["waits_on"] == "2d0704cd-7"


def test_older_runs_hold_their_section_while_they_work_and_fold_when_they_rest(tmp_path: Path) -> None:
    def stage(name: str, worktree: str | None = None, error: str | None = None) -> Older:
        save(
            tmp_path / "aaaa1111-0",
            RunState(task_id="aaaa1111-0", stage=name, worktree=worktree, error=error),
        )
        return legacy.older(tmp_path, "aaaa1111-0")

    for working in ("spec", "plan", "implement", "live_check", "checks", "shipping", "gate", "paused_limit"):
        assert stage(working) == Older(held=True)
    assert stage("paused_retry").held is True
    assert stage("shipped") == Older()
    assert legacy.older(tmp_path, "nope0000-0") == Older()
    folded = stage("failed", worktree="/w/wt", error="Checks   still\nred")
    assert folded.held is False
    assert (
        folded.note
        == "an earlier run ended failed (branch todo/aaaa1111-0, worktree /w/wt); it said: Checks still red"
    )
    assert stage("spec_wait").note == "an earlier run ended spec_wait (branch todo/aaaa1111-0)"
    assert "cancelled" in stage("cancelled").note


def test_t1914_a_run_that_rests_folds_at_once_and_the_repo_run_is_told_where_its_work_is(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "demo todos", "## alpha\nMake alpha.\n\n## beta\nMake beta.")
    older_run(rig, f"{note}-0", "failed")
    (card,) = rig.backend.board()["tasks"]  # one card for the repo: the failed run no longer keeps its own
    assert sorted(p["state"] for p in card["parts"]) == ["todo", "todo"]
    item = rig.sched.client.get_task(repo_card_id(repo)).item
    text = prompt.addendum(item, rig.run_dir(repo_card_id(repo)))
    assert f"Earlier work on [{note}-0]: an earlier run ended failed (branch todo/{note}-0)" in text
