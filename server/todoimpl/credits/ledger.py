"""The credit ledger: one durable line per finished turn, on either route, and what it cost that turn.

A result event's `total_cost_usd` is cumulative for its session, and a session resumes across turns and across
routes, so a turn's own cost is its total minus the previous turn's total in the same session (`delta`). The
ledger keeps `cumulative_usd` next to `delta_usd` so any line can be checked. A turn without a result event
(killed) has no cost: it counts as a turn at 0 and the next turn of its session pays the difference.

`<root>/credits-ledger.jsonl` is appended through `atomic.append_line` (fsynced; a torn last line is skipped
on read). When it is missing, `load` rebuilds it once from the streams under the run root. The server
keeps the turns in memory, so no request scans a stream.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

LEDGER_FILE = "credits-ledger.jsonl"
ROUTES = ("plan", "credits")
CHILDREN_DIR = "children"  # an umbrella's child run dirs: <root>/<card>/children/<child id>/ (runner.files)
STREAM_SUFFIX = ".stream.jsonl"
LOCK = threading.RLock()


@dataclass(frozen=True)
class Turn:
    """One ledger line."""

    stem: str
    task: str
    role: str
    route: str
    session_id: str | None
    cumulative_usd: float | None
    delta_usd: float
    ended_at: float


@dataclass
class Book:
    """The in-memory ledger of one run root."""

    turns: dict[str, Turn] = field(default_factory=dict)  # by stem: a stem written twice counts once
    last_cum: dict[str, float] = field(default_factory=dict)  # per session: its newest cumulative total

    def add(self, turn: Turn) -> None:
        """Keep the turn (replacing the same stem) and remember its session's total."""
        self.turns[turn.stem] = turn
        if turn.session_id and turn.cumulative_usd and turn.cumulative_usd > 0:
            self.last_cum[turn.session_id] = turn.cumulative_usd


_BOOKS: dict[Path, Book] = {}


def reset() -> None:
    """Forget every loaded ledger (tests; the files stay)."""
    with LOCK:
        _BOOKS.clear()


def delta(seen: dict[str, float], session_id: str | None, cumulative: float | None) -> float:
    """Return what a turn added to its session and remember the new total in `seen`.

    A positive total below the last one cannot be cumulative: the counter restarted (another route's process),
    so that turn's whole total is its cost. Zero or no total says nothing and costs nothing.
    """
    if cumulative is None or cumulative <= 0:
        return 0.0
    if not session_id:
        return cumulative
    prev = seen.get(session_id, 0.0)
    seen[session_id] = cumulative
    return cumulative if cumulative < prev else cumulative - prev


def _num(value: object) -> float | None:
    """Return the number, None for anything else (a bool is not a number here)."""
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _turn_of(raw: object) -> Turn | None:
    """Return the ledger line as a Turn; None for anything that is not a well-formed line."""
    if not isinstance(raw, dict):
        return None
    stem, route = raw.get("stem"), raw.get("route")
    paid, ended = _num(raw.get("delta_usd")), _num(raw.get("ended_at"))
    if not isinstance(stem, str) or route not in ROUTES or paid is None or ended is None:
        return None
    sid = raw.get("session_id")
    return Turn(
        stem, str(raw.get("task", "")), str(raw.get("role", "")), route,
        sid if isinstance(sid, str) else None, _num(raw.get("cumulative_usd")), paid, ended,
    )  # fmt: skip


def _read(path: Path, book: Book) -> None:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            turn = _turn_of(json.loads(line))
        except ValueError:
            continue
        if turn is not None:
            book.add(turn)


def _result_of(stream: Path) -> tuple[str | None, float | None]:
    """Return (session id, total cost) of the last result event of a stream; (None, None) without one."""
    found: tuple[str | None, float | None] = (None, None)
    for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"result"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            cost, sid = event.get("total_cost_usd"), event.get("session_id")
            found = (
                sid if isinstance(sid, str) else None,
                float(cost) if isinstance(cost, int | float) else None,
            )
    return found


def _ended(stream: Path, stem: str) -> float:
    """Return when the turn ended: the host's exit record, else the stream's last write."""
    try:
        ended = json.loads(stream.with_name(f"{stem}.exit.json").read_text(encoding="utf-8")).get("ended")
    except OSError, ValueError, AttributeError:
        ended = None
    return float(ended) if isinstance(ended, int | float) else stream.stat().st_mtime


def _route(stream: Path, stem: str) -> str:
    try:
        text = stream.with_name(f"{stem}.route").read_text(encoding="utf-8").strip()
    except OSError:
        return "plan"  # a turn with no route file is a plan turn
    return text if text in ROUTES else "plan"


def _backfill(root: Path, book: Book) -> None:
    """Rebuild the book from every stream under the run root, oldest turn first."""
    found: list[tuple[float, str, Path, str]] = []
    for run in [*root.glob("*/"), *root.glob(f"*/{CHILDREN_DIR}/*/")]:
        for stream in run.glob(f"*{STREAM_SUFFIX}"):
            stem = stream.name.removesuffix(STREAM_SUFFIX)
            found.append((_ended(stream, stem), stem, stream, run.name))
    seen: dict[str, float] = {}
    for ended, stem, stream, task in sorted(found, key=lambda f: f[:2]):
        sid, cost = _result_of(stream)
        book.add(
            Turn(stem, task, stem.rsplit("-", 1)[0], _route(stream, stem), sid, cost,
                 delta(seen, sid, cost), ended)
        )  # fmt: skip


def _line(turn: Turn) -> str:
    return json.dumps(asdict(turn), ensure_ascii=False)


def book(root: Path) -> Book:
    """Return the root's ledger, loading it (and the one-time backfill) on first use."""
    with LOCK:
        found = _BOOKS.get(root)
        if found is not None:
            return found
        found = _BOOKS[root] = Book()
        path = root / LEDGER_FILE
        if path.exists():
            _read(path, found)
        else:
            _backfill(root, found)
            if found.turns:
                atomic.write_text(path, "".join(_line(t) + "\n" for t in found.turns.values()))
        return found


def load(root: Path) -> int:
    """Load the ledger at server start (rebuilding it once if missing); return how many turns it holds."""
    return len(book(root).turns)


def record(  # noqa: PLR0913 - one ledger line
    root: Path, *, task: str, stem: str, role: str, route: str, session_id: str | None,
    cumulative: float | None, ended_at: float, estimate: float = 0.0,
) -> float:  # fmt: skip
    """Append the turn that just ended and return its own cost (see `delta`).

    A turn with no result event has no total; `estimate` (what its usage adds up to, list price) stands in for
    its cost, so a credit turn stopped by the cap is paid for in the credit spend.
    """
    with LOCK:
        mine = book(root)
        prior = mine.turns.get(stem)
        if prior is not None and prior.cumulative_usd == cumulative:
            return (
                prior.delta_usd
            )  # already there (the backfill saw this stream, or a crash replays the turn)
        paid = delta(mine.last_cum, session_id, cumulative) if cumulative is not None else estimate
        turn = Turn(stem, task, role, route, session_id, cumulative, paid, ended_at)
        atomic.append_line(root / LEDGER_FILE, _line(turn))
        mine.add(turn)
        return paid


def spent(root: Path, since: float, route: str = "credits") -> float:
    """Return the cost, at the SDK's list price, of the route's turns that ended at or after `since`."""
    with LOCK:
        return sum(t.delta_usd for t in book(root).turns.values() if t.route == route and t.ended_at >= since)


def turns(root: Path, since: float, route: str = "credits") -> int:
    """Return how many of the route's turns ended at or after `since` (killed ones included)."""
    with LOCK:
        return sum(1 for t in book(root).turns.values() if t.route == route and t.ended_at >= since)
