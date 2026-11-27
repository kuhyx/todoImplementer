"""Chore: precompute each waiting card's next-turn context into `<run>/nolimit-context.md`.

Per waiting card, each one capped step under 60 s: the commits on top of `origin/<base>`, the diff stat
against it, the uncommitted files, and the output of the repo's `test-changed` command (CLAUDE.md, run in
the card's worktree) with the failing tests it names. The file stamps the HEAD it was made at; a card whose
file already matches its HEAD is skipped. `prompts.nolimitctx` points the next turn's prompt at the file.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from todoimpl import atomic

from . import cards, ctxfile, repos, steps, tickets

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BUDGET = 45.0
STAMP = "<!-- head {sha} -->"


def path(run_dir: Path) -> Path:
    """Return the card's context file."""
    return ctxfile.path(run_dir)


def _fresh(card: cards.Card, head: str) -> bool:
    try:
        return path(card.run_dir).read_text(encoding="utf-8").startswith(STAMP.format(sha=head))
    except OSError:
        return False


def _block(title: str, step: steps.Step) -> str:
    body = step.tail or "(nothing)"
    state = "ok" if step.passed else ("cut at 60 s" if step.slow else f"exit {step.exit_code}")
    return f"## {title} ({state}, {step.seconds:g} s)\n\n```\n{body}\n```\n"


def build(card: cards.Card, now: float) -> str:
    """Write the card's context file; return what happened."""
    wt, base = card.worktree, f"origin/{card.base}"
    head = steps.run("context-head", "git rev-parse HEAD", wt)
    if not head.passed:
        return "skipped: git failed"
    if _fresh(card, head.tail.strip()):
        return "current"
    parts = [
        STAMP.format(sha=head.tail.strip()),
        f"# Next-turn context of {card.id}, precomputed while Claude was out\n",
        f"Made {time.strftime('%Y-%m-%d %H:%M', time.localtime(now))} at HEAD {head.tail.strip()[:12]}.\n",
        _block(f"Commits on top of {base}", steps.run("context-log", f"git log --oneline {base}..HEAD", wt)),
        _block(f"Diff stat against {base}", steps.run("context-diff", f"git diff --stat {base}...HEAD", wt)),
        _block("Uncommitted files", steps.run("context-status", "git status --short", wt)),
    ]
    command = repos.commands_of(repos.claude_md(wt)).get("test-changed")
    if command:
        tests = steps.run("context-tests", command, wt)
        parts.append(_block(f"`{command}`", tests))
        if failing := tickets.failures(tests):
            parts.append("## Failing tests\n\n" + "".join(f"- `{t}`\n" for t in failing))
    atomic.write_text(path(card.run_dir), "\n".join(parts))
    return "written"


def run(
    root: Path, still: Callable[[], bool], now: float, clock: Callable[[], float] = time.monotonic
) -> dict[str, object]:
    """Write the context of waiting cards until the budget is spent; return the report."""
    began, done = clock(), {}
    for card in cards.waiting(root):
        if not still() or clock() - began > BUDGET:
            break
        done[card.id] = build(card, now)
    return {"cards": done}
