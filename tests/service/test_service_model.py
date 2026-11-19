"""A Send-to-Claude note that names a model pins it instead of reaching the session (T2215)."""

from typing import Any

import pytest
from servicefakes import Rig
from todoimpl.board.state import run_dir
from todoimpl.lessons import load_lessons
from todoimpl.runner import modelswitch
from todoimpl.runner.files import write_json

FABLE = "claude-fable-5-2"


def test_t2215_a_model_note_pins_the_model_and_drafts_no_lesson_at_the_gate(rig: Rig) -> None:
    spawned: list[Any] = []
    rig.backend.spawn = spawned.append
    rig.run("t1", "gate")
    rig.backend.send("t1", "run it on claude fable 5.2")
    rig.backend.send("t1", "default")
    assert rig.scheduler.calls == [("set_model", "t1", FABLE), ("set_model", "t1", "default")]
    assert spawned == []
    assert load_lessons(run_dir(rig.root, "t1")) == []


@pytest.mark.parametrize("text", ["run it on gpt 5", "use sonnet 5.5 for the classifier"])
def test_t2215_an_unknown_model_is_a_normal_note(rig: Rig, text: str) -> None:
    rig.backend.send("t1", text)
    assert rig.scheduler.calls == [("send", "t1", text)]


def test_t2215_the_picker_click_pins_the_model(rig: Rig) -> None:
    rig.backend.model("t1", model=FABLE)
    assert rig.scheduler.calls == [("set_model", "t1", FABLE)]


def test_t2218_a_pick_the_cut_drive_has_not_settled_shows_at_once(rig: Rig) -> None:
    tid = rig.note()
    rig.run(tid, "cancelled", session_id="s", worktree="/w")  # the cut drive saved this; after_drive is next
    write_json(run_dir(rig.root, tid) / modelswitch.FILE, {"model": FABLE, "stage": "implement"})
    card = rig.card(tid)
    assert card["status"] != "cancelled"
    assert card["model"] == FABLE
    assert next(a for a in card["actions"] if a["id"] == "model")["value"] == FABLE


def test_t2221_a_model_command_with_more_words_pins_and_sends_the_rest(rig: Rig) -> None:
    spawned: list[Any] = []
    rig.backend.spawn = spawned.append
    rig.run("t1", "gate")
    rig.backend.send("t1", "run it on claude fable 5.2\nTry three bolder logos")
    assert rig.scheduler.calls == [("set_model", "t1", FABLE, "Try three bolder logos")]
    assert spawned == []
