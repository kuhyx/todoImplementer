"""T2519: an edit a card's turn saw land in ANOTHER repo's checkout never lets a deploy skip the wait."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from runnerfakes import Env, make_repo, sh
from schedfakes import CARD
from todoimpl.runner import deploy, srcguard, worktree
from todoimpl.runner.deployheal import DirtyCheckoutError

if TYPE_CHECKING:
    from pathlib import Path


def _repo(world: Env) -> tuple[Path, Path, Path]:
    """Push a commit changing `b.txt`; return (worktree, run dir, kuhy's checkout of kuhyx/demo)."""
    checkout = make_repo(world, files={"CLAUDE.md": "# demo\n", "b.txt": "old b\n"})
    wt = worktree.add(checkout, world.root, CARD).path
    (wt / "b.txt").write_text("new b\n", encoding="utf-8")
    sh(wt, "git", "commit", "-qam", "incoming")
    sh(wt, "git", "push", "-q", "origin", "HEAD:main")
    return wt, world.root / CARD, checkout


def test_t2519_an_edit_in_repo_b_seen_by_card_a_keeps_the_quiet_wait(world: Env) -> None:
    wt, run_dir, checkout = _repo(world)
    other = world.root / "0ther123-0"  # a card of another repo whose turn ran while kuhy edited demo
    other.mkdir(parents=True)
    srcguard.begin(other, "turn-1", "kuhyx/elsewhere")
    (checkout / "b.txt").write_text("his live edit\n", encoding="utf-8")
    seen: list[str] = []
    srcguard.end(other, "turn-1", "kuhyx/elsewhere", time.time(), seen.append)
    assert seen == [f"kuhy's checkout {checkout} changed while this turn ran: b.txt"]  # logged for the feed
    with pytest.raises(DirtyCheckoutError):
        deploy.run(wt, run_dir, CARD, "kuhyx/demo", f"git -C {checkout} pull -q --ff-only")
    assert (checkout / "b.txt").read_text(encoding="utf-8") == "his live edit\n"
    assert srcguard.owner(world.root, checkout, ["b.txt"]) is None
