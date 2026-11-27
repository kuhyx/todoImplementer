"""The token optimization note the board files after a usage reset: text, part, ~/.claude worktree.

`resetwatch.py` decides when; this module says what. The part's identity is its `Reset-Key: <iso>` line (the
reset instant), so a restart or a merge finds the note again instead of filing a second one. kuhy's steps
are quoted as he wrote them (2026-11-27). The note is user content read by a session, not a screen.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.errors.marks import RESET_KEY, is_tokenopt_run

from .worktree import GitError, git

if TYPE_CHECKING:
    from collections.abc import Iterable

    from todoimpl.board.state import RunState
    from todoimpl.service.cards import CardTask

log = logging.getLogger("todoimpl.runner")
REPO = "kuhyx/todoImplementer"
PRIORITY = "high"
WORKTREE = "claude-wt"  # <run dir>/claude-wt: a detached worktree of ~/.claude, in the session's dirs
FEED = "token optimization after reset"
GOAL = (
    "Cut Claude token usage after this usage reset, by kuhy's steps below. Do not ask kuhy anything; "
    "take recommended answers."
)
DONE = (
    "done: the previous optimization is scored, the new optimizations are shipped and deployed, and the "
    "skills `token-dashboard` and `token-optimization` hold what this round learned."
)
STEPS = (
    "1. Check if previous optimization worked",
    "2. Analyze token usage and figure out how to optimize it (with the goal of minimizing token usage)",
    (
        "3. Optimize the hell out of it, solutions take priority in order: a) anything that can run "
        "completely tokenless (pure algorithms, ordinary scripts, pipelines, regular code) b) anything that "
        "can run on free models using omniroute only c) anything that can run on claude haiku d) claude "
        "sonnet e) anything that optimizes how claude works itself"
    ),
    "4. Implement those optimizations, improve the optimization skills with the insights",
)
WHERE = (
    "Skills: `token-dashboard` (the token-dashboard MCP tools) and `token-optimization` (the audit). "
    f"Repos: this one ({REPO}) and ~/.claude, through `{WORKTREE}` in your run dir: a worktree of ~/.claude "
    "that is in your dirs. Commit ~/.claude changes there, rebase onto `origin/main`, push fast-forward only "
    "(`git push origin HEAD:main`, never forced) and run the deploy command of ~/.claude/CLAUDE.md "
    "(`## Commands`, `deploy:`). Write no other repo."
)


def iso(instant: float) -> str:
    """Return the reset instant as the key: UTC ISO to the second."""
    return datetime.fromtimestamp(int(instant), UTC).isoformat()


def title(key: str) -> str:
    """`Token optimization after reset <date>` (the reset's UTC date)."""
    return f"Token optimization after reset {key[:10]}"


def body(key: str) -> str:
    """Return the part's text: goal, done line, kuhy's steps, the skills and repos, the identity line."""
    return "\n".join([GOAL, DONE, "", *STEPS, "", WHERE, "", f"Reset-Key: {key}"])


@dataclass(frozen=True)
class Found:
    """The open part of a reset: the card that holds it and its note."""

    card: str
    note: str


def find(cards: Iterable[CardTask], key: str) -> Found | None:
    """Return the open part whose `Reset-Key:` line is `key`, looking at every part of every open card."""
    for card in cards:
        if card.status in ("done", "abandoned"):
            continue
        held = [(p.note_id, p.body) for p in card.parts] or [(card.item.note_id, card.body)]
        for note, text in held:
            if key in RESET_KEY.findall(text):
                return Found(card.id, note)
    return None


def claude_home() -> Path:
    """`$CLAUDE_CONFIG_DIR`, else ~/.claude: the repo the session improves."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(base) if base else Path.home() / ".claude"


def ensure_worktree(run_dir: Path, home: Path | None = None) -> str | None:
    """Add `<run dir>/claude-wt` as a detached worktree of ~/.claude's main; return why it failed, else None.

    Detached, so a second cycle never trips over a branch the first one made. An existing clean one moves to
    today's main (the card's run dir is the same every week); a dirty one is kept, and that is named.
    """
    target = run_dir / WORKTREE
    if (target / ".git").exists():
        return _refresh(target)
    run_dir.mkdir(parents=True, exist_ok=True)
    repo = ("-C", str(home or claude_home()), "worktree")
    try:
        git(run_dir, *repo, "prune")  # a run dir deleted by hand leaves its worktree registered: add refuses
        git(run_dir, *repo, "add", "--detach", str(target), "main")
    except GitError as exc:
        log.warning("token optimization: no ~/.claude worktree at %s: %s", target, exc.text)
        return exc.text
    return None


def _refresh(target: Path) -> str | None:
    """Move a clean kept worktree to main; return why it stays where it is, else None."""
    try:
        if git(target, "status", "--porcelain").stdout.strip():
            why = f"{target} has uncommitted work from an earlier round: kept as it is"
            log.warning("token optimization: %s", why)
            return why
        git(target, "checkout", "-q", "--detach", "main")
    except GitError as exc:
        log.warning("token optimization: ~/.claude worktree at %s not moved: %s", target, exc.text)
        return exc.text
    return None


def dirs(st: RunState, run_dir: Path) -> tuple[Path, ...]:
    """Return the extra dirs of a tokenopt run's turns: its ~/.claude worktree once it exists."""
    target = run_dir / WORKTREE
    return (target,) if is_tokenopt_run(st) and target.is_dir() else ()
