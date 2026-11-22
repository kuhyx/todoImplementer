"""The parts files in a run dir, the tick command, the prompt addendum and the next-cycle reset."""

from __future__ import annotations

import runpy
import sys
from typing import TYPE_CHECKING, Any

import pytest
from todoimpl.board.parts import TICKS
from todoimpl.board.state import RunState
from todoimpl.repotask import files, prompt, tick
from todoimpl.repotask.cycle import new_cycle
from todoimpl.repotask.model import Part
from todoimpl.repotask.start import prepare
from todoimpl.todo_mcp.items import Item

if TYPE_CHECKING:
    from pathlib import Path


def part(key: str, **fields: object) -> Part:
    base: dict[str, Any] = {
        "title": key,
        "body": "b",
        "priority": "medium",
        "done_check": None,
        "human": False,
        "held": False,
    }
    base.update(fields)
    note, _, index = key.partition("-")
    return Part(key, note, int(index), **base)


PARTS = (
    part("aaaa1111-0"),
    part("aaaa1111-1"),
    part("bbbb2222-0", human=True),
    part("cccc3333-0", held=True),
)
ITEM = Item("deadbeef", 0, "demo", "body", "kuhyx/demo", "todo", None, "kuhy", parts=PARTS)


def test_snapshot_lists_the_drives_parts_and_only_actionable_ones_can_be_ticked(tmp_path: Path) -> None:
    files.snapshot(tmp_path, ITEM)
    assert files.known(tmp_path) == {"aaaa1111-0", "aaaa1111-1"}
    with pytest.raises(files.PartError, match="not a part of this run"):
        files.mark_done(tmp_path, "bbbb2222-0")  # human work
    with pytest.raises(files.PartError, match="not a part of this run"):
        files.mark_done(tmp_path, "cccc3333-0")  # held by an older run


def test_ticks_are_kept_once_and_listed_in_work_order(tmp_path: Path) -> None:
    files.snapshot(tmp_path, ITEM)
    files.mark_done(tmp_path, "aaaa1111-1")
    files.mark_done(tmp_path, "aaaa1111-1")
    assert files.read(tmp_path).done == ("aaaa1111-1",)
    assert [p.key for p in files.ticked(tmp_path, ITEM)] == ["aaaa1111-1"]
    assert [p.key for p in files.unticked(tmp_path, ITEM)] == ["aaaa1111-0"]


def test_a_missing_or_garbled_file_reads_as_no_ticks(tmp_path: Path) -> None:
    assert files.read(tmp_path) == files.Ticks()
    (tmp_path / files.DONE).write_text("[1]", encoding="utf-8")
    assert files.read(tmp_path) == files.Ticks()


def test_a_split_part_needs_all_its_steps_before_it_can_be_ticked(tmp_path: Path) -> None:
    files.snapshot(tmp_path, ITEM)
    files.split(tmp_path, "aaaa1111-0", ["one", "two"])
    files.split(tmp_path, "aaaa1111-0", ["two", "three"])  # a repeated title is kept once
    assert files.read(tmp_path).progress("aaaa1111-0") == {"done": 0, "total": 3}
    assert files.read(tmp_path).progress("aaaa1111-1") is None
    with pytest.raises(files.PartError, match="open steps: one, two, three"):
        files.mark_done(tmp_path, "aaaa1111-0")
    for number in (1, 2, 3):
        files.step_done(tmp_path, "aaaa1111-0", number)
    assert files.read(tmp_path).progress("aaaa1111-0") == {"done": 3, "total": 3}
    files.mark_done(tmp_path, "aaaa1111-0")
    with pytest.raises(files.PartError, match="has 3 steps, no step 4"):
        files.step_done(tmp_path, "aaaa1111-0", 4)


def test_the_overlay_hands_the_ticks_to_the_card_and_leaves_other_runs_alone(tmp_path: Path) -> None:
    files.snapshot(tmp_path, ITEM)
    files.split(tmp_path, "aaaa1111-0", ["one"])
    files.mark_done(tmp_path, "aaaa1111-1")
    plain = RunState(task_id="x-0", stage="implement")
    assert files.overlay(tmp_path, plain) is plain
    marked = RunState(task_id="x-0", stage="implement", extra={"repotask": True})
    got = files.overlay(tmp_path, marked)
    assert got.extra[TICKS] == {"done": ["aaaa1111-1"], "progress": {"aaaa1111-0": {"done": 0, "total": 1}}}
    assert TICKS not in marked.extra


def test_the_commit_names_the_ticked_parts_notes(tmp_path: Path) -> None:
    assert files.commit_identity(ITEM, tmp_path) == ("demo", ["deadbeef"])  # nothing ticked yet
    files.snapshot(tmp_path, ITEM)
    files.mark_done(tmp_path, "aaaa1111-1")
    assert files.commit_identity(ITEM, tmp_path) == ("aaaa1111-1", ["aaaa1111"])
    section = Item("aaaa1111", 0, "one section", "body", "kuhyx/demo", "todo", None)
    assert files.commit_identity(section, tmp_path) == ("one section", ["aaaa1111"])


def test_the_tick_command_records_or_explains(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files.snapshot(tmp_path, ITEM)
    assert tick.main([str(tmp_path), "split", "aaaa1111-0", "one"]) == 0
    assert tick.main([str(tmp_path), "step", "aaaa1111-0", "1"]) == 0
    assert tick.main([str(tmp_path), "done", "aaaa1111-0"]) == 0
    assert "ok: done aaaa1111-0" in capsys.readouterr().out
    assert tick.main([str(tmp_path), "done", "nope0000-0"]) == 1
    assert "not a part of this run" in capsys.readouterr().err
    assert files.read(tmp_path).done == ("aaaa1111-0",)


def test_the_tick_command_runs_as_a_module(tmp_path: Path) -> None:
    import subprocess  # noqa: PLC0415

    files.snapshot(tmp_path, ITEM)
    shell = tick.command(tmp_path).split()
    assert shell[0].startswith("PYTHONPATH=")
    env = {"PYTHONPATH": shell[0].split("=", 1)[1]}
    done = subprocess.run(
        [sys.executable, "-m", "todoimpl.repotask.tick", str(tmp_path), "done", "aaaa1111-1"],
        env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert (done.returncode, done.stdout.strip()) == (0, "ok: done aaaa1111-1")


def test_the_prompt_lists_work_in_order_and_names_the_rest(tmp_path: Path) -> None:
    text = prompt.addendum(ITEM, tmp_path)
    assert "1. [aaaa1111-0] aaaa1111-0\n2. [aaaa1111-1] aaaa1111-1" in text
    assert "Human work, not yours, skip: [bbbb2222-0]" in text
    assert "Owned by an older run, do not touch: [cccc3333-0]" in text
    assert f"{tick.command(tmp_path)} done <key>" in text
    plain = Item("aaaa1111", 0, "one section", "body", "kuhyx/demo", "todo", None)
    assert prompt.addendum(plain, tmp_path) == ""
    bare = Item("deadbeef", 0, "demo", "b", "kuhyx/demo", "todo", None, "kuhy", parts=(part("aaaa1111-0"),))
    assert "Human work" not in prompt.addendum(bare, tmp_path)
    assert "Owned by" not in prompt.addendum(bare, tmp_path)


def test_a_new_cycle_clears_what_the_shipped_one_left(tmp_path: Path) -> None:
    files.snapshot(tmp_path, ITEM)
    files.mark_done(tmp_path, "aaaa1111-0")
    for name in ("plan.md", "live_check.md", "questions.json"):
        (tmp_path / name).write_text("old", encoding="utf-8")
    st = RunState(
        task_id="x-0", stage="shipped", worktree="/w", branch="todo/x-0", session_id="s", cost_usd=1.5
    )
    st.sessions, st.ship, st.checks = {"implement": "s"}, {"commit": "abc"}, {"passed": True}
    st.extra.update(spec_ok=True, partial={"done": []}, followup_id="f")
    new_cycle(st, tmp_path, 1.0)
    cleared = vars(st)
    assert [cleared[k] for k in ("worktree", "branch", "session_id", "ship", "checks")] == [None] * 5
    assert st.sessions == {}
    assert (st.extra["cycle"], st.cost_usd) == (2, 1.5)
    assert not {"spec_ok", "partial", "followup_id"} & st.extra.keys()
    assert files.read(tmp_path) == files.Ticks()
    assert not [p for p in tmp_path.iterdir() if p.name in ("plan.md", "live_check.md", "questions.json")]
    new_cycle(st, tmp_path, 1.0)
    assert st.extra["cycle"] == 3


def test_start_marks_the_run_and_begins_the_next_cycle_after_a_shipped_one(tmp_path: Path) -> None:
    st = RunState(task_id="x-0", stage="spec")
    prepare(st, ITEM, tmp_path, 1.0)
    assert (st.extra["repotask"], st.extra["repotask_title"], "cycle" in st.extra) == (True, "demo", False)
    shipped = RunState(task_id="x-0", stage="shipped")
    prepare(shipped, ITEM, tmp_path, 1.0)
    assert shipped.extra["cycle"] == 2


def test_the_tick_module_runs_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files.snapshot(tmp_path, ITEM)
    monkeypatch.setattr(sys, "argv", ["tick", str(tmp_path), "done", "aaaa1111-0"])
    with pytest.raises(SystemExit) as done:
        runpy.run_module("todoimpl.repotask.tick", run_name="__main__")
    assert done.value.code == 0
    assert files.read(tmp_path).done == ("aaaa1111-0",)
