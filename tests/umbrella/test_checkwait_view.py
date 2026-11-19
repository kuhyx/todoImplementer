"""An umbrella's line names the longest wait of its children's checks (T2187)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.card import current_line
from todoimpl.board.status import WAITS_FOR, Status
from todoimpl.umbrella.store import RECORD, child_dir
from todoimpl.umbrella.view import overlay

if TYPE_CHECKING:
    from pathlib import Path

KIDS = [{"id": f"umbr0001-{n}", "title": "t", "repo": f"kuhyx/r{n}", "done": False} for n in (1, 2, 3)]


def _umbrella(run_dir: Path, waits: dict[int, float]) -> store.RunState:
    for n, since in waits.items():
        child = store.RunState(task_id=f"umbr0001-{n}", stage="checks")
        child.extra[WAITS_FOR] = {"lock": True, "who": f"card-{n}", "since": since}
        store.save(child_dir(run_dir, f"umbr0001-{n}"), child)
    st = store.RunState(task_id="umbr0001-0", stage="implement")
    st.extra[RECORD] = {"kids": KIDS}
    return st


def test_t2187_b_the_umbrella_line_shows_the_child_check_that_waits_longest(tmp_path: Path) -> None:
    st = _umbrella(tmp_path, {1: 3600.0, 2: 1800.0})  # the third child waits on nothing
    shown = overlay(tmp_path, st, live=True, limit_until=None)
    assert shown.extra[WAITS_FOR]["who"] == "card-2"
    assert WAITS_FOR not in st.extra  # the saved run is not touched
    assert current_line(Status.WORKING, shown, None, 0.0).startswith("⏳🔒 card-2 ")


def test_t2187_b_the_umbrellas_own_wait_and_no_wait_stay_as_they_are(tmp_path: Path) -> None:
    quiet = overlay(tmp_path, _umbrella(tmp_path, {}), live=True, limit_until=None)
    assert WAITS_FOR not in quiet.extra
    own = _umbrella(tmp_path, {1: 100.0})
    own.extra[WAITS_FOR] = {"lock": True, "who": "round-check", "since": 5.0}
    assert overlay(tmp_path, own, live=True, limit_until=None).extra[WAITS_FOR]["who"] == "round-check"
