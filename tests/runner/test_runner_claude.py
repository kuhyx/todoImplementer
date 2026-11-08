import subprocess
from pathlib import Path

import pytest
from runnerfakes import Env, executable
from todoimpl.runner import claude


def test_build_has_the_agreed_argv_and_env(world: Env, tmp_path: Path) -> None:
    inv = claude.build("implement", "override\ngo", tmp_path, resume="s1")
    assert inv.argv == (
        str(world.bin / "claude"),
        "-p",
        "override\ngo",
        "--model",
        "opus",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "acceptEdits",
        "--add-dir",
        str(tmp_path),
        "--resume",
        "s1",
        "--disallowedTools",
        "Bash(git push:*)",
        "Bash(git push *)",
    )
    assert inv.env["CLAUDE_AUTO_CONTINUE"] == "0"
    assert inv.cwd == tmp_path


def test_classify_is_read_only_and_models_follow_roles(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inv = claude.build("classify", "p", tmp_path, extra_dirs=(tmp_path / "shots",))
    assert inv.argv[11:13] == (str(tmp_path), str(tmp_path / "shots"))
    assert "--resume" not in inv.argv
    assert inv.argv[-5:] == ("Bash(git push:*)", "Bash(git push *)", "Edit", "Write", "NotebookEdit")
    assert [claude.model_for(r) for r in ("spec", "plan", "implement", "classify")] == [
        "sonnet",
        "sonnet",
        "opus",
        "haiku",
    ]
    monkeypatch.setenv("TODOIMPL_MODEL", "haiku")
    assert claude.model_for("implement") == "haiku"


def test_claude_bin_prefers_env_then_path_then_local_bin(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_CLAUDE", "/opt/claude")
    assert claude.claude_bin() == "/opt/claude"
    monkeypatch.delenv("TODOIMPL_CLAUDE")
    assert claude.claude_bin() == str(world.bin / "claude")
    monkeypatch.setenv("PATH", "/nonexistent")
    assert claude.claude_bin() == str(world.home / ".local" / "bin" / "claude")


def test_kill_tree_escalates_to_sigkill_and_tolerates_dead_groups(tmp_path: Path) -> None:
    stubborn = tmp_path / "stubborn.sh"
    executable(stubborn, "#!/bin/bash\ntrap '' TERM\necho ready\nsleep 20\n")
    proc = subprocess.Popen([str(stubborn)], stdout=subprocess.PIPE, text=True, start_new_session=True)
    assert proc.stdout is not None
    assert proc.stdout.readline() == "ready\n"
    claude.kill_tree(proc, grace=0.2)
    assert proc.returncode == -9
    proc.stdout.close()
    done = subprocess.Popen(["true"], start_new_session=True)
    done.wait()
    claude.kill_tree(done, grace=0.1)
