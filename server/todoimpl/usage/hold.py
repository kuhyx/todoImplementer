"""The weekly emergency reserve (T2533, kuhy 2026-11-27): 5 % of `seven_day` is never spent by the board.

At 90 % medium and low cards start no new plan turn (high ones go on); at 95 % every plan turn stops at once
and pauses until the window resets, then resumes its own session. The hold has its own mark,
`<root>/usage-hold.json`, because the limit probe clears `limit-until` whenever the window is below 100 %.
Two sources feed it: the limit probe (`apply_probe`) and every plan turn's `rate_limit_event` (`guard.py`).
A reading under 90 % clears it; so does the window's reset instant passing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "usage-hold.json"
ALL, LOW_MEDIUM, NONE = "all", "low_medium", "none"
STOP_AT, HOLD_AT = 0.95, 0.90
HIGH = "high"


def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def level_of(used: float) -> str:  # noqa: D103
    return ALL if used >= STOP_AT else LOW_MEDIUM if used >= HOLD_AT else NONE


def observe(root: Path, used: float, resets_at: float, now: float) -> str:
    """Record a `seven_day` reading (fraction, reset epoch); return the level it puts the board at."""
    level = level_of(used)
    if level == NONE:
        (root / FILE).unlink(missing_ok=True)
        return NONE
    row = {"level": level, "until": resets_at, "used": used, "at": now}
    if _read(root) != row:
        atomic.write_text(root / FILE, json.dumps(row))
    return level


def level(root: Path, now: float) -> str:
    """Return the hold now: `all`, `low_medium` or `none` (no mark, or its window has reset)."""
    data = _read(root)
    until, found = data.get("until"), data.get("level")
    if not isinstance(until, int | float) or until <= now or found not in {ALL, LOW_MEDIUM}:
        return NONE
    return str(found)


def until(root: Path) -> float | None:  # noqa: D103
    value = _read(root).get("until")
    return float(value) if isinstance(value, int | float) else None


def used(root: Path, now: float) -> float | None:
    """Return the last weekly reading the hold saw while it holds, else None."""
    value = _read(root).get("used")
    return float(value) if level(root, now) != NONE and isinstance(value, int | float) else None


def held(root: Path, now: float, priority: str) -> bool:
    """Say whether a card of `priority` may start no plan turn now."""
    found = level(root, now)
    return found == ALL or (found == LOW_MEDIUM and priority != HIGH)


def from_event(obj: dict[str, Any]) -> tuple[float, float] | None:
    """Return (utilization, resetsAt) of a rate_limit_event's `seven_day` window, None when it has none."""
    info = obj.get("rate_limit_info")
    windows = info.get("unifiedWindows") if isinstance(info, dict) else None
    week = windows.get("seven_day") if isinstance(windows, dict) else None
    if not isinstance(week, dict):
        return None
    share, resets = week.get("utilization"), week.get("resetsAt")
    ok = all(isinstance(v, int | float) and not isinstance(v, bool) for v in (share, resets))
    return (float(share), float(resets)) if ok else None  # type: ignore[arg-type]


def apply_probe(root: Path, share: float, resets_at: float, now: float) -> str:
    """Record a probe reading; at 95 % stop every running plan turn (they pause until the reset)."""
    found = observe(root, share, resets_at, now)
    if found == ALL:
        from todoimpl.runner import guard  # noqa: PLC0415 - the runner imports usage, not the other way

        guard.stop_all(root, resets_at)
    return found
