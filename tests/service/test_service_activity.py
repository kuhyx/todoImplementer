"""The board reads a running card's last activity from its events.jsonl, ignoring board lines (T2404)."""

from __future__ import annotations

import json

from servicefakes import Rig
from todoimpl.board.state import run_dir

LATE = 4_000_000_000.0  # far after any state.json save


def _events(rig: Rig, tid: str, *rows: dict[str, object]) -> None:
    directory = run_dir(rig.root, tid)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")


def test_t2404_the_board_card_shows_the_last_real_activity_of_a_running_card(rig: Rig) -> None:
    tid = rig.note(repo=None)
    rig.run(tid, "implement")
    rig.scheduler.live = {tid}
    _events(
        rig,
        tid,
        {"type": "activity", "kind": "tool", "at": LATE},
        {"type": "activity", "kind": "system", "at": LATE + 99},
    )
    assert rig.card(tid)["updated"] == LATE


def test_t2404_a_card_that_is_not_running_does_not_read_its_events(rig: Rig) -> None:
    tid = rig.note(repo=None)
    rig.run(tid, "failed", updated=5.0)
    _events(rig, tid, {"type": "activity", "kind": "tool", "at": LATE})
    assert rig.card(tid)["updated"] == 5.0
