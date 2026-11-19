"""The deploy a repo declares: the `- deploy:` bullet of its CLAUDE.md at HEAD (DOCS-landing.md).

Two forms: ``- deploy: `<command>` `` runs the command; ``- deploy: none (<why>)`` says nothing of the repo
runs or installs anywhere, so Ship deploys nothing and counts the push as deployed (T2342). A `none` with no
reason is no declaration.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING

from .checks import CheckResult
from .files import NeedsYouError
from .worktree import git

if TYPE_CHECKING:
    from pathlib import Path

PREFIX = "pushed, not deployed"  # what every failure of a deploy starts with: the umbrella card keys on it
LINE = re.compile(r"^[ \t]*[-*][ \t]+deploy:[ \t]*`([^`\n]+)`", re.IGNORECASE)
NONE_LINE = re.compile(r"^[ \t]*[-*][ \t]+deploy:[ \t]*(none[ \t]*\([^)\n]*\S[^)\n]*\))", re.IGNORECASE)
NONE = re.compile(r"^none[ \t]*\(", re.IGNORECASE)
LINK_HOPS = 5  # CLAUDE.md -> AGENTS.md is one hop; a few more cover a chain, a loop ends here
SYMLINK_MODE = "120000"  # git tree mode of a symlink
LS_FIELDS = 4  # `git ls-tree` prints <mode> <type> <sha>\t<path>
FENCE = re.compile(r"^[ \t]*(```|~~~)")


class NoDeployLineError(NeedsYouError):
    """CLAUDE.md at HEAD declares no deploy: the session adds the line (T2342)."""

    def __init__(self, text: str) -> None:  # noqa: D107
        super().__init__(text, "run_failed")


def declared(text: str) -> str | None:
    """Return the first `- deploy:` outside code fences (a command or `none (<why>)`), else None."""
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif fenced:
            continue
        elif (found := LINE.match(line) or NONE_LINE.match(line)) and found.group(1).strip():
            return found.group(1).strip()
    return None


def is_none(command: str) -> bool:
    """Say whether a declaration is `none (<why>)`: nothing to deploy."""
    return NONE.match(command) is not None


def nothing(command: str) -> CheckResult:
    """Return the passing deploy result of a `none (<why>)` declaration; no unit runs."""
    return CheckResult("deploy", command, 0, f"nothing to deploy: {command}", "")


def claude_md(wt: Path) -> str:
    """Return CLAUDE.md as committed at HEAD, following in-repo symlinks (CLAUDE.md -> AGENTS.md), else "".

    `git show` on a symlink returns the link text, so the blob is resolved by hand: a target that is absolute,
    leaves the repo, dangles, is not a file or loops past `LINK_HOPS` yields "".
    """
    path = "CLAUDE.md"
    for _ in range(LINK_HOPS):
        entry = git(wt, "ls-tree", "HEAD", "--", path, check=False).stdout.split(maxsplit=3)
        if len(entry) < LS_FIELDS or entry[1] != "blob":
            return ""
        blob = git(wt, "cat-file", "blob", entry[2], check=False).stdout
        if entry[0] != SYMLINK_MODE:
            return blob
        target = posixpath.normpath(posixpath.join(posixpath.dirname(path), blob.strip()))
        if blob.startswith("/") or target == ".." or target.startswith("../"):
            return ""
        path = target
    return ""


def command_of(wt: Path, repo: str | None) -> str:
    """Return the deploy CLAUDE.md declares at HEAD, or raise `NoDeployLineError` ("pushed, not deployed")."""
    if (command := declared(claude_md(wt))) is None:
        msg = f"{PREFIX}: {repo or 'the repo'} declares no deploy: command in CLAUDE.md"
        raise NoDeployLineError(msg)
    return command
