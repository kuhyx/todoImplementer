"""kuhy's notes belong to their cycle (T2432): a shipped cycle's notes are not re-sent to the next one."""

from __future__ import annotations

from typing import Any

from repofakes import IMPL, LIVE, PLAN, Rig
from schedfakes import reply
from todoimpl.board import state as store
from todoimpl.repotask import files
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.files import write_json

PLAIN = "## Fix the parser\nHandle empty input.\ndone_check: true"
SECOND = "## Fix the printer\nHandle empty output.\ndone_check: true"
OLD = "huh? No it should be an unlock"


def prompts(rig: Rig) -> list[str]:
    return [str(c["prompt"]) for c in rig.world.calls()]


def test_t2432_a_new_cycle_does_not_resend_the_last_cycles_notes(rig: Rig) -> None:
    repo = rig.repo()
    first = rig.note(repo, "plain note", PLAIN)
    card = repo_card_id(repo)
    write_json(rig.run_dir(card) / files.DONE, {"done": [f"{first}-0"], "steps": {}})
    rig.script(card, PLAN, IMPL, LIVE)
    rig.sched.start(card)
    rig.wait(card, {"gate"})
    rig.sched.ship(card)
    st = rig.wait(card, {"shipped"})
    st.extra["notes"] = [OLD]  # kuhy's note of cycle 1, taken in by one of its turns
    store.save(rig.run_dir(card), st)
    seen = len(rig.world.calls())
    rig.note(repo, "printer note", SECOND)  # new work: same card, next cycle (Start clears the ticks)
    nudges = (reply("one part is left\n\nD: done"), reply("still one\n\nD: done"))
    rig.script(card, PLAN, IMPL, *nudges, LIVE)
    rig.sched.start(card)
    again = rig.wait(card, {"gate"})
    cycle_two: list[Any] = prompts(rig)[seen:]
    assert cycle_two
    assert not [p for p in cycle_two if OLD in p]
    assert again.extra["cycle"] == 2
    assert again.extra["cycle_seq"] >= 0
    assert again.extra["cycle_at"] > 0  # the Scheduler's clock marks where cycle 2 starts (T2479)
    assert OLD not in again.extra.get("notes", [])
