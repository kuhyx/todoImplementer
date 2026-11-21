"""Write a stall to the board's app-error report (a ticket by the errors loop) and the stall log (T2402).

The report is `<error state>/app-errors/todoimplementer.json`, a contract `report` (app-error.schema.json):
one record per cause (`stall-memory`, `stall-buildlock`, `stall-job-<tool>`, `stall-model`), its count the
number of stall episodes. The errors loop turns each record into one part of the todoImplementer card and
starts it first, with no usage gate (`is_stall`). Every episode is also a line of `<run root>/stalls.jsonl`
(and its end another), and `<run root>/stalls.json` holds the open episodes: a restart never counts one twice.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.errors.sources import state_base
from todoimpl.runner.files import read_json, write_json
from todoimpl.stall.slowstep import PREFIX as SLOW_PREFIX

if TYPE_CHECKING:
    from pathlib import Path

APP = "todoimplementer"
REPO = "kuhyx/todoImplementer"
KIND = "perf.stall"
LOG = "stalls.jsonl"
OPEN = "stalls.json"
MESSAGE = "a running card had no activity for over 60 s ({cause})"


def path() -> Path:
    """Return the board's app-error report path: every `*.json` there is a source of the errors loop."""
    return state_base() / "app-errors" / f"{APP}.json"


def is_stall(key: str) -> bool:
    """Say whether an errors-loop key (`<app>:<signature>`) is a stall: it starts first and ungated.

    Matches:
    - `todoimplementer:stall-...` (board's own stalls, cause from stall/cause.py)
    - `<any app>:slow-...` (routed slow-step stalls from any repo, prefix from slowstep.py)
    """
    _app, colon, sig = key.partition(":")
    return key.startswith(f"{APP}:stall-") or (bool(colon) and sig.startswith(SLOW_PREFIX))


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat(timespec="seconds")


def file(signature: str, detail: str, now: float) -> None:
    """Count one more episode of `signature` in the report (a new record for a new cause)."""
    data = read_json(path())
    errors: list[dict[str, Any]] = data.get("errors", []) if isinstance(data, dict) else []
    record = next((e for e in errors if isinstance(e, dict) and e.get("signature") == signature), None)
    if record is None:
        cause = signature.removeprefix("stall-")
        record = {"app": APP, "repo": REPO, "signature": signature, "kind": KIND, "count": 0,
                  "message": MESSAGE.format(cause=cause), "first_seen": _iso(now), "build": 0}  # fmt: skip
        errors.append(record)
    record.update(count=int(record.get("count", 0)) + 1, last_seen=_iso(now), detail=detail, open=True)
    path().parent.mkdir(parents=True, exist_ok=True)
    atomic.write_text(path(), json.dumps({"version": 1, "errors": errors}, indent=2) + "\n")


def log(root: Path, row: dict[str, Any]) -> None:
    """Append one line to the stall log."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / LOG).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def open_episodes(root: Path) -> dict[str, float]:
    """Return card -> the `since` of its episode already filed."""
    data = read_json(root / OPEN)
    if not isinstance(data, dict):
        return {}
    return {k: float(v) for k, v in data.items() if isinstance(v, int | float) and not isinstance(v, bool)}


def save_open(root: Path, episodes: dict[str, float]) -> None:
    """Remember the open episodes."""
    write_json(root / OPEN, episodes)
