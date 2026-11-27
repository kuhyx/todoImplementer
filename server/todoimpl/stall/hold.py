"""Hold a quiet card while a sub-agent's request is out, then judge the quiet by the answer's tokens (T2563).

A sub-agent thinking writes nothing until its block is done (`stall/request.py`), so a card quiet for a
minute while one of its sub-agents has a request out is not filed yet: it is held, at most `HOLD` s from the
request. When the answer comes, the model is taken to have written its tokens at `FLOOR` tokens/s up to the
answer (the slowest of 111 sub-agent requests over 30 s on 2026-11-27 ran at 82, its wait included); the
quiet left before that, cut where the card's own work came back, is filed when over the limit. A request
with no answer by `HOLD` lets the watch file the quiet as any other. `stalls-held.json` keeps the holds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.runner import orphans
from todoimpl.runner.files import read_json, write_json

from . import report, request, subagent

if TYPE_CHECKING:
    from .scan import Running

HOLD = 240.0  # s from the request a quiet card is held, like an advisor call (`advisor.ADVISOR`)
FLOOR = 80.0  # output tokens/s the model is taken to write at; lower credits a wait as writing
FILE = "stalls-held.json"
SIGNATURE = "stall-model"


@dataclass(frozen=True)
class Held:
    """One held quiet: the card, its `since`, the request's transcript and send time, when work came back."""

    card: str
    since: float
    path: str
    sent: float
    back: float | None = None


def key(card: str, since: float) -> str:
    """Return the key of one quiet of one card: a card can have a second quiet while the first is held."""
    return f"{card}@{since!r}"


def load(root: Path) -> dict[str, Held]:
    """Return the held quiets; a torn or foreign entry is dropped."""
    data = read_json(root / FILE)
    held: dict[str, Held] = {}
    for name, raw in (data if isinstance(data, dict) else {}).items():
        try:
            held[name] = Held(**raw)
        except TypeError:
            continue
    return held


def save(root: Path, held: dict[str, Held]) -> None:
    """Remember the held quiets."""
    write_json(root / FILE, {name: asdict(h) for name, h in held.items()})


def asking(run_dir: Path, now: float) -> tuple[str, float] | None:
    """Return the transcript and send time of the card's oldest sub-agent request out for under `HOLD` s."""
    rec = orphans.read(run_dir)
    if rec is None:
        return None
    paths = subagent.transcripts(run_dir / f"{rec.stem}.stream.jsonl", now - HOLD)
    out = [(sent, str(p)) for p in paths if (sent := request.asked(p)) is not None and now - sent <= HOLD]
    if not out:
        return None
    sent, path = min(out)
    return path, sent


def quiet(held: Held) -> float | None:
    """Return how long the held quiet was once its request is answered, None while it is still out."""
    if (got := request.answer(Path(held.path), held.sent)) is None:
        return None
    at, tokens = got
    end = at - tokens / FLOOR
    if held.back is not None:
        end = min(end, held.back)
    return end - held.since


def _file(root: Path, held: Held, idle: float, now: float) -> None:
    detail = f"a sub-agent waited on the model: its answer came {now - held.sent:.0f} s after the request"
    report.file(SIGNATURE, f"card {held.card} quiet {round(idle)} s: {detail}", now)
    row = {"at": now, "card": held.card, "since": held.since, "idle": round(idle), "signature": SIGNATURE}
    report.log(root, {**row, "detail": detail})
    report.log(root, {"at": now, "card": held.card, "since": held.since, "ended": held.since + idle})


def review(
    root: Path, held: dict[str, Held], since: dict[str, float], now: float, limit: float
) -> dict[str, Held]:
    """Judge each answered hold (file its quiet when over `limit`), drop the ended ones, keep the rest.

    `since` is each running card's last activity: past a hold's `since`, the card's work came back there.
    """
    keep: dict[str, Held] = {}
    for name, h in held.items():
        if (idle := quiet(h)) is not None:
            if idle > limit:
                _file(root, h, idle, now)
            continue
        last = since.get(h.card)
        if last is None or now - h.sent > HOLD:
            continue  # the turn is over, or the request hangs: the watch files the quiet itself
        keep[name] = h if h.back is not None or last <= h.since else replace(h, back=last)
    return keep


def holds(held: dict[str, Held], run: Running, now: float) -> bool:
    """Say whether a quiet card is held: already, or now because a sub-agent's request is out."""
    if key(run.card, run.since) in held:
        return True
    if (found := asking(run.run_dir, now)) is None:
        return False
    held[key(run.card, run.since)] = Held(run.card, run.since, *found)
    return True
