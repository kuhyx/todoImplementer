"""Research cards (DOCS-triage.md): a note of URLs gets a session with no repo, a report and choices to pick.

The session has no worktree: its cwd is `<run dir>/research`. It writes `research.md` (shown in the drawer as
the live-check report) and `research.json` (the suggested actions), and ends on `A:` with one `choice` per
action (`Make note` or `Skip`; the 24 h auto-adopt of DOCS-asks.md applies). When every choice is resolved the
server, not the model, makes a todo note per picked action and closes the research note.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.asks import store
from todoimpl.asks.parse import parse_asks
from todoimpl.asks.view import is_open
from todoimpl.merge.apply import MergeError
from todoimpl.merge.umbrella import create_umbrella
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.pipeline import Driver
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.asks.parse import Ask

MAKE = "Make note"
REPO = re.compile(r"[\w.-]+/[\w.-]+")
DONE_FILE = "research-done.json"


class ResearchDriver(Driver):
    """A Driver with no worktree and no spec or plan stage: the research session is the implement stage."""

    def _worktree(self) -> None:
        scratch = self.ctx.run_dir / "research"
        scratch.mkdir(parents=True, exist_ok=True)
        self.state.worktree = str(scratch)
        self.state.extra.update(research=True, tier="cheap")  # the turn plan reads `research` (tiering.py)
        self.save()

    def run(self) -> None:
        """Skip the stages a research note has no use for, then drive as usual."""
        if self.state.stage in ("spec", "plan"):
            self.state.stage = "implement"
        super().run()


def _choices(text: str) -> list[Ask]:
    return [ask for ask in parse_asks(text) if ask.type == "choice"]


def _read(directory: Path) -> tuple[str | None, Any]:
    """Return the note's deliverable and the action rows of `research.json`.

    The file is a plain list of actions, or `{"deliverable": "<line or null>", "actions": [...]}` (T2091).
    """
    try:
        data = json.loads((directory / "research.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None, None
    if not isinstance(data, dict):
        return None, data
    need = data.get("deliverable")
    return (need.strip() or None if isinstance(need, str) else None), data.get("actions")


def _deliverable(directory: Path) -> str | None:
    """Return what the research note itself asks to be made (a logo, a page), None when it asks for none."""
    return _read(directory)[0]


def _actions(directory: Path) -> dict[str, dict[str, Any]]:
    """Return the suggested actions the session wrote, keyed by choice id; malformed rows are dropped."""
    rows = _read(directory)[1]
    keep = {}
    for row in rows if isinstance(rows, list) else []:
        ok = isinstance(row, dict) and all(
            isinstance(row.get(k), str) and row[k].strip() for k in ("id", "title", "body")
        )
        repo = row.get("repo") if ok else None
        if ok and (repo is None or (isinstance(repo, str) and REPO.fullmatch(repo))):
            keep[row["id"]] = row
    return keep


def _made(directory: Path) -> dict[str, str]:
    try:
        data = json.loads((directory / DONE_FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _make_note(d: Driver, action: dict[str, Any]) -> str:
    """Add the action as a todo note: in its repo, or with no repo (triage routes it) through the todo CLI."""
    repo, title, body = action.get("repo"), action["title"].strip(), action["body"].strip()
    if repo:
        return d.ctx.client.add_task(repo, title, body).id[:8]
    return create_umbrella(f"{title}\n\n{body}")[:8]


def finish(d: Driver, choices: list[Ask]) -> str:
    """Make a note per picked action (once each, even on a retry), close the research note, end shipped.

    The note closes only when a made note `delivers` the note's own deliverable; else it stays open (T2091).
    """
    directory = d.ctx.run_dir
    answers, actions, made = store.load(directory)["items"], _actions(directory), _made(directory)
    failed = []
    for ask in choices:
        if (answers.get(ask.id) or {}).get("answer") != MAKE or ask.id in made or ask.id not in actions:
            continue
        try:
            made[ask.id] = _make_note(d, actions[ask.id])
        except (TodoError, MergeError) as exc:
            failed.append(f"{ask.id}: {exc}")
        atomic.write_text(directory / DONE_FILE, json.dumps(made))
    if failed:
        msg = "research note not made: " + "; ".join(failed)
        raise NeedsYouError(msg, "run_failed")
    skipped = len(choices) - len(made)
    notes = ", ".join(f"{key}={note}" for key, note in made.items()) or "none"
    need = _deliverable(directory)
    if need and not any(actions.get(key, {}).get("delivers") is True for key in made):
        msg = f"research note kept open: it asks for {need!r} and no note made delivers it (made: {notes})"
        raise NeedsYouError(msg, "run_failed")
    d.ctx.client.close_task(d.state.task_id, f"Research done: notes made {notes}; skipped {skipped}.")
    return "shipped"


def run_stage(d: Driver) -> str | None:
    """Run the implement stage of a research card: report and choices, then the notes once kuhy answered."""
    st, directory = d.state, d.ctx.run_dir
    asked = _choices(str(st.extra.get("last_reply", "")))
    items = store.load(directory)["items"]
    if asked and (directory / "research.json").exists() and not any(is_open(items.get(a.id)) for a in asked):
        return finish(d, asked)
    res = d.turn("implement", "research", prompt="research")
    report = directory / "research.md"
    st.live_check = {
        "report_md": report.read_text(encoding="utf-8") if report.exists() else res.text,
        "shots": [],
    }
    choices = _choices(res.text)
    if res.tag == "D" and not choices:
        return finish(d, [])
    if choices:
        st.last_tag = "A"  # the choices are the ask, whatever tag the session ended on
        return None
    return d.after_tag(res, "implement")
