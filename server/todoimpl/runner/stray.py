"""Stray edits a deploy set aside (T2512): work origin lacks becomes a ticket for Claude (T2514).

The deploy stashed a board run's leftovers in kuhy's checkout and kept a patch. When origin already holds
those changes (a session landed them, maybe with more), nothing is left to do. Otherwise the work is filed
as a `work.stray` record in `<error state>/app-errors/stray-work.json`; the errors loop makes it a part of
the repo's card, and a session decides what to land (`errors/ticket.py`, `STRAY_GOAL`). Never kuhy's.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.board.repos import OWNER
from todoimpl.errors.sources import state_base
from todoimpl.errors.ticket import STRAY as KIND

from . import deployheal
from .files import NeedsYouError, read_json
from .heavybuild import NOT_APP
from .worktree import git

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["FILE", "KIND", "landed", "report", "route"]

FILE = "stray-work.json"
SUFFIX = "-stray"  # the hash leads: a ticket title shows the signature's first 8 characters
MESSAGE = "edits a board run left in kuhy's checkout, stashed by a deploy: land what origin lacks"


def landed(checkout: Path, ref: str, stash: str) -> bool:
    """Say whether `ref` already holds everything the stash holds; a git failure says no or raises (route it).

    Tracked edits: merging the stash into `ref` (base: the commit it was made on) leaves `ref`'s tree as
    is. Untracked files (the stash's third parent): `ref` has each of them with the same content.
    """
    merged = git(checkout, "merge-tree", "--write-tree", f"--merge-base={stash}^1", ref, stash, check=False)
    tree = git(checkout, "rev-parse", "--verify", "--quiet", f"{ref}^{{tree}}", check=False)
    if merged.returncode or tree.returncode or merged.stdout.split("\n", 1)[0] != tree.stdout.strip():
        return False
    extra = f"{stash}^3"  # `-u` makes it even when no file is untracked: then its tree is empty
    if git(checkout, "rev-parse", "--verify", "--quiet", extra, check=False).returncode:
        return True
    names = [n for n in git(checkout, "ls-tree", "-r", "-z", "--name-only", extra).stdout.split("\0") if n]
    return (
        not names or git(checkout, "diff", "--quiet", extra, ref, "--", *names, check=False).returncode == 0
    )


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat(timespec="seconds")


def report(repo: str, patch: Path, stash: str, files: list[str], now: float, owner: str = "") -> str:  # noqa: PLR0913, PLR0917
    """Count the patch in the stray-work report (one record per patch content); return its ticket key."""
    path = state_base() / "app-errors" / FILE
    data = read_json(path)
    errors: list[dict[str, Any]] = data.get("errors", []) if isinstance(data, dict) else []
    full = repo if "/" in repo else f"{OWNER}/{repo}"
    app = NOT_APP.sub("-", full.rsplit("/", 1)[-1].lower()).strip("-") or "repo"
    sig = hashlib.sha256(patch.read_bytes()).hexdigest()[:12] + SUFFIX
    record = next((e for e in errors if e.get("app") == app and e.get("signature") == sig), None)
    if record is None:
        record = {"app": app, "repo": full, "signature": sig, "kind": KIND, "count": 0, "build": 0,
                  "message": MESSAGE, "first_seen": _iso(now)}  # fmt: skip
        errors.append(record)
    detail = (
        f"stash {stash} (in your worktree: git stash show -p --include-untracked {stash}; "
        f"git stash apply {stash}); patch {patch}; files: {', '.join(files)}"
        + (f"; left by card {owner}" if owner else "")
    )
    record.update(count=int(record["count"]) + 1, last_seen=_iso(now), detail=detail, open=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic.write_text(path, json.dumps({"version": 1, "errors": errors}, indent=2) + "\n")
    return f"{app}:{sig}"


def route(checkout: Path, repo: str, aside: deployheal.Aside, files: list[str], now: float) -> str:
    """File the set-aside work for Claude unless origin holds it; return the close evidence line."""
    by = f" left by card {aside.owner}" if aside.owner else ""
    head = f"set aside stray edits{by} in {checkout}: {aside.patch} (git stash {aside.stash})"
    try:
        held = landed(checkout, deployheal.incoming_ref(checkout), aside.stash)
    except (
        NeedsYouError
    ):  # git cannot tell (failed ls-tree, no origin branch): route it, lose nothing (T2518)
        held = False
    if held:
        return f"{head}; origin already holds them"
    key = report(repo, aside.patch, aside.stash, files, now, aside.owner)
    return f"{head}; origin lacks them: ticket {key} for Claude"
