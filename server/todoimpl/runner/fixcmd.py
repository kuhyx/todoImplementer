"""The one-line command kuhy runs (or clicks Go on) when a permission cannot be added automatically."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .permissions import Verdict
    from .stream import Denial

__all__ = ("command_for", "grant_command", "needs_tty")
TTY_PROGRAMS = (
    "sudo", "su", "doas", "pacman", "yay", "paru",
    "ssh", "passwd", "visudo", "vim", "vi", "nano",
    "less", "top", "htop",
)  # fmt: skip
NEEDS_TTY = re.compile(r"(?<![\w-])(" + "|".join(TTY_PROGRAMS) + r")(?![\w-])")


def needs_tty(command: str) -> bool:
    """Say whether the command wants a terminal or a password, which Go cannot give."""
    return NEEDS_TTY.search(command) is not None


def _settings_file() -> Path:
    return Path.home() / ".claude" / "settings.json"


def grant_command(rules: tuple[str, ...]) -> str:
    """Build the jq one-liner that adds allow rules to the user settings."""
    target = shlex.quote(str(_settings_file()))
    tmp = shlex.quote(str(_settings_file().with_name("settings.json.todoimpl-tmp")))
    expr = f".permissions.allow = (((.permissions.allow // []) + {json.dumps(list(rules))}) | unique)"
    return f"jq {shlex.quote(expr)} {target} > {tmp} && mv {tmp} {target}"


def _one_line(command: str) -> str:
    if "\n" not in command:
        return command
    body = command.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"bash -c $'{body}'"


def command_for(d: Denial, verdict: Verdict, worktree: Path) -> str | None:
    """Return a Bash call as is from its worktree; other tools get a settings rule when one is safe."""
    if d.tool_name == "Bash":
        command = str(d.tool_input.get("command", "")).strip()
        return f"cd {shlex.quote(str(worktree))} && {_one_line(command)}" if command else None
    return grant_command(verdict.grant) if verdict.grant and not d.hook else None
