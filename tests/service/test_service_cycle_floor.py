"""A reopened repo card shows only its current cycle: activity, peer, stages, plan and cost (T2479, T2480)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from contract_lib import validate
from servicefakes import Rig
from todoimpl.board.cyclefloor import AT, COST, SEQ
from todoimpl.board.state import RunState, run_dir
from todoimpl.repotask.cycle import new_cycle
from todoimpl.runner.files import write_json

if TYPE_CHECKING:
    from pathlib import Path

PART = "## Fix the parser\nHandle empty input.\ndone_check: true"
STAGES = [
    {"stage": "implement", "started": 1.0, "ended": 2.0},
    {"stage": "shipped", "started": 3.0, "ended": None},
]


def _events(directory: Path, count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "activity", "at": float(n), "kind": "text", "text": f"l{n}", "seq": n}
        for n in range(1, count + 1)
    ]
    lines = [json.dumps(r) for r in rows]
    (directory / "events.jsonl").write_text(
        "\n".join([*lines, '{"torn'][: count + 1]) + "\n", encoding="utf-8"
    )


def _peer(card: str, at: float, text: str) -> dict[str, Any]:
    return {"id": f"{card}.{int(at):04x}", "card": card, "at": at, "text": text, "state": "delivered"}


def _seqs(rig: Rig, card: str) -> list[int]:
    return [int(e["seq"]) for e in rig.backend.subscribe(card) if e.get("type") == "activity"]


def test_t2479_a_new_cycle_records_where_it_starts(tmp_path: Path) -> None:
    _events(tmp_path, 3)
    st = RunState(task_id="deadbeef-0", stage="shipped", cost_usd=2.5, extra={"repotask": True})
    new_cycle(st, tmp_path, 100.0)
    assert (st.extra[AT], st.extra[SEQ], st.extra[COST]) == (100.0, 3, 2.5)
    validate("state", st.to_dict())
    fresh = RunState(task_id="deadbeef-0", stage="shipped")
    new_cycle(fresh, tmp_path / "none", 5.0)
    assert fresh.extra[SEQ] == 0


def test_t2479_a_card_in_its_next_cycle_shows_only_this_cycles_rows(rig: Rig) -> None:
    card = rig.note(body=PART)
    directory = run_dir(rig.root, card)
    _events(directory, 10)
    rig.scheduler.events = [
        json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()[:10]
    ]
    write_json(directory / "peer.json", [_peer(card, 5.0, "old"), _peer(card, 50.0, "new")])
    stages = [*STAGES, {"stage": "spec", "started": 40.0, "ended": None}]
    floor = {"repotask": True, "cycle": 2, AT: 40.0, SEQ: 7, COST: 1.5}
    rig.run(card, "spec", stages=stages, extra=floor, cost_usd=2.0)
    detail = rig.backend.task(card)
    assert detail is not None
    assert [s["started"] for s in detail["stages"]] == [40.0]
    assert [m["text"] for m in detail["peer"]] == ["new"]
    assert detail["card"]["cost_usd"] == 0.5  # T2480: this cycle's spend; the usage page keeps the total
    assert (rig.backend.floor(card), _seqs(rig, card)) == (7, [8, 9, 10])


def test_t2479_a_card_resting_between_cycles_shows_nothing_of_the_shipped_one(rig: Rig) -> None:
    card = rig.note(body=PART)
    directory = run_dir(rig.root, card)
    _events(directory, 10)
    rig.scheduler.events = [
        json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()[:10]
    ]
    (directory / "plan.md").write_text("# Plan of the shipped cycle\n", encoding="utf-8")
    write_json(directory / "peer.json", [_peer(card, 5.0, "old")])
    rig.run(
        card, "shipped", stages=STAGES, extra={"repotask": True}, cost_usd=2.0, worktree="/w", session_id="s"
    )
    detail = rig.backend.task(card)
    assert detail is not None
    assert (detail["card"]["status"], detail["card"]["cost_usd"]) == ("backlog", 0.0)
    shown = (detail["plan_md"], detail["stages"], detail["diff"], detail["worktree"], "peer" in detail)
    assert shown == (None, [], None, None, False)
    assert (rig.backend.floor(card), _seqs(rig, card)) == (10, [])


def test_t2479_a_card_that_never_cycled_shows_everything(rig: Rig) -> None:
    card = rig.note(body=PART)
    directory = run_dir(rig.root, card)
    write_json(directory / "peer.json", [_peer(card, 5.0, "old")])
    rig.run(card, "implement", stages=STAGES[:1], extra={"repotask": True})
    detail = rig.backend.task(card)
    assert detail is not None
    assert ([m["text"] for m in detail["peer"]], len(detail["stages"]), rig.backend.floor(card)) == (
        ["old"],
        1,
        0,
    )
    assert rig.backend.floor("ffff0000-0") == 0


def test_t2480_a_reopened_card_costs_only_this_cycle(rig: Rig) -> None:
    card = rig.note(body=PART)
    rig.run(card, "implement", extra={"repotask": True, "cycle": 3, COST: 4.0}, cost_usd=4.25)
    assert rig.card(card)["cost_usd"] == 0.25
    rig.run(card, "shipped", extra={"repotask": True, COST: 4.0}, cost_usd=4.25)
    assert rig.card(card)["cost_usd"] == 0.0  # between cycles: the next one has spent nothing


def test_t2479_a_feed_with_no_activity_seq_has_floor_zero(tmp_path: Path) -> None:
    (tmp_path / "events.jsonl").write_text('{"type": "stage"}\n[1]\n', encoding="utf-8")
    st = RunState(task_id="deadbeef-0", stage="shipped")
    new_cycle(st, tmp_path, 5.0)
    assert st.extra[SEQ] == 0
