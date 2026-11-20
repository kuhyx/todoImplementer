"""Clone a note's repo when no checkout exists anywhere (T2079, DOCS-landing.md, "Where a repo lives").

A `kuhyx/<name>` repo that GitHub says does not exist is a new project: it is created first (T2377).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

GH = "gh"  # the binary; the test suite points it at nothing so no test ever clones
TIMEOUT_S = 900.0  # a big repo over a slow line; the drive waits, the click never does
# gh's own words for a repo GitHub does not have (GraphQL NOT_FOUND). Anything else (network, auth, rate
# limit) is a real clone failure and must never create a repo.
NOT_FOUND = "Could not resolve to a Repository"
_VISIBILITY = re.compile(r"^\s*visibility:\s*(public|private)\s*$", re.IGNORECASE)
_FENCE = "```"


class RepoMissingError(OSError):
    """GitHub has no such repo: the clone found nothing, as opposed to failing to reach it."""


def src_root() -> Path:
    """Return where new clones go: $TODOIMPL_SRC, else ~/src."""
    return Path(os.environ.get("TODOIMPL_SRC") or Path.home() / "src")


def wants_public(body: str) -> bool:
    """Say whether a note asks for a public repo: a `visibility: public` line outside code fences.

    Private is the default; any `visibility: private` line wins over a public one.
    """
    seen: set[str] = set()
    fenced = False
    for line in body.split("\n"):
        if line.lstrip().startswith(_FENCE):
            fenced = not fenced
        elif not fenced and (match := _VISIBILITY.match(line)):
            seen.add(match.group(1).lower())
    return seen == {"public"}


def _gh(*args: str) -> None:
    """Run `gh <args>`; any failure raises OSError naming gh's own words, RepoMissingError for NOT_FOUND."""
    what = f"gh {' '.join(args[:3])}"
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            [GH, *args],
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )  # fmt: skip
    except (subprocess.TimeoutExpired, OSError) as exc:
        msg = f"{what}: {exc}"
        raise OSError(msg) from exc
    if proc.returncode != 0:
        said = (proc.stderr or proc.stdout).strip()
        msg = f"{what} failed: {said[-300:]}"
        raise (RepoMissingError if NOT_FOUND in said else OSError)(msg)


def gh_clone(repo: str, dest: Path) -> None:
    """Run `gh repo clone <owner>/<name> <dest>`; any failure raises OSError naming gh's own words."""
    _gh("repo", "clone", repo, str(dest))


def gh_create(repo: str, *, public: bool) -> None:
    """Create `repo` on GitHub with a README commit on its default branch, so worktrees can branch off it."""
    _gh("repo", "create", repo, "--public" if public else "--private", "--add-readme")
