"""Keep board turns and free workers out of kuhy's checkouts under ~/src; catch what lands there (T2515).

kuhy's session policy runs board turns loose (`--add-dir ~`, bypassPermissions, an empty deny list), and
`--add-dir` cannot leave `~/src` out of `~`. So every turn whose cwd is not under the src root also gets
the writer tools denied there (`policy.src_deny_for`); Bash stays free: a deploy pulls in `~/src/<repo>`.

What Bash or a free worker still writes into the card's own checkout is found by comparing it before and
after: `begin` keeps a snapshot beside the turn's stream (`<stem>.checkout.json`, so an adopted turn finds it
after a restart), `end` writes the new edits to `<run>/checkout-edits.jsonl` and says them once. A file counts
when it is dirty after the turn and was clean or held other content before. `attributed` and `owner` tell a
deploy or a heal whether the edits still sitting there are exactly what a card left.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from . import worktree
from .files import NeedsYouError, read_json, write_json

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

LOG = "checkout-edits.jsonl"
SNAPSHOT = ".checkout.json"
GONE = "-"  # a deleted file's content
RENAME_OR_COPY = "RC"


def checkout_of(repo: str | None) -> Path | None:
    """Return the card's checkout, None when the card has no repo or no clone (never clones)."""
    try:
        return worktree.repo_dir(repo)
    except NeedsYouError:
        return None


def _digest(path: Path) -> str:
    """Return the file's sha256, GONE when it cannot be read (deleted, or a nested repo's directory)."""
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError:
        return GONE


def snapshot(checkout: Path) -> dict[str, str]:
    """Return {path: content digest} of every edited, staged or untracked file of the checkout."""
    status = ("status", "--porcelain=v1", "-z", "--untracked-files=all")
    out = worktree.git(checkout, *status, check=False).stdout
    found: dict[str, str] = {}
    tokens = iter(out.split("\0"))
    for token in tokens:
        if len(token) > len("XY "):
            found[token[3:]] = _digest(checkout / token[3:])
            if token[0] in RENAME_OR_COPY:
                next(tokens, None)  # a rename lists its old path next
    return found


def _snap_path(run_dir: Path, stem: str) -> Path:
    return run_dir / f"{stem}{SNAPSHOT}"


def begin(run_dir: Path, stem: str, repo: str | None) -> None:
    """Keep the card's checkout state as the turn starts; nothing when the card has no checkout."""
    if (checkout := checkout_of(repo)) is not None:
        write_json(_snap_path(run_dir, stem), {"checkout": str(checkout), "files": snapshot(checkout)})


def end(run_dir: Path, stem: str, repo: str | None, now: float, say: Callable[[str], None]) -> list[str]:
    """Record and say the files the turn left dirty in the card's checkout; return them ([] when none)."""
    path = _snap_path(run_dir, stem)
    before = read_json(path)
    checkout = checkout_of(repo)
    path.unlink(missing_ok=True)  # consumed once: a replayed stream says nothing again
    if before is None or checkout is None:  # no checkout, or a turn launched before T2515
        return []
    was: dict[str, str] = before.get("files", {})
    new = {name: digest for name, digest in snapshot(checkout).items() if was.get(name) != digest}
    if new:
        row = {"at": now, "stem": stem, "checkout": str(checkout), "files": new}
        with (run_dir / LOG).open("a", encoding="utf-8") as log:
            log.write(json.dumps(row) + "\n")
        say(f"this turn left edits in kuhy's checkout {checkout}: {' '.join(sorted(new))}")
    return sorted(new)


def _recorded(run_dir: Path, checkout: Path) -> dict[str, set[str]]:
    """Return {path: digests} the card recorded for this checkout."""
    seen: dict[str, set[str]] = {}
    try:
        lines = (run_dir / LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return seen
    for line in lines:
        row = json.loads(line)
        if row["checkout"] == str(checkout):
            for name, digest in row["files"].items():
                seen.setdefault(name, set()).add(digest)
    return seen


def attributed(run_dir: Path, checkout: Path, files: Iterable[str]) -> bool:
    """Say whether every file still holds content this card left there (and there is at least one)."""
    names = list(files)
    seen = _recorded(run_dir, checkout)
    return bool(names) and all(_digest(checkout / name) in seen.get(name, ()) for name in names)


def owner(root: Path, checkout: Path, files: Iterable[str]) -> str | None:
    """Return the card (run dir name, child cards too) whose recorded edits the files all still are."""
    names = list(files)
    for log in sorted((*root.glob(f"*/{LOG}"), *root.glob(f"*/children/*/{LOG}"))):
        if attributed(log.parent, checkout, names):
            return log.parent.name
    return None
