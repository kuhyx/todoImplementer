"""Assembles GET /api/board and GET /api/task/<item-id> from notes, run states and the live/limit context."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.asks.view import items as ask_items
from todoimpl.peer.book import thread_of
from todoimpl.runner.parsing import parse_questions

from .card import Context, build_card
from .umbrella import detail

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .state import RunState
    from .types import TaskLike

COLUMNS = (
    ("backlog", "Backlog"),
    ("running", "Running"),
    ("needs_you", "Needs you"),
    ("done", "Done"),
)


def repo_checker() -> Callable[[str | None], str | None]:
    """Return a function mapping a note's repo to its display path when an absolute repo is not a git repo.

    A relative repo (`owner/name`) is never missing: Start finds its checkout by origin or clones it (T2079).
    """

    def missing(repo: str | None) -> str | None:
        path = Path(repo).expanduser() if repo else None
        if path is None or not path.is_absolute() or (path / ".git").exists():
            return None
        home = str(Path.home())
        text = str(path)
        return "~" + text[len(home) :] if text.startswith(home + os.sep) else text

    return missing


def _ask_order(card: dict[str, Any]) -> tuple[int, int, float]:
    """Needs-you cards: questions first (however many), then least effort, then the longest waiting."""
    ask = card["needs"]
    if ask is None:
        return (0, 0, 0.0)
    return (ask["category"] != "questions", ask["effort"], card["updated"] or 0.0)


def build_board(
    tasks: Sequence[TaskLike], runs: dict[str, RunState], ctx: Context, build: str, known: Sequence[str] = ()
) -> dict[str, Any]:
    """Return the /api/board object: every note as a card, grouped by the four fixed columns.

    `repos` is the cards' repos plus `known` (GitHub repos with no note yet, T2413), so the filter and the
    new-task picker list a brand-new repo too.
    """
    built = [(build_card(task, runs.get(task.id), ctx), task.created_by == "claude") for task in tasks]
    order = [key for key, _ in COLUMNS]
    # Inside a column kuhy's own notes come first, then the Needs-you order.
    built.sort(key=lambda pair: (order.index(pair[0]["column"]), pair[1], *_ask_order(pair[0])))
    cards = [card for card, _ in built]
    return {
        "build": build,
        "generated_at": ctx.now,
        "slots": {"used": len(ctx.live)},
        "limit": ctx.limit.to_dict(),
        "auto_close": ctx.auto_close,
        "columns": [
            {"id": key, "label": label, "count": sum(1 for card in cards if card["column"] == key)}
            for key, label in COLUMNS
        ],
        "repos": sorted({*(task.repo for task in tasks if task.repo), *known}),
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


def _asks(card: dict[str, Any], run: RunState | None) -> list[dict[str, Any]]:
    """Return the cards of an open Claude question, so it reaches the spec questions' answer view (T1816)."""
    needs = card.get("needs")
    if run is None or needs is None or needs["kind"] != "claude_question":
        return []
    return [vars(q) for q in parse_questions(str(run.extra.get("last_reply", "")))]


def build_task(
    task: TaskLike, run: RunState | None, directory: Path, ctx: Context, diff: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the /api/task/<item-id> object: card, plan, questions, live check, checks, diff, session."""
    card = build_card(task, run, ctx)
    umbrella = detail(task, run)
    return {
        "card": card,
        "body": task.body or (run.note_body if run is not None and run.note_body is not None else ""),
        "done_check": task.done_check,
        "plan_md": _read(directory / "plan.md"),
        "questions": [vars(q).copy() for q in run.spec_questions] if run is not None else [],
        "asks": _asks(card, run),
        "ask_items": ask_items(task.body, run, directory, getattr(task, "parts", ())),
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
        **({"umbrella": umbrella} if umbrella is not None else {}),
        **({"peer": peer} if (peer := thread_of(directory)) else {}),
    }
