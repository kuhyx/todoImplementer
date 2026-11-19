"""How the board shows a repo task: part states, one status, the wait on another run, the next cycle."""

from __future__ import annotations

from typing import Any

from contract_lib import validate
from todoimpl.board.card import Context, build_card
from todoimpl.board.parts import NO_ASK, TICKS, parts_of
from todoimpl.board.state import RunState
from todoimpl.repotask.model import Part
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item


def part(key: str, **fields: bool) -> Part:
    note, _, index = key.partition("-")
    return Part(
        key, note, int(index), key, "b", "medium", None, fields.get("human", False), fields.get("held", False)
    )


def card_of(*parts: Part, title: str = "demo", check: str | None = None) -> CardTask:
    item = Item("deadbeef", 0, title, "body", "kuhyx/demo", "todo", check, "kuhy", parts=parts)
    return CardTask("deadbeef-0", title, "body", "kuhyx/demo", "todo", "medium", check, item)


def run(stage: str = "implement", extra: dict[str, Any] | None = None) -> RunState:
    return RunState(task_id="deadbeef-0", stage=stage, extra=extra or {}, cost_usd=2.0)


MIXED = (
    part("aaaa1111-0"),
    part("aaaa1111-1"),
    part("bbbb2222-0", human=True),
    part("cccc3333-0", held=True),
)


def test_each_part_has_one_state_and_the_first_owed_one_is_the_one_being_worked() -> None:
    ticks = {"done": ["aaaa1111-0"], "progress": {"aaaa1111-1": {"done": 1, "total": 2}}}
    shown = parts_of(card_of(*MIXED, part("dddd4444-0")), run(extra={TICKS: ticks}), working=True)
    assert shown is not None
    assert [(p["id"], p["state"]) for p in shown] == [
        ("aaaa1111-0", "done"),
        ("aaaa1111-1", "working"),
        ("bbbb2222-0", "human"),
        ("cccc3333-0", "held"),
        ("dddd4444-0", "todo"),
    ]
    assert shown[1]["steps"] == {"done": 1, "total": 2}
    assert shown[0]["steps"] is None


def test_no_part_is_working_while_the_run_is_not() -> None:
    waiting = parts_of(card_of(part("aaaa1111-0")), None, working=False)
    assert waiting is not None
    assert waiting[0]["state"] == "todo"
    assert parts_of(card_of(), None, working=False) is None


def test_a_card_lists_its_parts_and_validates_against_the_contract() -> None:
    card = build_card(card_of(*MIXED), run(), Context(live=frozenset({"deadbeef-0"}), now=1.0))
    validate("common", card, "task_card")
    assert card["status"] == "working"
    assert [p["state"] for p in card["parts"]] == ["working", "todo", "human", "held"]


def test_a_section_card_has_no_parts_key() -> None:
    section = CardTask(
        "aaaa1111-0",
        "t",
        "b",
        "kuhyx/demo",
        "todo",
        "medium",
        None,
        Item("aaaa1111", 0, "t", "b", "kuhyx/demo", "todo", None),
    )
    assert "parts" not in build_card(section, None, Context())


def test_a_shipped_cycle_with_parts_left_is_backlog_again_and_keeps_its_cost() -> None:
    card = build_card(card_of(part("aaaa1111-0")), run("shipped"), Context(now=1.0))
    validate("common", card, "task_card")
    assert (card["status"], card["stage"], card["cost_usd"]) == ("backlog", None, 2.0)
    assert [a["id"] for a in card["actions"]] == ["start", "wont", "done-manually"]
    assert card["actions"][0]["enabled"] is True


def test_the_card_of_a_shipped_section_is_still_done() -> None:
    section = CardTask(
        "aaaa1111-0",
        "t",
        "b",
        "kuhyx/demo",
        "done",
        "medium",
        None,
        Item("aaaa1111", 0, "t", "b", "kuhyx/demo", "done", None),
    )
    assert build_card(section, run("shipped"), Context())["status"] == "done"


def test_a_repo_with_only_human_work_is_yours_and_cannot_be_started() -> None:
    card = build_card(card_of(part("bbbb2222-0", human=True), title="demo"), None, Context())
    assert (card["status"], card["assignee"]) == ("yours", "human")
    start, wont, _ = card["actions"]
    assert (start["id"], start["enabled"], wont["id"]) == ("start", False, "wont")
    assert "MANUAL WORK REQUIRED" in str(start["reason"])


def test_a_queued_card_names_the_run_it_waits_on_and_a_working_one_does_not() -> None:
    queued = build_card(card_of(part("aaaa1111-0")), run("plan"), Context(waits={"deadbeef-0": "2d0704cd-7"}))
    validate("common", queued, "task_card")
    assert (queued["status"], queued["waits_on"]) == ("queued", "2d0704cd-7")
    working = build_card(
        card_of(part("aaaa1111-0")),
        run("plan"),
        Context(live=frozenset({"deadbeef-0"}), waits={"deadbeef-0": "2d0704cd-7"}),
    )
    assert "waits_on" not in working
    assert "waits_on" not in build_card(card_of(part("aaaa1111-0")), run("plan"), Context())


def test_t1925_a_card_waiting_on_its_repos_run_shows_only_the_lock_not_a_stage_line() -> None:
    queued = build_card(card_of(part("aaaa1111-0")), run("plan"), Context(waits={"deadbeef-0": "2d0704cd-7"}))
    assert queued["current"] == ""  # "waiting to continue plan" read as if the plan had started
    assert (
        build_card(card_of(part("aaaa1111-0")), run("plan"), Context())["current"]
        == "waiting to continue plan"
    )


def test_t1951_a_manual_card_with_a_repo_says_what_kuhy_must_do() -> None:
    body = "Convert Home to a grid.\nNeeds: kuhy `! textgate approve` for the tile captions\n"
    ask = Part(
        "bbbb2222-0", "bbbb2222", 0, "MANUAL WORK REQUIRED: fit", body, "medium", None, human=True, held=False
    )
    bare = Part(
        "cccc3333-0",
        "cccc3333",
        0,
        "MANUAL WORK REQUIRED: x",
        "no ask",
        "medium",
        None,
        human=True,
        held=False,
    )
    assert build_card(card_of(ask), None, Context())["current"] == (
        "yours: kuhy `! textgate approve` for the tile captions"
    )
    assert build_card(card_of(bare), None, Context())["current"] == NO_ASK
