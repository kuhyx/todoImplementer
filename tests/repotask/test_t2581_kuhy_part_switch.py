"""T2581: a part kuhy adds while the run works an automatic one is the very next turn's work.

The drive read the card once, so kuhy's new part stayed out of every prompt (and its tick was refused) until
the next cycle. Each implement turn now re-reads the parts, lists kuhy's first, tells the session to switch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from repofakes import LIVE, PLAN, Rig
from schedfakes import reply
from todoimpl.errors import ticket
from todoimpl.errors.record import AppError
from todoimpl.repotask import files
from todoimpl.repotask.ids import repo_card_id

if TYPE_CHECKING:
    from pathlib import Path

RECORD = AppError("demo", "kuhyx/demo", "07626036aa", "crash", "boom", 1, "2026-11-27T00:00:00+00:00",
                  "2026-11-27T00:00:00+00:00", 0)  # fmt: skip
SLOW = ({"_fake": "sleep", "sec": 2}, {"_fake": "result", "text": "worked on the ticket\n\nD: done"})


def _prompt(rig: Rig, n: int) -> str:
    rig.until(lambda: len(rig.world.calls()) > n)
    return str(rig.world.calls()[n]["prompt"])


def _known(run_dir: Path) -> set[str]:
    return files.known(run_dir)


def test_t2581_kuhys_part_added_mid_run_comes_first_on_the_next_turn(rig: Rig) -> None:
    repo = rig.repo()
    auto = rig.note(repo, "demo errors", f"## {ticket.title(RECORD)}\n{ticket.body(RECORD)}")
    card = repo_card_id(repo)
    rig.script(card, PLAN, SLOW, reply("switched\n\nD: done"), reply("still\n\nD: done"), LIVE)
    rig.sched.start(card)
    assert f"1. [{auto}-0]" in _prompt(rig, 1)  # the implement turn, working the ticket
    kuhy = rig.note(repo, "kuhy fix", "Make the kuhy fix.")
    nxt = _prompt(rig, 2)
    assert f"1. [{kuhy}-0] kuhy fix" in nxt
    assert f"2. [{auto}-0]" in nxt
    assert f"kuhy added [{kuhy}-0] kuhy fix while you worked" in nxt
    assert f"{kuhy}-0" in _known(rig.run_dir(card))  # its tick is accepted now
    third = _prompt(rig, 3)
    assert "kuhy added" not in third  # the switch note is said once
    rig.sched.cancel(card)
