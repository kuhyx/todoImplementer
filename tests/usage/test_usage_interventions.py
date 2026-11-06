"""The intervention record, the permission classifier and the contract shape of the autonomy block."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from autofix import WEEK45, add_turn, make_run, tail
from todoimpl.usage import usage_summary
from todoimpl.usage.asks import is_permission_ask, last_result_text, turns
from todoimpl.usage.interventions import record, recorded

if TYPE_CHECKING:
    from pathlib import Path

# Lines taken from the real A: asks in ~/.cache/todoImplementer (2026-11-06).
PERMISSION = [
    "Run `! textgate approve` for the tile captions (Shutdown, Gaming) before implementation starts.",
    "In the worktree's `.pre-commit-config.yaml`, add this before `- id: todo-closer` (or approve the edit)",
    "fix stage blocked: decide the duplicate-code threshold, and approve the `leetcode_coach` gate edit.",
    "I need permission to write outside the worktree.",
    "Please allow the Bash tool `systemctl --user restart x` so I can continue.",
    "Run `sudo pacman -S adb` and tell me when it is done.",
]
NOT_PERMISSION = [
    "attach the phone with ADB authorized, then re-run the implementation stage.",
    "register the sims3 MCP (command above) and restart; steps 6b-9 are untouched until it connects.",
    "Ship the build, then say whether to resolve the network/server signatures.",
    "plug in and unlock the Pixel. Then I'll do the staged release install.",
    "",
]


@pytest.mark.parametrize("line", PERMISSION)
def test_permission_lines_match(line: str) -> None:
    assert is_permission_ask(line)


@pytest.mark.parametrize("line", NOT_PERMISSION)
def test_other_asks_do_not_match(line: str) -> None:
    assert not is_permission_ask(line)


def test_record_appends_and_recorded_reads_them_back(tmp_path: Path) -> None:
    assert recorded(tmp_path / "a-0") is None
    record(tmp_path, "a-0", "start", 5.0)
    record(tmp_path, "a-0", "send", 6.5)
    assert recorded(tmp_path / "a-0") == [(5.0, "start"), (6.5, "send")]
    assert (tmp_path / "a-0" / "interventions.jsonl").read_text().count("\n") == 2


def test_record_never_raises_when_the_disk_refuses(tmp_path: Path) -> None:
    (tmp_path / "a-0").write_text("a file where the run dir should be")
    record(tmp_path, "a-0", "send", 1.0)  # an action that worked must not fail on its bookkeeping


def test_usage_summary_carries_a_valid_autonomy_block(tmp_path: Path, usage_validator: Any) -> None:
    run = make_run(tmp_path, "aaaaaaaa-0", "gate", updated=WEEK45)
    add_turn(run, "implement", WEEK45, "A", tail("x", "A: approve the edit"))
    make_run(tmp_path, "bbbbbbbb-0", "gate", updated=WEEK45)
    out = usage_summary(tmp_path, now=WEEK45)
    usage_validator.validate(out)
    assert out["autonomy"]["permission_asks"]["value"] == 1
    assert out["autonomy"]["done_unassisted"]["value"] == 50.0


def test_last_result_text_reads_the_tail_and_skips_what_is_not_a_result(tmp_path: Path) -> None:
    stream = tmp_path / "s.stream.jsonl"
    stream.write_text('{"type": "result", "result": "done"}\n{"type": "assistant"}\n[1]\n{torn\n')
    assert last_result_text(stream) == "done"
    stream.write_text('{"type": "assistant"}\n')
    assert last_result_text(stream) == ""
    assert last_result_text(tmp_path / "missing.stream.jsonl") == ""


def test_turns_skip_files_without_an_epoch(tmp_path: Path) -> None:
    (tmp_path / "junk.result.json").write_text('{"tag": "A"}')
    assert turns(tmp_path) == []
