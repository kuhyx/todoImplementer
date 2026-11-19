"""The `ask_items` of a task detail: parsed asks joined with their saved state (ask.schema.json)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import allow, store
from .parse import Ask, parse_asks

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.repotask.model import Part

DAY = 24 * 3600.0
RESOLVED = ("answered", "auto", "done", "approved")


def _add(found: list[Ask], parts: Iterable[Part], *, manual: bool) -> list[Ask]:
    for part in parts:
        if part.manual == manual:
            found += [a for a in parse_asks(part.body) if all(a.id != b.id for b in found)]
    return found


def work_asks(body: str, run: RunState | None, parts: Iterable[Part] = ()) -> list[Ask]:
    """Return the asks of the newest reply, else those of the body and of the card's non-manual parts."""
    reply = str(run.extra.get("last_reply", "")) if run is not None else ""
    if found := parse_asks(reply):
        return found
    return _add(parse_asks(body), parts, manual=False)


def source(body: str, run: RunState | None, parts: Iterable[Part] = ()) -> list[Ask]:
    """Return every ask the card shows: the work's, then those of its manual parts.

    A manual part's asks are kuhy's own decisions on the same card (T2114): they show beside the reply's.
    """
    parts = list(parts)
    return _add(work_asks(body, run, parts), parts, manual=True)


def is_open(record: dict[str, Any] | None) -> bool:
    """Return True while the ask waits for kuhy (no record, undone, or rejected)."""
    return not record or record.get("state") in ("open", "rejected")


def _item(ask: Ask, record: dict[str, Any] | None, root: Path, seen: float | None) -> dict[str, Any]:
    out: dict[str, Any] = {"id": ask.id, "type": ask.type, "title": ask.title, "risk": ask.risk}
    out["state"] = (
        "open" if is_open(record) and (record or {}).get("state") != "rejected" else (record or {})["state"]
    )
    if ask.type == "choice":
        out |= {"options": list(ask.options), "recommended": ask.recommended}
        if ask.risk == "reversible" and out["state"] == "open" and seen is not None:
            out["auto_at"] = seen + DAY
    if ask.type == "command":
        out |= {"command": ask.command, "mode": allow.mode(root, ask.command or "")}
        out["warning"] = out["mode"] == "terminal"
    if ask.type == "screenshot" and ask.shot:
        out["shot"] = ask.shot
    for key in ("answer", "at", "result"):
        if record and key in record:
            out[key] = record[key]
    return out


def items(
    body: str, run: RunState | None, directory: Path, parts: Iterable[Part] = ()
) -> list[dict[str, Any]]:
    """Return the contract list for one card; empty when the note has no valid ask block."""
    asks = source(body, run, parts)
    if not asks:
        return []
    data = store.load(directory)
    return [_item(a, data["items"].get(a.id), directory.parent, data["seen"].get(a.id)) for a in asks]


def released(body: str, directory: Path) -> bool:
    """Return True when the text has an ask block and kuhy resolved every ask in it (T1994)."""
    asks = parse_asks(body)
    data = store.load(directory)
    return bool(asks) and not any(is_open(data["items"].get(a.id)) for a in asks)


def held(body: str, run: RunState | None, directory: Path, parts: Iterable[Part] = ()) -> list[str]:
    """Return `<title>: <answer>` of the session's answered choices that still wait for an open one (T2275).

    The session hears the answers once no choice is open (`AskService._resolve`); a note sent before that
    carries them, so a note never drops an answer. A manual part's answers are kuhy's own and never carried.
    """
    choices = [a for a in work_asks(body, run, parts) if a.type == "choice"]
    records = store.load(directory)["items"]
    if not any(is_open(records.get(a.id)) for a in choices):
        return []
    found = ((a, records.get(a.id)) for a in choices)
    return [f"{a.title}: {rec['answer']}" for a, rec in found if rec and not is_open(rec) and "answer" in rec]


def decided(body: str, directory: Path) -> list[str]:
    """Return `<title>: <answer>` for every answered choice of the text, in block order."""
    data = store.load(directory)
    answers = ((a, data["items"].get(a.id) or {}) for a in parse_asks(body) if a.type == "choice")
    return [f"{a.title}: {rec['answer']}" for a, rec in answers if not is_open(rec) and "answer" in rec]
