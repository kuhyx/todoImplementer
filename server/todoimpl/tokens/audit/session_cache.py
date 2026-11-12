"""Load a transcript's window :class:`Session`, from the file cache when valid (T1997).

One pass per file: turns, tool calls and the image estimate come from the same
event stream (the audit used to parse each file twice). The result is cached
only when the file's own record timestamps all fall inside the window, because
then the window removed nothing and the result is the same for any window that
still contains them. A file cut by the window is parsed fresh every time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.tokens.audit import filecache, imagecost, parse, records
from todoimpl.tokens.audit.model import Session, ToolCall, Turn

if TYPE_CHECKING:
    from pathlib import Path

KIND = "session"


def _dump(session: Session, bounds: records.Bounds) -> dict[str, Any]:
    return {
        "low": bounds.low,
        "high": bounds.high,
        "image_cost": session.image_cost,
        "turns": [
            [t.usage, t.context, t.model, t.is_sidechain, t.message_id, t.tool_calls, t.timestamp]
            for t in session.turns
        ],
        "tools": [[c.name, c.result_tokens, c.path, c.skill, c.commit] for c in session.tools],
    }


def _restore(session: Session, data: dict[str, Any]) -> Session:
    session.turns = [Turn(*row) for row in data["turns"]]
    session.tools = [ToolCall(*row) for row in data["tools"]]
    session.image_cost = data["image_cost"]
    return session


def _covers(data: dict[str, Any], window: records.Window) -> bool:
    bounds = records.Bounds()
    bounds.low, bounds.high = data["low"], data["high"]
    return bounds.inside(window)


def load(path: Path, window: records.Window) -> Session:
    """Return the session of ``path`` restricted to ``window``."""
    data = filecache.load(KIND, path)
    if data is not None and _covers(data, window):
        return _restore(parse.new_session(path), data)
    bounds = records.Bounds()
    events = list(parse.iter_events(path, window, bounds))
    session = imagecost.annotate(parse.fill(parse.new_session(path), events), events)
    if bounds.inside(window):
        filecache.store(KIND, path, _dump(session, bounds))
    return session
