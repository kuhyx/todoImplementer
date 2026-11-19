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


def source(body: str, run: RunState | None, parts: Iterable[Part] = ()) -> list[Ask]:
    """Return the asks of the newest reply, else those of the body and of a repo card's parts.

    A manual part's asks are kuhy's own decisions on the same card (T2114): they show beside the reply's.
    """
    reply = str(run.extra.get("last_reply", "")) if run is not None else ""
    found = parse_asks(reply)
    current = bool(found)
    found = found or parse_asks(body)
    for part in parts:
        if current and not part.manual:
            continue
        found += [a for a in parse_asks(part.body) if all(a.id != b.id for b in found)]
    return found


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


def decided(body: str, directory: Path) -> list[str]:
    """Return `<title>: <answer>` for every answered choice of the text, in block order."""
    data = store.load(directory)
    answers = ((a, data["items"].get(a.id) or {}) for a in parse_asks(body) if a.type == "choice")
    return [f"{a.title}: {rec['answer']}" for a, rec in answers if not is_open(rec) and "answer" in rec]
