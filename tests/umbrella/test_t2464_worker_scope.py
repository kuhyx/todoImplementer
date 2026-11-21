"""T2464: a free worker of one repo wrote into kuhy's checkouts of other repos (umbrella 7808ee0a-0)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from todoimpl.runner import freeworker
from todoimpl.umbrella import rounds
from todoimpl.umbrella.note import Child

SHIM = """#!/bin/sh
printf '%s\\n' "$@" > "$ARGS_FILE"
echo edited > made.txt
"""


def _child(repo: str = "kuhyx/system-maintenance") -> Child:
    text = "Put my logo everywhere in every single app"
    title = "Put my logo everywhere"
    return Child("abcd1234", 1, repo, 0, text, title, None, None, done=False, cid="umbr0001-1")


def test_t2464_the_task_file_scopes_the_child_to_its_own_repo(tmp_path: Path) -> None:
    rounds._write_task(tmp_path, _child())
    task = (tmp_path / "task.md").read_text(encoding="utf-8")
    assert "Put my logo everywhere in every single app" in task
    assert "kuhyx/system-maintenance" in task
    assert "other repos" in task.lower()
    assert (
        "everywhere" in task.split("Put my logo everywhere in every single app", 1)[1]
    )  # said after the text


def test_t2464_the_worker_cannot_write_under_the_src_root_and_is_told_its_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "wt"
    repo.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@x"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    shim = tmp_path / "bin" / "claude-free"
    shim.parent.mkdir()
    shim.write_text(SHIM, encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim.parent}:/usr/bin:/bin")
    monkeypatch.setenv("ARGS_FILE", str(tmp_path / "args"))
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path / "src"))
    (tmp_path / "prompt.md").write_text("Do the thing.", encoding="utf-8")
    code = freeworker.main([str(repo), str(tmp_path / "prompt.md"), str(tmp_path / "worker.log")])
    assert code == 0
    args = (tmp_path / "args").read_text(encoding="utf-8").splitlines()
    denied = args[args.index("--disallowedTools") + 1 :]
    for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        assert f"{tool}(/{tmp_path / 'src'}/**)" in denied
    assert "Bash(git push:*)" in denied
    assert str(repo) in args[1]
    assert args[1].startswith(freeworker.PREAMBLE)
