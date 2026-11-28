"""The ship ledger: one `ships.jsonl` line per part a Ship (or a Close) finished, to price a shipped part.

`new_cycle` clears the sessions of the cycle that shipped, so the join the usage page needs (part ->
sessions -> cost) is written at close time, before that reset. The file sits in the run root beside the
other board-wide ledgers (`credits-ledger.jsonl`) and is append-only, written durably (`todoimpl.atomic`).

Line: `{card, part, title, repo, cycle, at (ISO, UTC), kind (ship | close | done_manually), sessions: [id]}`.
`sessions` are the cycle's sessions: every session with a result event in a stream the cycle started, plus
the role sessions the state names. Parts shipped together share them; readers split the cost by part
(`tokens_api/ships.py`).

`python -m todoimpl.repotask.ledger backfill` adds the last shipped cycle of every run that has none yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.board.state import run_root
from todoimpl.runner.files import STREAM_SUFFIX, read_json
from todoimpl.tokens.items import stream_sessions

from . import files

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

FILE = "ships.jsonl"
STATE = "state.json"


def _iso(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, UTC).isoformat(timespec="seconds")


def _epoch(stream: Path) -> float:
    """Return the epoch part of `<role>-<epoch>.stream.jsonl` (0 when the name has none)."""
    try:
        return float(stream.name.removesuffix(STREAM_SUFFIX).rsplit("-", 1)[1])
    except IndexError, ValueError:
        return 0.0


def cycle_sessions(run_dir: Path, state: dict[str, Any]) -> list[str]:
    """Return the session ids of the run's current cycle, oldest first (streams since the cycle floor)."""
    floor = state.get("cycle_at")
    start = float(floor) if isinstance(floor, int | float) else 0.0
    found: dict[str, None] = {}
    for stream in sorted((p for p in run_dir.glob(f"*{STREAM_SUFFIX}") if _epoch(p) >= start), key=_epoch):
        found.update(dict.fromkeys(stream_sessions(stream)))
    roles = state.get("sessions")
    for entry in roles.values() if isinstance(roles, dict) else ():
        sid = entry.get("session_id") if isinstance(entry, dict) else None
        if isinstance(sid, str) and sid:
            found[sid] = None
    return list(found)


def _lines(
    card: str, state: dict[str, Any], kind: str, at: float, sessions: list[str]
) -> Callable[[Iterable[tuple[str, str]]], list[str]]:
    """Return a function turning `(part key, title)` pairs into ledger lines of one close."""
    repo, cycle = state.get("repo"), state.get("cycle")
    base = {
        "card": card,
        "repo": repo if isinstance(repo, str) else "",
        "cycle": int(cycle) if isinstance(cycle, int | float) else 1,
        "at": _iso(at),
        "kind": kind,
        "sessions": sessions,
    }
    return lambda parts: [json.dumps({**base, "part": k, "title": t}, sort_keys=True) for k, t in parts]


def record(root: Path, card: str, parts: Iterable[tuple[str, str]], kind: str, now: float) -> int:
    """Append one line per `(part key, title)` of `card`; return how many. Call before `new_cycle`."""
    run_dir = root / card
    state = read_json(run_dir / STATE)
    state = state if isinstance(state, dict) else {}
    return len(_append(root, _lines(card, state, kind, now, cycle_sessions(run_dir, state))(parts)))


def read(root: Path) -> list[dict[str, Any]]:
    """Return the ledger's lines in order; a torn or foreign line is skipped."""
    try:
        text = (root / FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[Any] = []
    for line in text.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return [r for r in rows if isinstance(r, dict) and isinstance(r.get("sessions"), list)]


def backfill(root: Path) -> int:
    """Add the last shipped cycle of each run with no ledger line for that cycle; return the lines added.

    Older cycles are gone: `new_cycle` cleared their ticks and sessions. Only a state that still holds `ship`
    (the cycle that closed) is read; its parts are the ticked keys, or the card itself for a section card.
    """
    have = {(r.get("card"), r.get("cycle")) for r in read(root)}
    added = 0
    for state_file in sorted(root.glob(f"*/{STATE}")):
        state, run_dir = read_json(state_file), state_file.parent
        ship = state.get("ship") if isinstance(state, dict) else None
        closed = ship.get("closed_at") if isinstance(ship, dict) else None
        if not isinstance(closed, int | float):
            continue
        cycle = int(state.get("cycle") or 1)
        if (run_dir.name, cycle) in have:
            continue
        keys = list(files.read(run_dir).done) if state.get("repotask") else [run_dir.name]
        title = str(state.get("repotask_title") or "")
        lines = _lines(run_dir.name, state, "ship", closed, cycle_sessions(run_dir, state))
        added += len(_append(root, lines([(k, title) for k in keys])))
    return added


def _append(root: Path, lines: list[str]) -> list[str]:
    for line in lines:
        atomic.append_line(root / FILE, line)
    return lines


def main(argv: list[str] | None = None) -> int:
    """`backfill [--root DIR]`: print how many lines were added."""
    cli = argparse.ArgumentParser(prog="ledger", description="Ship ledger tools.")
    cli.add_argument("action", choices=["backfill"])
    cli.add_argument("--root", type=Path, default=None)
    args = cli.parse_args(argv)
    print(f"added {backfill(args.root or run_root())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
