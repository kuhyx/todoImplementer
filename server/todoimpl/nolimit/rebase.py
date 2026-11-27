"""Chore: rebase each waiting card's worktree onto origin, so its next turn starts from a current base.

Per waiting card (not ended, no turn in flight), each git call one capped step under 60 s: skip a tree with
changes, fetch, skip when `origin/<base>` is already an ancestor of HEAD, else `git rebase origin/<base>`. A
conflict aborts the rebase (the tree is back as it was) and files one ticket through the errors loop
(`nolimit-rebase` of the card's repo), so the next turn knows before it starts.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from . import cards, steps, tickets
from .repos import Repo

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BUDGET = 45.0


def _repo(card: cards.Card) -> Repo:
    """Name the ticket after the card's repo, else the card."""
    return Repo(card.repo.rsplit("/", 1)[-1], card.worktree, card.repo)


def rebase_card(card: cards.Card, now: float) -> str:
    """Rebase one card; return what happened."""
    wt, base = card.worktree, f"origin/{card.base}"
    status = steps.run("rebase-status", "git status --porcelain", wt)
    if not status.passed or status.tail.strip():
        return "skipped: changes"
    if not steps.run("rebase-fetch", "git fetch -q origin", wt).passed:
        return "skipped: fetch failed"
    if steps.run("rebase-current", f"git merge-base --is-ancestor {base} HEAD", wt).passed:
        return "current"
    done = steps.run("rebase", f"git rebase -q {base}", wt)
    if done.passed:
        return "rebased"
    steps.run("rebase-abort", "git rebase --abort", wt)
    tickets.red(_repo(card), steps.failed("rebase", f"rebase {card.id} onto {base}", done.tail), now)
    return "conflict: ticket filed"


def run(
    root: Path, still: Callable[[], bool], now: float, clock: Callable[[], float] = time.monotonic
) -> dict[str, object]:
    """Rebase waiting cards until the budget is spent; return the report."""
    began, done = clock(), {}
    for card in cards.waiting(root):
        if not still() or clock() - began > BUDGET:
            break
        done[card.id] = rebase_card(card, now)
    return {"cards": done}
