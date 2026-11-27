"""Chore: remove the worktrees and branches of ended cards (shipped, closed, done manually, cancelled).

Per ended card, every git call one capped step under 60 s:
- a worktree with changes git would keep (`git status --porcelain`) stays, reported as kept;
- otherwise its size is measured (`du -sb`) and `git worktree remove --force` runs from the repo that owns it
  (`--force` only drops ignored files such as node_modules; tracked or new files were ruled out above);
- its branch is deleted only when its tip is already on origin (`git branch -r --contains`): a cancelled
  card's unpushed commits keep their branch, which costs no disk.
Nothing outside `.git` of kuhy's checkout is written; a busy card (turn in flight) is never touched.
"""

from __future__ import annotations

import shlex
import time
from typing import TYPE_CHECKING

from . import cards, steps

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BUDGET = 45.0  # seconds of one chore run; the rest waits for the next turn of the rotation


def _out(name: str, command: str, cwd: Path) -> str | None:
    """Run one capped step; return its output, None when it failed or was cut."""
    done = steps.run(name, command, cwd)
    return done.tail if done.passed else None


def prune_card(card: cards.Card) -> tuple[str, int]:
    """Prune one ended card; return (what happened, bytes freed)."""
    wt = card.worktree
    left = _out("prune-status", "git status --porcelain", wt)
    if left is None or left.strip():
        return "kept: changes", 0
    common = _out("prune-common", "git rev-parse --path-format=absolute --git-common-dir", wt)
    size = _out("prune-du", f"du -sb {shlex.quote(str(wt))} | cut -f1", wt.parent)
    if common is None or size is None:
        return "kept: git failed", 0
    repo = shlex.quote(common.strip().removesuffix("/.git"))
    on_origin = bool((_out("prune-pushed", "git branch -r --contains HEAD", wt) or "").strip())
    if (
        _out("prune-remove", f"git -C {repo} worktree remove --force {shlex.quote(str(wt))}", wt.parent)
        is None
    ):
        return "kept: remove failed", 0
    freed = int(size.strip() or 0)
    if card.branch and on_origin:
        _out("prune-branch", f"git -C {repo} branch -q -D {shlex.quote(card.branch)}", wt.parent)
        return "removed, branch deleted", freed
    return "removed, branch kept", freed


def run(
    root: Path, still: Callable[[], bool], clock: Callable[[], float] = time.monotonic
) -> dict[str, object]:
    """Prune ended cards until the budget is spent; return the report the strip and the CLI show."""
    began, done, freed = clock(), {}, 0
    for card in cards.all_cards(root):
        if not card.ended or card.busy:
            continue
        if not still() or clock() - began > BUDGET:
            break
        what, size = prune_card(card)
        done[card.id], freed = what, freed + size
    return {"cards": done, "freed_bytes": freed}
