"""Addenda for the cheap tier (DOCS-tiers.md): Sonnet manages free models or works alone, or Opus does."""

from __future__ import annotations

from pathlib import Path

GIVE_UP = "If you cannot finish, end your reply with a line `ESCALATE: <reason>`."


def manager(worktree: Path, run_dir: Path, worker: str, repo: str) -> str:
    """Sonnet as a manager: free models type through the server's worker command, Sonnet reviews."""
    return (
        "Tier cheap, free models allowed. You manage; free models do the edits. Per bounded sub-task "
        f"(small, one concern, files named) write it to a file in {run_dir} and run `timeout 3000 {worker} "
        f"{worktree} <sub-task file> {run_dir}/worker-<n>.log --issues {run_dir} --child {repo}`; never raw "
        "`claude-free` (it answers with a grilling round). The command exits 0 only when the worktree "
        "changed: judge by `git diff` and the checks, not by what the worker says. After each call read "
        "`git diff`, run the checks yourself, fix any permission block the worker hit, and redo or finish "
        f"whatever it botched. Log every free-model problem as one JSON line in {run_dir}/free-issues.jsonl: "
        "ts, child, phase (start|edit|tool-call|permission|checks|output), model, symptom (exact text, cut "
        "at 500 chars), action, fixed. Never hand it secrets or paths outside the worktree. "
        f"{GIVE_UP}"
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
