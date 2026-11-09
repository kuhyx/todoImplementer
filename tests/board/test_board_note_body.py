"""note_body: the note text the board took at Start survives a later rewrite or close of the source note."""

import json
from pathlib import Path

from board_helpers import Note, ctx, run
from contract_lib import validate
from todoimpl.board import board, state
from todoimpl.board.state import NOTE_BODY_MAX, RunState


def test_t1862_note_body_round_trips_and_validates(tmp_path: Path) -> None:
    original = run(note_body="taken at pickup")
    state.save(tmp_path, original)
    assert state.load(tmp_path) == original
    assert original.to_dict()["note_body"] == "taken at pickup"
    validate("state", original.to_dict())


def test_t1862_absent_note_body_stays_absent() -> None:
    assert "note_body" not in run().to_dict()
    assert RunState.from_dict(run().to_dict()).note_body is None


def test_t1862_an_oversized_note_body_is_cut_not_refused(tmp_path: Path) -> None:
    raw = run().to_dict() | {"note_body": "x" * (NOTE_BODY_MAX + 7)}
    (tmp_path / "state.json").write_text(json.dumps(raw), encoding="utf-8")
    loaded = state.load(tmp_path)
    assert loaded is not None
    assert loaded.note_body == "x" * NOTE_BODY_MAX
    validate("state", loaded.to_dict())


def test_t1862_task_payload_shows_the_body_taken_at_pickup(tmp_path: Path) -> None:
    rewritten = Note(body="rewritten later")
    out = board.build_task(rewritten, run(note_body="taken at pickup"), tmp_path, ctx())
    assert out["body"] == "taken at pickup"
    validate("task", out)
    assert board.build_task(rewritten, run(), tmp_path, ctx())["body"] == "rewritten later"
