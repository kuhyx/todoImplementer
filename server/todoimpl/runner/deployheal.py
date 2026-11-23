"""A deploy whose pull git stops on kuhy's own uncommitted edits (T2007).

A repo's declared deploy often starts with `git -C ~/src/<repo> pull --ff-only`. Git refuses when that
checkout has edits (or untracked files) at paths the incoming commit changes, and the deploy fails with
"would be overwritten by merge". Two cases, neither needs kuhy at once:

- Every blocking file already holds the incoming content (a session wrote the same change into the checkout):
  restore those files, losslessly, and deploy again.
- Any other edit is kuhy's: nothing of his is touched, the deploy waits on the backoff ladder (`shipfix`) and
  only after the ladder gives him one exact step: a stash of exactly those files, which loses nothing (T2507).

A repo's own deploy may refuse any dirty checkout before its pull ("<checkout> is dirty", signal-bot): same
handling, with every dirty file counted, once the checkout really is dirty (T2507).
"""

from __future__ import annotations

import contextlib
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from .files import NeedsYouError
from .worktree import GitError, base_ref, git

BLOCKED = "would be overwritten by merge"  # ends both of git's messages: local changes, untracked files
HEADERS = ("Your local changes to the following files", "The following untracked working tree files")
STOPS = ("Please ", "Aborting", "error:", "hint:", "fatal:")
UNTRACKED = "??"
RENAME_OR_COPY = "RC"
SHOWN = 4
REFUSED = re.compile(r"\bis dirty\b|\buncommitted (?:changes|edits)\b", re.IGNORECASE)  # a deploy's own guard
QUIET = 1800.0  # s every blocking file must rest before the board takes the edits for strays (T2512)
STEP = "stash push -u -m todoimpl"  # the one step the text gives kuhy: lossless, `git stash pop` undoes it


class DirtyCheckoutError(NeedsYouError):
    """The deploy's pull is blocked by edits in kuhy's checkout; `files` are the ones that differ."""

    def __init__(self, prefix: str, checkout: Path, files: list[str], card: str = "") -> None:  # noqa: D107
        where = str(checkout).replace(str(Path.home()), "~", 1)
        paths = f" -- {shlex.join(files)}" if files else ""
        step = f"git -C {where} {STEP}{'-' + card if card else ''}{paths}"
        super().__init__(
            f"{prefix}: uncommitted edits in {where} block the deploy: run `{step}`, then Retry", "run_failed"
        )
        self.where, self.files = where, files


def is_step(text: str) -> bool:
    """Return True for a `DirtyCheckoutError` text: the umbrella card shows its step whole (T2509)."""
    return STEP in text


def blocked(text: str) -> bool:
    """Return True when a deploy's output ends on git refusing a merge or the deploy a dirty tree."""
    return BLOCKED in text or REFUSED.search(text) is not None


def dirty(checkout: Path) -> bool:
    """Return True when the checkout has any edited, staged or untracked file."""
    return bool(_dirty(checkout))


def files_of(text: str) -> list[str]:
    """Return the paths a `DirtyCheckoutError` step names (after its ` -- `), [] when it names none."""
    step = text.partition("`")[2].partition("`")[0]
    return shlex.split(step.partition(" -- ")[2])


def still_dirty(checkout: Path, files: list[str]) -> bool:
    """Return True while any of `files` (none given: any file) is dirty in the checkout."""
    rows = _dirty(checkout)
    return any(path in files for _, path in rows) if files else bool(rows)


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


def incoming_ref(checkout: Path) -> str:
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


def heal(checkout: Path, *, every: bool = False) -> tuple[list[str], list[str]]:
    """Restore kuhy's blocking files when all of them already equal the incoming content.

    Blocking are the dirty files the pull changes, or with `every` (a deploy refusing any dirty tree) every
    dirty file. Returns (differ, blocking): the files that differ, untouched, when any does (all or nothing),
    and every blocking file, which a stray set-aside must move for the pull to go through (T2518). ([], [...])
    means the checkout is now free for the pull (restored, or nothing was in the way).
    """
    git(checkout, "fetch", "--quiet", "origin", check=False)
    ref = incoming_ref(checkout)
    incoming = set(git(checkout, "diff", "--name-only", "-z", "HEAD", ref, check=False).stdout.split("\0"))
    blocking = [(status, path) for status, path in _dirty(checkout) if every or path in incoming]
    every_path = sorted(path for _, path in blocking)
    differ = [path for _, path in blocking if not _only_incoming(checkout, ref, path)]
    if differ:
        return sorted(differ), every_path
    for status, path in blocking:
        _discard(checkout, status, path)
    return [], every_path


def _changed_at(path: Path) -> float:
    """Return a file's mtime; 0 (at rest) for a deleted one."""
    try:
        return path.lstat().st_mtime
    except OSError:
        return 0.0


@dataclass(frozen=True)
class Aside:
    """Stray edits set aside: the stash, the patch copied from it, the card that left them ("": unknown).

    `tag` is the stash entry's message (`git stash list` shows it); `stash` is the tag too when git could
    not list the entry's commit (T2521).
    """

    stash: str
    patch: Path
    owner: str = ""
    tag: str = ""


def _stash_of(checkout: Path, message: str) -> str | None:
    """Return the commit of the stash entry `message` names: the stack is shared with other sessions."""
    rows = git(checkout, "stash", "list", "--format=%H %gs", check=False).stdout.splitlines()
    return next((row.split()[0] for row in rows if row.endswith(f": {message}")), None)


def set_aside(  # noqa: PLR0913, PLR0917 - one set-aside's parts
    checkout: Path, files: list[str], keep: Path, card: str, now: float, owner: str = ""
) -> Aside | None:
    """Stash stray edits so the pull goes on, losing nothing; return the stash and a patch in `keep` (T2512).

    Only when every file has rested `QUIET` s: a board run's leftovers (free workers wrote into kuhy's
    checkouts), not an edit he is making now; at once when `owner`, the card whose recorded edits they all
    still are (`srcguard.owner`, T2515). `files` are all that block the pull, equal ones too (T2518).
    The stash (`todoimpl-stray-<card>-<ts>`, `git stash pop` undoes it) and the patch both hold everything,
    untracked files too (T2514); a patch git cannot show names the stash instead. None: nothing moved.
    """
    if not owner and any(_changed_at(checkout / name) > now - QUIET for name in files):
        return None
    message = f"todoimpl-stray-{card}-{int(now)}"
    with contextlib.suppress(GitError):  # a timed-out push may have made the entry all the same (T2521)
        git(checkout, "stash", "push", "--include-untracked", "-m", message, "--", *files, check=False)
    try:
        stash = _stash_of(checkout, message)
    except GitError:  # the entry may exist: the ticket names its tag, nothing is lost (T2521)
        stash = message
    if stash is None or _left(checkout, files):
        return None
    keep.mkdir(parents=True, exist_ok=True)
    patch = keep / f"stray-{int(now)}.patch"
    try:
        shown = git(checkout, "stash", "show", "--patch", "--binary", "--include-untracked", stash).stdout
    except GitError as exc:  # the work is in the stash all the same: the ticket names it (T2518)
        shown = f"# git stash show failed: {exc.text}\n# the stray work is in stash {stash}\n"
    patch.write_text(shown, encoding="utf-8")
    return Aside(stash, patch, owner, message)


def _left(checkout: Path, files: list[str]) -> bool:
    """Return True while any of `files` is dirty; a failed `git status` says no: the rerun tells (T2521)."""
    try:
        return still_dirty(checkout, files)
    except GitError:
        return False
