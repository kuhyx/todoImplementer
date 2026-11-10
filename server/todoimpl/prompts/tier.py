"""Addenda for the cheap tier (DOCS-tiers.md): Sonnet manages free models or works alone, or Opus does."""

from __future__ import annotations

from pathlib import Path

GIVE_UP = "If you cannot finish, end your reply with a line `ESCALATE: <reason>`."


def manager(worktree: Path) -> str:
    """Sonnet as a manager: the free models type, Sonnet reviews, checks and repairs."""
    return (
        "Tier cheap, free models allowed. You manage; free models do the edits. From "
        f"{worktree} run `timeout 55 claude-free -p '<one bounded sub-task>' --permission-mode "
        "bypassPermissions` per sub-task (small, one concern, files named). After each call read "
        "`git diff`, run the checks yourself, fix any permission block the worker hit, and redo or finish "
        f"whatever it botched. Never hand it secrets or paths outside the worktree. {GIVE_UP}"
    )


def alone(why: str) -> str:
    """Sonnet without free models: the repo is private or the gateway is down."""
    return f"Tier cheap, free models not available ({why}): do the work yourself, no claude-free. {GIVE_UP}"


def escalated(reason: str) -> str:
    """Opus after the cheaper tier gave up or failed: the normal prompt plus why."""
    return (
        f"Escalation: the cheaper tier (Sonnet managing free models) did not finish: {reason}. "
        "You are the last tier: run `git status` and `git diff`, keep what is sound, do the rest yourself "
        "(no claude-free, no ESCALATE)."
    )
