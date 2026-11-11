"""Exact-string command allow-list `$TODOIMPL_HOME/cmd-allow.json` (never patterns) and the never-add set."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "cmd-allow.json"
NEVER_ADD = re.compile(
    r"sudo|pkexec|\bsu\b|\brm\s+-\w*[rf]|pacman|chattr|poweroff|shutdown|reboot|git\s+push\s+.*--force"
    r"|(?:curl|wget)\b.*\|\s*(?:ba|z)?sh|textgate\s+approve|mkfs|\bdd\b",
)
ROOT = re.compile(r"sudo|pkexec|\bsu\b|systemctl(?!\s+--user)")


def listed(root: Path) -> list[str]:
    """Return the allowed command strings."""
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return []
    return [c for c in data if isinstance(c, str)] if isinstance(data, list) else []


def is_allowed(root: Path, command: str) -> bool:
    """Return True when this exact string was added before and is not in the never-add set."""
    return command in listed(root) and not NEVER_ADD.search(command)


def mode(root: Path, command: str) -> str:
    """Return the button: `run`, `add_run` (not listed yet) or `terminal` (never-add set: copy text)."""
    if NEVER_ADD.search(command) or ROOT.search(command):
        return "terminal"
    return "run" if command in listed(root) else "add_run"


def add(root: Path, command: str) -> bool:
    """Add one exact command; False (nothing written) for the never-add set."""
    if NEVER_ADD.search(command) or ROOT.search(command):
        return False
    items = listed(root)
    if command not in items:
        atomic.write_text(root / FILE, json.dumps([*items, command], indent=1))
    return True
