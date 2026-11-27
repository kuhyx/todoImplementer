"""T2580: runs that wait in the engine's queue start kuhy's cards before automatic ones."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board.state import RunState
from todoimpl.repotask import files, lane
from todoimpl.repotask.model import Part
from todoimpl.repotask.start import prepare
from todoimpl.runner.files import write_json
from todoimpl.todo_mcp.items import Item

if TYPE_CHECKING:
    from pathlib import Path

TICKET = "Fix it.\nError-Signature: kartka:abc"


def _lane(root: Path, card: str, name: str | None) -> None:
    (root / card).mkdir(parents=True)
    if name is not None:
        write_json(root / card / files.PRIORITY, {"priority": "medium", "lane": name})


def test_t2580_queue_order_puts_kuhy_first_and_keeps_fifo_inside_a_lane(tmp_path: Path) -> None:
    for card, name in (("a-0", lane.APP), ("b-0", lane.BOARD), ("c-0", None), ("d-0", lane.KUHY)):
        _lane(tmp_path, card, name)
    write_json(tmp_path / "e-0" / files.PRIORITY, {"lane": "nonsense"})
    assert files.queue_order(tmp_path, ["a-0", "b-0", "c-0", "d-0", "e-0"]) == [
        "c-0",
        "d-0",
        "e-0",
        "b-0",
        "a-0",
    ]


def test_t2580_snapshot_writes_the_lane_and_low_for_an_app_note(tmp_path: Path) -> None:
    files.snapshot(tmp_path, Item("abcd1234", 0, "kartka", TICKET, "kuhyx/kartka", "todo", None), "high")
    assert (files.priority(tmp_path), files.lane_rank(tmp_path)) == ("low", lane.rank(lane.APP))


def test_t2580_start_writes_the_lane_before_the_drive(tmp_path: Path) -> None:
    part = Part("abcd1234-0", "abcd1234", 0, "fix", TICKET, "low", None, human=False, held=False)
    item = Item("abcd1234", 0, "kartka", TICKET, "kuhyx/kartka", "todo", None, parts=(part,))
    prepare(RunState(task_id="x-0", stage="spec", started_at=0.0), item, tmp_path / "x-0", 0.0)
    assert (files.priority(tmp_path / "x-0"), files.lane_rank(tmp_path / "x-0")) == ("low", 2)
