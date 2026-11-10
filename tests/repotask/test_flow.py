"""A repo task end to end: one run over several parts, ticks, Ship closing only the ticked ones (T1912)."""

from __future__ import annotations

import pytest
from contract_lib import validate
from repofakes import IMPL, LIVE, PLAN, Rig
from runnerfakes import sh
from schedfakes import reply
from todoimpl.repotask import files
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.files import write_json
from todoimpl.runner.scheduler import RunnerError

NUDGED = (reply("one part is left\n\nD: done"), reply("still one\n\nD: done"))  # the two nudge turns
BODY_A = "## alpha\nMake alpha.\ndone_check: true\n\n## beta\nMake beta.\ndone_check: true"


def seed(rig: Rig) -> tuple[str, str, str, str]:
    """Two notes of one repo (three parts); return (repo, card, note A, note B)."""
    repo = rig.repo()
    first = rig.note(repo, "demo todos", BODY_A)
    second = rig.note(repo, "gamma note", "Make gamma.\ndone_check: true")
    return repo, repo_card_id(repo), first, second


def tick_before_start(rig: Rig, card: str, *keys: str) -> None:
    """Pre-write Claude's ticks (the fake claude cannot run the tick command)."""
    write_json(rig.run_dir(card) / files.DONE, {"done": list(keys), "steps": {}})


def test_t1912_ship_closes_only_the_ticked_parts_and_names_their_notes(rig: Rig) -> None:
    repo, card, first, second = seed(rig)
    rig.script(card, PLAN, IMPL, *NUDGED, LIVE)
    tick_before_start(rig, card, f"{first}-0", f"{second}-0")
    rig.sched.start(card)
    st = rig.wait(card, {"gate"})
    validate("state", st.to_dict())
    assert st.extra["repotask"] is True
    prompt = rig.world.calls()[0]["prompt"]
    assert "Repo task: ONE run" in prompt
    assert f"[{first}-0] alpha" in prompt
    assert f"[{second}-0] gamma note" in prompt
    assert rig.backend.board()["tasks"][0]["status"] == "ready_to_ship"
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    notes = rig.fake.store.notes
    text_a = next(n.text for key, n in notes.items() if key.startswith(first))
    assert "## [x] alpha" in text_a
    assert "## [x] beta" not in text_a
    assert next(n.status for key, n in notes.items() if key.startswith(first)) == "todo"
    assert next(n.status for key, n in notes.items() if key.startswith(second)) == "done"
    log = sh(rig.world.tmp / "remotes" / "demo.git", "git", "log", "-1", "--format=%B", "main")
    assert f"Todo: {first}" in log
    assert f"Todo: {second}" in log
    assert log.split("\n")[0] in ("alpha", "gamma note")  # the first ticked part names the commit
    rig.cache.refresh()
    again = rig.card(repo)
    assert (again["status"], [p["title"] for p in again["parts"]], again["stage"]) == (
        "backlog",
        ["beta"],
        None,
    )
    assert again["cost_usd"] > 0


def test_start_after_a_shipped_cycle_begins_the_next_one(rig: Rig) -> None:
    _, card, first, _ = seed(rig)
    rig.script(card, PLAN, IMPL, *NUDGED, LIVE)
    tick_before_start(rig, card, f"{first}-0")
    rig.sched.start(card)
    rig.wait(card, {"gate"})
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    rig.cache.refresh()
    rig.script(card, PLAN)
    rig.sched.start(card, auto_ship=True)
    st = rig.state(card)
    assert (st.extra["cycle"], st.worktree, st.auto_ship) == (2, None, True)
    assert files.read(rig.run_dir(card)) == files.Ticks()
    rig.wait(card, {"gate", "failed"})


def test_unticked_parts_are_asked_for_twice_and_a_ship_with_none_ticked_is_refused(rig: Rig) -> None:
    _, card, _, _ = seed(rig)
    rig.script(card, PLAN, IMPL, reply("still working\n\nD: done"), reply("again\n\nD: done"), LIVE)
    rig.sched.start(card)
    st = rig.wait(card, {"gate"})
    assert st.extra["part_nudges"] == 2
    nudged = [c for c in rig.world.calls() if "Parts not ticked" in str(c["prompt"])]
    assert len(nudged) == 2
    rig.sched.ship(card)
    failed = rig.wait(card, {"failed"})
    assert "No part is ticked" in str(failed.error)
    assert failed.extra["failed_stage"] == "shipping"


def test_a_repo_with_only_human_work_cannot_be_started(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "MANUAL WORK REQUIRED: rotate the key", "do it by hand")
    with pytest.raises(RunnerError, match="MANUAL WORK REQUIRED"):
        rig.sched.start(repo_card_id(repo))


def test_a_held_only_repo_has_nothing_for_the_run(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "MANUAL WORK REQUIRED: rotate the key", "do it by hand")
    other = rig.note(repo, "held note", "## held\nx")
    write_json(rig.run_dir(f"{other}-0") / "state.json", {"x": 1})  # unreadable as a run: counts as in flight
    rig.cache.refresh()
    card = rig.card(repo)
    assert card["title"].startswith("MANUAL WORK REQUIRED")
    assert [p["state"] for p in card["parts"]] == ["held", "human"]
    assert card["status"] == "yours"
