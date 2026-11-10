"""Addenda for the cheap tier (DOCS-tiers.md): Opus manages free models or works alone."""

from __future__ import annotations

from pathlib import Path

from .coach import COACHING

GIVE_UP = "If you cannot finish, end your reply with a line `ESCALATE: <reason>`."


def manager(worktree: Path, run_dir: Path, worker: str, repo: str, rules: str = "") -> str:
    """Opus as a manager: free models type through the server's worker command, Opus coaches them.

    `rules` (the textgate rules) go at the top of every sub-task file: the worker has no skill context.
    """
    given = f" Start every sub-task file with these rules, verbatim:\n{rules}\n" if rules else ""
    return (
        "Tier cheap, free models allowed. You manage; free models do the edits. Per bounded sub-task "
        f"(small, one concern, files named) write it to a file in {run_dir} and run `timeout 3000 {worker} "
        f"{worktree} <sub-task file> {run_dir}/worker-<n>.log --issues {run_dir} --child {repo}`; never raw "
        "`claude-free` (it answers with a grilling round). The command exits 0 only when the worktree "
        "changed: judge by `git diff` and the checks, not by what the worker says. After each call read "
        "`git diff`, run the checks yourself and fix any permission block the worker hit. "
        f"{COACHING} "
        f"Log every free-model problem as one JSON line in {run_dir}/free-issues.jsonl: "
        "ts, child, phase (start|edit|tool-call|permission|checks|output|prompt), model, symptom (exact "
        "text, cut at 500 chars), action, fixed. Never hand it secrets or paths outside the worktree."
        f"{given} {GIVE_UP}"
    )


def alone(why: str) -> str:
    """Opus without free models: the repo is private or the gateway is down."""
    return f"Tier cheap, free models not available ({why}): do the work yourself, no claude-free. {GIVE_UP}"


def escalated(reason: str) -> str:
    """Higher effort after the cheaper tier gave up or failed: the normal prompt plus why."""
    return (
        f"Escalation: the cheaper tier (Opus at medium effort managing free models) did not finish: "
        f"{reason}. "
        "You are the last tier, at higher effort: run `git status` and `git diff`, keep what is sound, "
        "do the rest yourself (no claude-free, no ESCALATE)."
    )
