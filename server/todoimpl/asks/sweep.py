"""Sweep of the cards that wait on kuhy: classify, add an `ask` block to a card's section, drop a stray note.

`python -m todoimpl.asks.sweep report` prints the table (card, ask type, why); `add <card> <file>` appends the
block in <file> to that card's section of its note through the todo app (card text only, never code of another
repo) and logs the edit on this board's card; `drop-note <run dir> <text>` removes a stray note from a card.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl import atomic
from todoimpl.board.state import FILE, run_dir, run_root
from todoimpl.todo_mcp.items import sections

from . import store
from .parse import parse_asks

if TYPE_CHECKING:
    from collections.abc import Sequence

    from todoimpl.todo_mcp.client import TodoClient

CREDENTIAL = re.compile(r"credential|password|token|api[ _-]?key|secret|sign[- ]in|login", re.IGNORECASE)
PHYSICAL = re.compile(
    r"phone|nfc|haptic|on-device|physical|visual|drive to|buzzer|wearable|tag\b", re.IGNORECASE
)
COMMAND = re.compile(r"`!\s*[^`]+`|`[a-z][\w./ -]+`", re.IGNORECASE)
DECISION = re.compile(
    r"decide|pick|choice|call on|vs\b|\byes/no\b|\bok to\b|restate or drop|narrow", re.IGNORECASE
)
NO_NEED = "no Needs: line"


def classify(text: str) -> str:
    """Return the ask type of a card's ask text: credential, physical, command, decision, unclear."""
    if NO_NEED in text:
        return "unclear"
    for kind, pattern in (
        ("credential", CREDENTIAL),
        ("command", COMMAND),
        ("physical", PHYSICAL),
        ("decision", DECISION),
    ):
        if pattern.search(text):
            return kind
    return "unclear"


def table(rows: Sequence[tuple[str, str, str]]) -> str:
    """Return the markdown table of (card, ask type, what changed)."""
    lines = ["| card | ask type | change |", "| --- | --- | --- |"]
    lines += [f"| {card} | {kind} | {change} |" for card, kind, change in rows]
    return "\n".join(lines)


def add_ask(client: TodoClient, card: str, block: str, *, now: float | None = None) -> str:
    """Append the fenced `ask` block to section `card` (`<note id8>-<n>`); return the edit line."""
    if not parse_asks(block):
        msg = "the block is not a valid ask block"
        raise ValueError(msg)
    note_id, _, number = card.rpartition("-")
    task = client.get_task(note_id)
    found = sections(task.body)
    index = int(number)
    if index >= len(found):
        msg = f"{card}: section {index} not found"
        raise ValueError(msg)
    lines = task.body.split("\n")
    end = found[index + 1].heading if index + 1 < len(found) else len(lines)
    while end > found[index].heading + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:end] = ["", block.strip("\n")]
    client.update_task(note_id, body="\n".join(lines))
    return f"sweep: ask block added to {card} at {time.strftime('%F %H:%M', time.localtime(now))}"


def log_edit(directory: Path, line: str) -> None:
    """Record one sweep edit on the board card's ask log."""
    data = store.load(directory)
    data["log"].append(line)
    store.save(directory, data)


def drop_note(directory: Path, text: str) -> bool:
    """Remove the stray note `text` from the run's notes and log it; False when it is not there."""
    path = directory / FILE
    state = json.loads(path.read_text(encoding="utf-8"))
    notes = [n for n in state.get("notes", []) if n != text]
    if len(notes) == len(state.get("notes", [])):
        return False
    state["notes"] = notes
    atomic.write_text(path, json.dumps(state, ensure_ascii=False, indent=1))
    log_edit(directory, "stray itch note closed")
    return True


def main(argv: Sequence[str] | None = None, client: TodoClient | None = None) -> int:
    """CLI: report | add <card> <file> | drop-note <card> <text>."""
    parser = argparse.ArgumentParser(prog="todoimpl.asks.sweep")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    add = sub.add_parser("add")
    add.add_argument("card")
    add.add_argument("file", type=Path)
    add.add_argument("--log", help="board card whose log records the edit (default: the section id)")
    drop = sub.add_parser("drop-note")
    drop.add_argument("card")
    drop.add_argument("text")
    args = parser.parse_args(argv)
    root = run_root()
    if args.cmd == "drop-note":
        done = drop_note(run_dir(root, args.card), args.text)
        print("ok: stray note closed" if done else "nothing to drop")
        return 0 if done else 1
    if client is None:
        from todoimpl.todo_mcp.client import TodoClient  # noqa: PLC0415 - only the todo-app commands need it

        client = TodoClient.from_env()
    if args.cmd == "add":
        line = add_ask(client, args.card, args.file.read_text(encoding="utf-8"))
        log_edit(run_dir(root, args.log or args.card), line)
        print(line)
        return 0
    return report(client)


def report(client: TodoClient) -> int:
    """Print the table of every open Yours-style note section waiting on kuhy (read-only)."""
    rows = []
    for task in client.list_tasks(full=True):
        for number, part in enumerate(sections(task.body)):
            if part.done or not part.title.startswith("MANUAL WORK REQUIRED"):
                continue
            kind = "choice" if parse_asks("\n".join(part.lines)) else classify(part.title)
            rows.append((f"{task.id}-{number}", kind, part.title[:60]))
    print(table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
