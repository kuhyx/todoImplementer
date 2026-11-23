"""Keep board turns and free workers out of kuhy's checkouts under ~/src; catch what lands there (T2519).

kuhy's session policy runs board turns loose (`--add-dir ~`, bypassPermissions, an empty deny list), and
`--add-dir` cannot leave `~/src` out of `~`. So every turn whose cwd is not under the src root also gets
the writer tools denied there (`policy.src_deny_for`); Bash stays free: a deploy pulls in `~/src/<repo>`.
A free worker's shell is walled off for real (`srcwall`).

What a shell still writes is found by comparing `git status` of every checkout under the src root (any
`<src>/*/.git`, plus the card's own checkout) before and after: `begin` keeps a snapshot beside the turn's
stream (`<stem>.checkout.json`, so an adopted turn finds it after a restart), `end` writes the new edits to
`<run>/checkout-edits.jsonl` with the card (the run dir's name) and says them once. A sandboxed worker scans
its own checkout only: it cannot write the others, so what changes there is someone else's. A file counts
when it is dirty after the turn and was clean or held other content before. `attributed` and `owner` tell a
deploy or a heal whether the edits still sitting there are exactly what one card left.
"""

from __future__ import annotations

import functools
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.clone import src_root

from . import worktree
from .files import NeedsYouError, read_json, write_json

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

LOG = "checkout-edits.jsonl"
SNAPSHOT = ".checkout.json"
GONE = "-"  # a deleted file's content
RENAME_OR_COPY = "RC"
SCAN_TIMEOUT = 10.0  # one stuck repo is left out, never fails the turn
WIDTH = 16  # repos scanned side by side


def checkout_of(repo: str | None) -> Path | None:
    """Return the card's checkout, None when the card has no repo or no clone (never clones)."""
    try:
        return worktree.repo_dir(repo)
    except NeedsYouError:
        return None


@functools.lru_cache(maxsize=8192)
def _hash(path: str, stamp: tuple[int, int, int]) -> str:  # noqa: ARG001 - the stamp only keys the cache
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _digest(path: Path) -> str:
    """Return the file's sha256, GONE when it cannot be read (deleted, or a nested repo's directory).

    Cached by inode, size and mtime: the begin and end of every turn rehash only files that changed.
    """
    try:
        info = path.stat()
        return _hash(str(path), (info.st_ino, info.st_size, info.st_mtime_ns))
    except OSError:
        return GONE


def snapshot(checkout: Path) -> dict[str, str]:
    """Return {path: content digest} of every edited, staged or untracked file of the checkout.

    `--no-optional-locks`: the scan never takes kuhy's index.lock while he commits.
    """
    status = ("--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all")
    out = worktree.git(checkout, *status, check=False, timeout=SCAN_TIMEOUT).stdout
    found: dict[str, str] = {}
    tokens = iter(out.split("\0"))
    for token in tokens:
        if len(token) > len("XY "):
            found[token[3:]] = _digest(checkout / token[3:])
            if token[0] in RENAME_OR_COPY:
                next(tokens, None)  # a rename lists its old path next
    return found


def checkouts(repo: str | None, *, everywhere: bool = True) -> list[Path]:
    """Return the card's checkout and, when `everywhere`, every repo directly under the src root."""
    own = checkout_of(repo)
    found = {git.parent for git in src_root().glob("*/.git")} if everywhere else set()
    return sorted(found | ({own} if own else set()))


def _scan_one(checkout: Path) -> tuple[str, dict[str, str]] | None:
    try:
        return str(checkout), snapshot(checkout)
    except worktree.GitError, OSError:  # timed out, or the directory is gone
        return None


def scan(paths: Iterable[Path]) -> dict[str, dict[str, str]]:
    """Return {checkout: snapshot} of the checkouts that answered, scanned side by side."""
    with ThreadPoolExecutor(WIDTH) as pool:
        return dict(row for row in pool.map(_scan_one, paths) if row is not None)


def _snap_path(run_dir: Path, stem: str) -> Path:
    return run_dir / f"{stem}{SNAPSHOT}"


def begin(run_dir: Path, stem: str, repo: str | None, *, everywhere: bool = True) -> None:
    """Keep the checkouts' state as the turn starts; nothing when there is no checkout to watch."""
    if paths := checkouts(repo, everywhere=everywhere):
        write_json(_snap_path(run_dir, stem), {"checkouts": scan(paths)})


def _before(saved: dict[str, object]) -> dict[str, dict[str, str]]:
    """Return {checkout: files} of a snapshot; one from before T2519 held the card's checkout only."""
    if "checkouts" in saved:
        return saved["checkouts"]  # type: ignore[return-value]
    return {str(saved["checkout"]): saved["files"]}  # type: ignore[dict-item]


def end(run_dir: Path, stem: str, repo: str | None, now: float, say: Callable[[str], None]) -> list[str]:
    """Record and say the files the turn left dirty in the watched checkouts; return their paths."""
    own = str(checkout_of(repo))
    path = _snap_path(run_dir, stem)
    saved = read_json(path)
    path.unlink(missing_ok=True)  # consumed once: a replayed stream says nothing again
    if saved is None:  # nothing watched, or a turn launched before T2515
        return []
    was = _before(saved)
    left: list[str] = []
    for checkout, files in sorted(scan(Path(name) for name in was).items()):
        new = {name: digest for name, digest in files.items() if was[checkout].get(name) != digest}
        if new:
            row = {"at": now, "stem": stem, "card": run_dir.name, "checkout": checkout, "files": new}
            with (run_dir / LOG).open("a", encoding="utf-8") as log:
                log.write(json.dumps(row) + "\n")
            names = " ".join(sorted(new))  # another repo's change may be kuhy's or a parallel card's
            say(
                f"this turn left edits in kuhy's checkout {checkout}: {names}"
                if checkout == own
                else f"kuhy's checkout {checkout} changed while this turn ran: {names}"
            )
            left += (str(Path(checkout) / name) for name in sorted(new))
    return left


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
    """Return the one card (run dir name, child cards too) whose recorded edits the files all still are.

    Cards run side by side: when two saw the same edit land, which one wrote it is unknown, so none owns it.
    """
    names = list(files)
    logs = (*root.glob(f"*/{LOG}"), *root.glob(f"*/children/*/{LOG}"))
    cards = {log.parent.name for log in logs if attributed(log.parent, checkout, names)}
    return cards.pop() if len(cards) == 1 else None
