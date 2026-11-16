"""A deploy whose pull git stops on kuhy's own uncommitted edits (T2007).

A repo's declared deploy often starts with `git -C ~/src/<repo> pull --ff-only`. Git refuses when that
checkout has edits (or untracked files) at paths the incoming commit changes, and the deploy fails with
"would be overwritten by merge". Two cases, neither needs kuhy at once:

- Every blocking file already holds the incoming content (a session wrote the same change into the checkout):
  restore those files, losslessly, and deploy again.
- Any other edit is kuhy's: nothing of his is touched, the deploy waits on the backoff ladder (`shipfix`) and
  only after the ladder names the files to him.
"""

from __future__ import annotations

from pathlib import Path

from .files import NeedsYouError
from .worktree import base_ref, git

BLOCKED = "would be overwritten by merge"  # ends both of git's messages: local changes, untracked files
HEADERS = ("Your local changes to the following files", "The following untracked working tree files")
STOPS = ("Please ", "Aborting", "error:", "hint:", "fatal:")
UNTRACKED = "??"
RENAME_OR_COPY = "RC"
SHOWN = 4


class DirtyCheckoutError(NeedsYouError):
    """The deploy's pull is blocked by edits in kuhy's checkout; `files` are the ones that differ."""

    def __init__(self, prefix: str, checkout: Path, files: list[str]) -> None:  # noqa: D107
        where = str(checkout).replace(str(Path.home()), "~", 1)
        shown = ", ".join(files[:SHOWN]) + (f" and {len(files) - SHOWN} more" if len(files) > SHOWN else "")
        edits = f" to {shown}" if files else " (the deploy log names the files)"
        super().__init__(
            f"{prefix}: the deploy's pull into {where} stops on uncommitted edits{edits}: "
            "commit or discard them, then Retry",
            "run_failed",
        )
        self.where, self.files = where, files


def blocked(text: str) -> bool:
    """Return True when a deploy's output ends on git refusing a merge over local files."""
    return BLOCKED in text


def listed(text: str) -> list[str]:
    """Return the paths git names under its "would be overwritten" header (tab-indented lines)."""
    files: list[str] = []
    naming = False
    for line in text.splitlines():
        if any(head in line for head in HEADERS):
            naming = True
        elif naming and line.startswith("\t"):
            files.append(line.strip())
        elif naming and line.lstrip().startswith(STOPS):
            naming = False
    return files


def _incoming(checkout: Path) -> str:
    """Return what `git pull --ff-only` would merge: the branch's upstream, else origin's default branch."""
    up = git(checkout, "rev-parse", "--verify", "--quiet", "@{u}", check=False)
    return "@{u}" if up.returncode == 0 else base_ref(checkout)[0]


def _dirty(checkout: Path) -> list[tuple[str, str]]:
    """Return (status, path) of every edited, staged or untracked file."""
    out = git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    rows: list[tuple[str, str]] = []
    tokens = iter(out.split("\0"))
    for token in tokens:
        if len(token) > len("XY "):
            rows.append((token[:2], token[3:]))
            if token[0] in RENAME_OR_COPY:
                next(tokens, None)  # a rename lists its old path next
    return rows


def _blob(checkout: Path, spec: str) -> str | None:
    """Return the blob id behind `<ref>:<path>` (or `:<path>` for the index), None when there is none."""
    found = git(checkout, "rev-parse", "--verify", "--quiet", spec, check=False)
    return found.stdout.strip() if found.returncode == 0 else None


def _only_incoming(checkout: Path, ref: str, path: str) -> bool:
    """Return True when discarding `path` loses nothing of kuhy's.

    The tree holds the incoming content, and the index holds nothing of his: no entry for an untracked file,
    else HEAD's blob or the incoming one.
    """
    want, head, staged = (
        _blob(checkout, f"{ref}:{path}"),
        _blob(checkout, f"HEAD:{path}"),
        _blob(checkout, f":{path}"),
    )
    have = git(
        checkout, "hash-object", "--", path, check=False
    )  # git's own filters, as the pull would see it
    if want is None or have.returncode != 0 or have.stdout.strip() != want:
        return False
    return head is None if staged is None else staged in (head, want)


def _discard(checkout: Path, status: str, path: str) -> None:
    """Put one file back to HEAD (index and tree), or remove it when HEAD has none: the pull brings it."""
    if status == UNTRACKED:
        (checkout / path).unlink(missing_ok=True)
    elif git(checkout, "cat-file", "-e", f"HEAD:{path}", check=False).returncode == 0:
        git(checkout, "restore", "--source=HEAD", "--staged", "--worktree", "--", path)
    else:
        git(checkout, "rm", "-q", "-f", "--", path)


def heal(checkout: Path) -> list[str]:
    """Restore kuhy's blocking files when all of them already equal the incoming content.

    Returns the files that differ, untouched, when any does (all or nothing); [] when the checkout is now free
    for the pull (restored, or nothing was in the way).
    """
    git(checkout, "fetch", "--quiet", "origin", check=False)
    ref = _incoming(checkout)
    incoming = set(git(checkout, "diff", "--name-only", "-z", "HEAD", ref, check=False).stdout.split("\0"))
    blocking = [(status, path) for status, path in _dirty(checkout) if path in incoming]
    differ = [path for _, path in blocking if not _only_incoming(checkout, ref, path)]
    if differ:
        return sorted(differ)
    for status, path in blocking:
        _discard(checkout, status, path)
    return []
