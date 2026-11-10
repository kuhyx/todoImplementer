"""Human-made notes sort above Claude-made ones inside every column; the web renders the server order."""

from board_helpers import Note, ctx, run
from todoimpl.board import board
from todoimpl.board.state import RunState, SpecQuestion


def order(notes: list[Note], runs: dict[str, RunState] | None = None) -> list[str]:
    out = board.build_board(notes, runs or {}, ctx(), "b")
    return [t["title"] for t in out["tasks"]]


def test_human_notes_first_inside_a_column() -> None:
    notes = [
        Note(id="aaaaaaaa-0", title="claude one", created_by="claude"),
        Note(id="bbbbbbbb-0", title="human one", created_by="kuhy"),
        Note(id="cccccccc-0", title="claude two", created_by="claude"),
        Note(id="dddddddd-0", title="human two"),
    ]
    assert order(notes) == ["human one", "human two", "claude one", "claude two"]


def test_columns_stay_in_order_and_each_sorts_on_its_own() -> None:
    notes = [
        Note(id="aaaaaaaa-0", title="running claude", created_by="claude"),
        Note(id="bbbbbbbb-0", title="backlog claude", created_by="claude"),
        Note(id="cccccccc-0", title="running human"),
        Note(id="dddddddd-0", title="backlog human"),
    ]
    runs = {
        "aaaaaaaa-0": run(task_id="aaaaaaaa-0", stage="checks"),
        "cccccccc-0": run(task_id="cccccccc-0", stage="checks"),
    }
    assert order(notes, runs) == ["backlog human", "backlog claude", "running human", "running claude"]


def test_human_first_comes_before_the_needs_you_order() -> None:
    notes = [
        Note(id="aaaaaaaa-0", title="claude asks", created_by="claude"),
        Note(id="bbbbbbbb-0", title="human asks"),
    ]
    runs = {
        "aaaaaaaa-0": run(task_id="aaaaaaaa-0", stage="spec_wait", spec_questions=[SpecQuestion("Q1", "t")]),
        "bbbbbbbb-0": run(task_id="bbbbbbbb-0", stage="failed", error="boom"),
    }
    assert order(notes, runs) == ["human asks", "claude asks"]
