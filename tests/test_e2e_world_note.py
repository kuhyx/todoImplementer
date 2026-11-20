"""[T2355] The e2e scratch world never reaches kuhy's real todo app through the todo CLI.

A repo-less new task (T2347) and the merge umbrella add notes with the todo CLI (`$TODOIMPL_TODO_NOTE`,
else `dart run` in ~/src/todo). The scratch server did not set it, so a live check of "add task, no repo"
would have written a real note.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "e2e"))
e2e_world: Any = importlib.import_module("e2e_world")  # the scratch-world scripts are not a package


def test_t2355_the_scratch_server_uses_a_recording_todo_cli(tmp_path: Path) -> None:
    state = e2e_world.State(work=str(tmp_path))
    (tmp_path / "bin").mkdir()
    e2e_world.write_shims(state)
    cli = e2e_world.server_env(state)["TODOIMPL_TODO_NOTE"]
    assert cli == str(tmp_path / "bin" / "todo_note")
    args = ["--text", "# Idea", "--by", "kuhy"]
    out = subprocess.run([cli, *args], capture_output=True, text=True, check=True)
    note_id = out.stdout.split()[-1]
    assert len(note_id) == 36
    assert (tmp_path / "todo_note.log").read_text().splitlines() == args
