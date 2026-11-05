"""Assembles GET /api/board and GET /api/task/<item-id> from notes, run states and the live/limit context."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .card import Context, build_card
from .repos import repo_path

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .state import RunState
    from .types import TaskLike

COLUMNS = (
    ("backlog", "Backlog"),
    ("running", "Running"),
    ("needs_you", "Needs you"),
    ("ready", "Ready to ship"),
    ("done", "Done"),
)


def repo_checker(src_root: Path | None = None) -> Callable[[str | None], str | None]:
    """Return a function mapping a note's repo to its display path when that is not a git repo on disk.

    A relative repo is looked up under `src_root` (`$TODOIMPL_SRC`, default `~/src`); absolute and `~` as is.
    """

    def missing(repo: str | None) -> str | None:
        if not repo:
            return None
        path = Path(repo).expanduser()
        path = path if path.is_absolute() else repo_path(repo, src_root)
        if (path / ".git").exists():
            return None
        home = str(Path.home())
        text = str(path)
        return "~" + text[len(home) :] if text.startswith(home + os.sep) else text

    return missing


def build_board(
    tasks: Sequence[TaskLike], runs: dict[str, RunState], ctx: Context, build: str
) -> dict[str, Any]:
    """Return the /api/board object: every note as a card, grouped by the five fixed columns."""
    cards = [build_card(task, runs.get(task.id), ctx) for task in tasks]
    order = [key for key, _ in COLUMNS]
    cards.sort(key=lambda card: order.index(card["column"]))
    return {
        "build": build,
        "generated_at": ctx.now,
        "slots": {"used": len(ctx.live)},
        "limit": ctx.limit.to_dict(),
        "columns": [
            {"id": key, "label": label, "count": sum(1 for card in cards if card["column"] == key)}
            for key, label in COLUMNS
        ],
        "repos": sorted({task.repo for task in tasks if task.repo}),
        "tasks": cards,
    }


def _read(path: Path) -> str | None:
    """Return the file text, None when it does not exist."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def resume_command(run: RunState | None) -> str | None:
    """Return `cd <worktree> && claude --resume <id>`, None without a session and a worktree."""
    if run is None or not run.session_id or not run.worktree:
        return None
    return f"cd {shlex.quote(run.worktree)} && claude --resume {shlex.quote(run.session_id)}"


def _stages(run: RunState | None) -> list[dict[str, Any]]:
    """Return the stage history; a run that recorded none gets its current stage."""
    if run is None:
        return []
    if run.stages:
        return run.stages
    return [{"stage": run.stage, "started": run.started_at or run.updated, "ended": None}]


def build_task(
    task: TaskLike, run: RunState | None, directory: Path, ctx: Context, diff: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the /api/task/<item-id> object: card, plan, questions, live check, checks, diff, session."""
    return {
        "card": build_card(task, run, ctx),
        "body": task.body,
        "done_check": task.done_check,
        "plan_md": _read(directory / "plan.md"),
        "questions": [vars(q).copy() for q in run.spec_questions] if run is not None else [],
        "checks": run.checks if run is not None else None,
        "live_check": run.live_check if run is not None else None,
        "self_check": run.self_check if run is not None else [],
        "diff": diff,
        "stages": _stages(run),
        "skills_loaded": run.skills_loaded if run is not None else [],
        "worktree": run.worktree if run is not None else None,
        "branch": run.branch if run is not None else None,
        "resume_command": resume_command(run),
        "lesson": run.lesson if run is not None else None,
        "error": run.error if run is not None else None,
    }
