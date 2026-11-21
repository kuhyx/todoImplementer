"""Heavy builds become tickets (T2424).

kuhy, 2026-11-21: "if we get a heavy build optimize the hell out of it". A build that holds a build slot for
over `LIMIT` s is heavy: three slots only help while builds are short. The hold ceiling files each such ticket
once into the contract report `<error state>/app-errors/heavy-builds.json`, against the repo of the card that
ran it (its run dir's state.json). The errors loop turns each record into a part of that repo's card
(DOCS-errors.md): make this build finish under 60 s.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.errors.sources import state_base
from todoimpl.runner.files import read_json

if TYPE_CHECKING:
    from pathlib import Path

    from .buildqueue import Ticket

LIMIT = 60.0  # s a build may hold a slot before it is heavy
FILE = "heavy-builds.json"
KIND = "perf.heavybuild"
MESSAGE = "a build held a build slot for over 60 s ({what}); make it finish under 60 s"
STEPS = frozenset({"run", "exec"})  # `uv run pytest`, `pnpm exec vitest`: the step is the next word
CHILDREN = "children"
NOT_APP = re.compile(r"[^a-z0-9_-]+")


def signature(command: str) -> str:
    """Return `heavy-<tool>-<step>`: the word after `run`/`exec`, else the first plain word or a flag."""
    words = command.split()
    tool = words[0].rsplit("/", 1)[-1] if words else "build"
    plain = [w for w in words[1:] if not w.startswith("-") and "/" not in w and "=" not in w]
    at = next((i for i, w in enumerate(plain[:-1]) if w in STEPS), None)
    if at is not None:
        plain = plain[at + 1 :]
    flags = [w.lstrip("-") for w in words[1:] if w.startswith("--") and "=" not in w]
    step = plain[0] if plain else (flags[-1] if flags else "")
    return "-".join(p for p in ("heavy", tool, step) if p)


def repo_of(root: Path, card: str) -> str | None:
    """Return the repo of a card's run dir (`<root>/<card>` or a child's `<root>/<id8>-0/children/<card>`)."""
    if card == "?":
        return None
    for run in (root / card, root / f"{card.split('-', 1)[0]}-0" / CHILDREN / card):
        data = read_json(run / "state.json")
        if isinstance(data, dict) and isinstance(data.get("repo"), str) and "/" in data["repo"]:
            return str(data["repo"])
    return None


def held_for(ticket: Ticket, now: float) -> float:
    """Return how long the ticket has held its slot (0 when its time does not parse)."""
    try:
        return now - time.mktime(time.strptime(ticket.since, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return 0.0


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat(timespec="seconds")


def file(ticket: Ticket, repo: str, now: float) -> None:
    """Count one more heavy run of this build in the report (a new record for a new repo and step)."""
    path = state_base() / "app-errors" / FILE
    data = read_json(path)
    errors: list[dict[str, Any]] = data.get("errors", []) if isinstance(data, dict) else []
    app = NOT_APP.sub("-", repo.rsplit("/", 1)[-1].lower()).strip("-") or "repo"
    sig = signature(ticket.command)
    record = next((e for e in errors if e.get("app") == app and e.get("signature") == sig), None)
    if record is None:
        record = {"app": app, "repo": repo, "signature": sig, "kind": KIND, "count": 0, "build": 0,
                  "message": MESSAGE.format(what=ticket.command), "first_seen": _iso(now)}  # fmt: skip
        errors.append(record)
    detail = f"card {ticket.card} held a slot {held_for(ticket, now):.0f} s: {ticket.command}"
    record.update(count=int(record["count"]) + 1, last_seen=_iso(now), detail=detail, open=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic.write_text(path, json.dumps({"version": 1, "errors": errors}, indent=2) + "\n")
