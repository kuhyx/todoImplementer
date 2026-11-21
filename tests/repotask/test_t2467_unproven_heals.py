"""T2467: a ticked part no passed live row names goes back to the live check, never to kuhy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repofakes import IMPL, PLAN, Rig
from schedfakes import reply
from test_flow import NUDGED, seed, tick_before_start
from todoimpl.repotask import files
from todoimpl.runner import partproof

if TYPE_CHECKING:
    from fake_todo_store import FakeNote

DEFERRED = "- [x] C1 [{a}]: saw alpha\n- [~] C2 [{b}]: after ship: not rerun (heavy build slots)\n\nD: done"
TIMED = "- [x] C2 [{b}]: ran the build, timed -> 21 s"


def _note(rig: Rig, id8: str) -> FakeNote:
    return next(n for key, n in rig.fake.store.notes.items() if key.startswith(id8))


def _refused(rig: Rig, *rounds: str, live: str = DEFERRED) -> tuple[str, str, str]:
    """Ship a card whose live check deferred part b; `rounds` are what the proof rounds write (one each)."""
    _, card, first, second = seed(rig)
    keys = {"a": f"{first}-0", "b": f"{second}-0"}
    report = str(rig.run_dir(card) / "live_check.md")
    turns = [
        ({"_fake": "write", "path": report, "text": text.format(**keys)}, *reply("D: done"))
        for text in rounds
    ]
    rig.script(card, PLAN, IMPL, *NUDGED, reply(live.format(**keys)), *turns)
    tick_before_start(rig, card, *keys.values())
    rig.sched.start(card)
    rig.wait(card, {"gate"})
    rig.sched.ship(card)
    return card, first, second


def test_t2467_an_unproven_part_goes_back_to_the_live_check(rig: Rig) -> None:
    card, first, second = _refused(rig, TIMED)
    st = rig.wait(card, {"gate"})  # checks ran again; the test suite holds the gate
    assert st.error is None
    assert st.extra[partproof.ROUNDS] == 1
    asked = rig.world.calls()[-1]["prompt"]
    assert f"[{second}-0] gamma note" in asked
    assert "after ship: not rerun (heavy build slots)" in asked  # what the deferred row said
    assert (
        f"[{first}-0]" not in asked.split("Repo task:", maxsplit=1)[0]
    )  # the proven part is not asked again
    report = str((st.live_check or {})["report_md"])
    assert "C1" in report  # the proven row is kept: the round wrote only C2
    assert "timed -> 21 s" in report
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    assert "## [x] alpha" in _note(rig, first).text
    assert _note(rig, second).status == "done"
    assert "timed -> 21 s" in str(_note(rig, second).evidence)


def test_t2467_rounds_spent_the_board_unticks_the_part_and_ships_the_rest(rig: Rig) -> None:
    still = "- [~] C2 [{b}]: after ship: cannot be seen now"
    card, first, second = _refused(rig, still, still)
    for _ in range(partproof.MAX_ROUNDS):
        rig.wait(card, {"gate"})
        rig.sched.ship(card)
    st = rig.wait(card, {"shipped"})
    assert st.error is None
    assert files.read(rig.run_dir(card)).done == (f"{first}-0",)
    assert "## [x] alpha" in _note(rig, first).text
    assert _note(rig, second).status != "done"  # open for the next cycle, never closed unproven


def test_t2467_no_proven_part_left_rests_with_retry_as_the_one_step(rig: Rig) -> None:
    none = "- [~] C1 [{a}]: after ship: no\n- [~] C2 [{b}]: after ship: no"
    card, first, second = _refused(rig, none, none, live=none + "\n\nD: done")
    for _ in range(partproof.MAX_ROUNDS):
        rig.wait(card, {"gate"})
        rig.sched.ship(card)
    failed = rig.wait(card, {"failed"})
    assert f"{first}-0" in str(failed.error)
    assert f"{second}-0" in str(failed.error)
    assert str(failed.error).endswith("Retry runs the live check again")
    assert "untick" not in str(failed.error)  # kuhy has no way to untick: never ask him to
    assert files.read(rig.run_dir(card)).done == (f"{first}-0", f"{second}-0")  # Retry finds them ticked


def test_t2467_merged_keeps_old_rows_and_takes_the_new_ones() -> None:
    old = "# live\n- [x] C1 [a-0]: saw a\n- [~] C2 [b-0]: after ship"
    new = "- [x] C2 [b-0]: timed 21 s\n- [x] C3 [b-0]: extra"
    assert partproof.merged(old, new) == "# live\n- [x] C1 [a-0]: saw a\n" + new
    assert partproof.merged(old, "") == old
