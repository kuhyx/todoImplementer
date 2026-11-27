"""Which repos the no-limit runner visits: every real checkout under the src root whose origin is kuhy's.

A checkout is a directory with a `.git` directory (a linked worktree has a `.git` file and is skipped) and a
hosted `origin` of the owner `kuhyx`: the runner never pushes to, or files a ticket for, a repo kuhy does not
own. Its commands are the backticked bullets of its CLAUDE.md (`- test: `...``). The full gate is `gate`,
else `test`; a repo with neither gets read-only checks only (its `lint`, never a commit or a push).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from todoimpl.board.repos import OWNER

if TYPE_CHECKING:
    from pathlib import Path

BULLET = re.compile(r"^[ \t]*[-*][ \t]+([a-z][a-z0-9-]*):[ \t]*`([^`\n]+)`", re.IGNORECASE)
FENCE = re.compile(r"^[ \t]*(```|~~~)")
ORIGIN = re.compile(r'\[remote "origin"\][^\[]*?^\s*url\s*=\s*(\S+)', re.MULTILINE)
HOSTED = re.compile(
    r"(?:[a-z+]+://(?:[^@/\s]+@)?[^/\s]+/|[^@/\s]+@[^:/\s]+:)([^/\s]+)/([^/\s]+?)(?:\.git)?/?$"
)


@dataclass(frozen=True)
class Repo:
    """One checkout: its directory name, path, `owner/name` and the CLAUDE.md commands."""

    name: str
    path: Path
    slug: str
    commands: dict[str, str] = field(default_factory=dict)

    @property
    def gate(self) -> str | None:
        """Return the full gate: `gate`, else `test`; None makes the repo read-only."""
        return self.commands.get("gate") or self.commands.get("test")


def commands_of(text: str) -> dict[str, str]:
    """Return the first `- <key>: `<command>`` bullet of each key outside code fences."""
    found: dict[str, str] = {}
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (hit := BULLET.match(line)) and hit.group(2).strip():
            found.setdefault(hit.group(1).lower(), hit.group(2).strip())
    return found


def slug_of(path: Path) -> str | None:
    """Return the checkout's hosted origin as `owner/name` when the owner is kuhy's, else None.

    Read from `.git/config` as written: a URL rewrite (`insteadOf`) changes where git fetches, not whose
    repo it is.
    """
    try:
        config = (path / ".git" / "config").read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None
    url = ORIGIN.search(config)
    hosted = None if url is None else HOSTED.search(url.group(1))
    if hosted is None or hosted.group(1).lower() != OWNER:
        return None
    return f"{OWNER}/{hosted.group(2)}"


def _read(path: Path) -> str:
    try:
        return (path / "CLAUDE.md").read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return ""


def load(path: Path) -> Repo | None:
    """Return the repo of one checkout, None when it is no real checkout of kuhy's."""
    if not (path / ".git").is_dir() or (slug := slug_of(path)) is None:
        return None
    return Repo(path.name, path, slug, commands_of(_read(path)))


def discover(src: Path) -> list[Repo]:
    """Return every repo under `src`, sorted by name (the visiting order)."""
    if not src.is_dir():
        return []
    return [repo for path in sorted(src.iterdir()) if (repo := load(path)) is not None]
