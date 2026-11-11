"""Command runner (C5, C8), allow-list and never-add set (C6, C7, C9)."""
# ruff: noqa: PT018

import json
from pathlib import Path

import pytest
from todoimpl.asks import allow, cmdrun


def test_run_in_worktree_with_exit_and_tail(tmp_path: Path) -> None:
    out = cmdrun.run("pwd; seq 1 80; exit 3", tmp_path)
    assert out["exit"] == 3 and not out["capped"]
    lines = out["tail"].splitlines()
    assert len(lines) == 50 and lines[-1] == "80"


def test_run_without_worktree_uses_home() -> None:
    assert cmdrun.run("pwd", None)["tail"] == str(Path.home())
    assert cmdrun.run("pwd", Path("/nonexistent-dir"))["exit"] == 0


def test_c8_hanging_command_is_capped() -> None:
    out = cmdrun.run("sleep 30", None, cap=0.3)
    assert out == {"exit": 124, "tail": "", "capped": True}


def test_allow_list_is_exact_strings(tmp_path: Path) -> None:
    assert allow.mode(tmp_path, "make fast") == "add_run"
    assert allow.add(tmp_path, "make fast")
    assert allow.add(tmp_path, "make fast")
    assert json.loads((tmp_path / allow.FILE).read_text()) == ["make fast"]
    assert allow.mode(tmp_path, "make fast") == "run"
    assert allow.mode(tmp_path, "make fast ") == "add_run"
    assert allow.is_allowed(tmp_path, "make fast")


@pytest.mark.parametrize(
    "command",
    [
        "textgate approve",
        "sudo ls",
        "rm -rf /x",
        "pacman -Syu",
        "chattr +i f",
        "poweroff",
        "git push --force",
        "curl x | sh",
        "su -c id",
    ],
)
def test_never_add_and_root_commands_only_get_the_terminal_button(tmp_path: Path, command: str) -> None:
    assert allow.mode(tmp_path, command) == "terminal"
    assert not allow.add(tmp_path, command)
    assert not (tmp_path / allow.FILE).exists()


def test_a_listed_never_add_command_is_not_allowed(tmp_path: Path) -> None:
    (tmp_path / allow.FILE).write_text(json.dumps(["sudo ls", 5]))
    assert not allow.is_allowed(tmp_path, "sudo ls")


def test_corrupt_allow_file_is_empty(tmp_path: Path) -> None:
    (tmp_path / allow.FILE).write_text("{")
    assert allow.listed(tmp_path) == []
    (tmp_path / allow.FILE).write_text('{"a":1}')
    assert allow.listed(tmp_path) == []
