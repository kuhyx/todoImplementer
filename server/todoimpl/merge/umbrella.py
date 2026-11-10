"""Create the repo-less umbrella note with the todo app's own CLI: add_task of the MCP needs a repo."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from .apply import UPSTREAM, MergeError

TIMEOUT_S = 55.0  # `dart run` may compile on first use; still under the 60 s cap
NOTE_ID = re.compile(r"[0-9a-f-]{8,36}")


def note_command() -> tuple[list[str], Path]:
    """Return the CLI argv prefix and cwd: `$TODOIMPL_TODO_NOTE`, else dart run in ~/src/todo."""
    custom = os.environ.get("TODOIMPL_TODO_NOTE")
    if custom:
        return shlex.split(custom), Path.cwd()
    home = Path(os.environ.get("TODOIMPL_TODO_APP") or Path.home() / "src" / "todo")
    return ["dart", "run", "bin/todo_note.dart"], home


def create_umbrella(text: str) -> str:
    """Add `text` as a note without a repo (`--by claude`) and return the id the CLI printed."""
    prefix, cwd = note_command()
    try:
        proc = subprocess.run(  # noqa: S603
            [*prefix, "--text", text, "--by", "claude"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"the todo CLI timed out after {TIMEOUT_S:g}s"
        raise MergeError(msg, UPSTREAM) from exc
    except OSError as exc:
        msg = f"cannot run the todo CLI: {exc}"
        raise MergeError(msg, UPSTREAM) from exc
    lines = proc.stdout.split()
    if proc.returncode != 0 or not lines or not NOTE_ID.fullmatch(lines[-1]):
        detail = (proc.stderr or proc.stdout).strip()[-200:]
        msg = f"the todo CLI did not add the umbrella: {detail}"
        raise MergeError(msg, UPSTREAM)
    return lines[-1]
