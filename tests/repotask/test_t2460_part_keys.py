"""T2460: on a card with several parts each criterion names its part; Ship closes a part on its own rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repofakes import IMPL, PLAN, Rig
from schedfakes import reply
from test_files import part
from test_flow import seed, tick_before_start
from todoimpl.repotask import files, prompt
from todoimpl.runner.approval import kuhy_ids
from todoimpl.runner.parsing import for_part, parse_criteria, parse_live
from todoimpl.runner.shipstage import live_summary
from todoimpl.todo_mcp.items import Item

if TYPE_CHECKING:
    from pathlib import Path

    from fake_todo_store import FakeNote

TAG = "`Cn [<part key>]: ...`"


def _item(*keys: str) -> Item:
    return Item("deadbeef", 0, "demo", "b", "kuhyx/demo", "todo", None, "kuhy", parts=tuple(map(part, keys)))


def test_t2460_live_rows_and_plan_criteria_carry_the_part_key() -> None:
    rows = parse_live("- [x] C1 [aaaa1111-0]: ran -> saw\n- [ ] **C2 [bbbb2222-0]**: no\n- [x] C3: plain")
    assert [(r["criterion"], r["part"], r["done"], r["note"]) for r in rows] == [
        ("C1", "aaaa1111-0", True, "ran -> saw"),
        ("C2", "bbbb2222-0", False, "no"),
        ("C3", None, True, "plain"),
    ]
    plan = "## Acceptance criteria\nC1 [aaaa1111-0]: I do X, I see Y\n"
    plan += "C2 [bbbb2222-0]: (kuhy) kuhy approves it"
    assert parse_criteria(plan) == ["I do X, I see Y", "(kuhy) kuhy approves it"]
    assert kuhy_ids(parse_criteria(plan)) == ["C2"]


def test_t2460_only_a_card_with_several_parts_asks_for_keyed_criteria(tmp_path: Path) -> None:
    assert TAG in prompt.addendum(_item("aaaa1111-0", "bbbb2222-0"), tmp_path)
    assert TAG not in prompt.addendum(_item("aaaa1111-0"), tmp_path)
    parts = (part("aaaa1111-0"), part("bbbb2222-0", human=True))
    lone = Item("d", 0, "d", "b", "r", "todo", None, parts=parts)
    assert not files.keyed(lone)
    assert TAG not in prompt.addendum(lone, tmp_path)


def test_t2460_each_part_keeps_only_its_own_live_rows() -> None:
    rows = live_summary("- [x] C1 [a-0]: saw a\n- [x] C2 [b-0]: saw b")
    text = f"Shipped abc.\n{rows}\ntests `t` exit 0:"
    assert "live C1 [a-0]: done (saw a)" in text
    assert for_part(text, "a-0") == "Shipped abc.\nlive C1 [a-0]: done (saw a)\ntests `t` exit 0:"
    assert for_part(text, "b-0") == "Shipped abc.\nlive C2 [b-0]: done (saw b)\ntests `t` exit 0:"
    assert live_summary("- [x] C1: saw") == "live C1: done (saw)"  # untagged rows read as before


def _ship(rig: Rig, live: str) -> tuple[str, str, str]:
    """Ship a three-part card with both notes' first parts ticked; `live` names them `{a}` and `{b}`."""
    _, card, first, second = seed(rig)
    keyed = {"_fake": "result", "text": live.format(a=f"{first}-0", b=f"{second}-0")}
    rig.script(card, PLAN, IMPL, reply("one left\n\nD: done"), reply("still one\n\nD: done"), (keyed,))
    tick_before_start(rig, card, f"{first}-0", f"{second}-0")
    rig.sched.start(card)
    rig.wait(card, {"gate"})
    rig.sched.ship(card)
    return card, first, second


def _note(rig: Rig, id8: str) -> FakeNote:
    return next(n for key, n in rig.fake.store.notes.items() if key.startswith(id8))


def test_t2460_ship_refuses_a_ticked_part_no_passed_criterion_names(rig: Rig) -> None:
    card, first, second = _ship(rig, "- [x] C1 [{a}]: saw alpha\n- [~] C2 [{b}]: needs phone: x\n\nD: done")
    held = rig.wait(card, {"gate"})  # refused: the live check got the part back (T2467), nothing closed
    assert f"[{second}-0]" in rig.world.calls()[-1]["prompt"]
    assert (held.error, held.ship) == (None, None)
    assert "## [x]" not in _note(rig, first).text
    assert _note(rig, second).status != "done"


def test_t2460_each_closed_note_holds_only_its_own_evidence(rig: Rig) -> None:
    card, first, second = _ship(rig, "- [x] C1 [{a}]: saw alpha\n- [x] C2 [{b}]: saw gamma\n\nD: done")
    rig.wait(card, {"shipped"})
    text_a = _note(rig, first).text
    assert ("## [x] alpha" in text_a, "saw alpha" in text_a, "saw gamma" in text_a) == (True, True, False)
    assert "Shipped " in text_a
    evidence_b = str(_note(rig, second).evidence)
    seen = ("saw gamma" in evidence_b, "saw alpha" in evidence_b, "Shipped " in evidence_b)
    assert seen == (True, False, True)
