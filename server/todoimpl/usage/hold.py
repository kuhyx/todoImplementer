"""The weekly emergency reserve (T2533, kuhy 2026-11-27): 5 % of `seven_day` is never spent by the board.

At 90 % medium and low cards start no new plan turn (high ones go on); at 95 % every plan turn stops at once
and pauses until the window resets, then resumes its own session. The hold has its own mark,
`<root>/usage-hold.json`, because the limit probe clears `limit-until` whenever the window is below 100 %.
Two sources feed it: the limit probe (`apply_probe`) and every plan turn's `rate_limit_event` (`guard.py`).
A reading under 90 % clears it; so does the window's reset instant passing.

The daily allowance (kuhy 2026-11-28; the board burned 91 % of a week in 12 h): on day N of the window
(`resets_at - 7 d` is day 0) at most N/7 of `seven_day` may be used, whoever spent it. Above it no card
starts a plan turn (high ones too) and a running chain stops at its next turn (`chain._hold`) until the next
day starts. The mark keeps every reading, and the allowance is worked out when it is read.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "usage-hold.json"
ALL, ALLOWANCE, LOW_MEDIUM, NONE = "all", "allowance", "low_medium", "none"
STOP_AT, HOLD_AT = 0.95, 0.90
DAY = 86400.0
DAYS = 7
HIGH = "high"


def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def level_of(used: float) -> str:  # noqa: D103
    return ALL if used >= STOP_AT else LOW_MEDIUM if used >= HOLD_AT else NONE


def _day(resets_at: float, now: float) -> int:
    """Return which day of its 7-day window `now` is in (1..7)."""
    return min(DAYS, max(1, math.ceil((now - (resets_at - DAYS * DAY)) / DAY)))


def allowance_at(resets_at: float, now: float) -> float:
    """Return the share of `seven_day` that may be used by `now`: day N of 7 allows N/7."""
    return _day(resets_at, now) / DAYS


def observe(root: Path, used: float, resets_at: float, now: float) -> str:
    """Record a `seven_day` reading (fraction, reset epoch); return the level it puts the board at."""
    found = level_of(used)
    row = {"level": found, "until": resets_at, "used": used, "at": now}
    if _read(root) != row:
        atomic.write_text(root / FILE, json.dumps(row))
    return found if found == ALL else level(root, now)


def _num(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def level(root: Path, now: float) -> str:
    """Return the hold now: `all`, `allowance`, `low_medium` or `none` (no mark, or its window has reset)."""
    data = _read(root)
    reset, spent = _num(data, "until"), _num(data, "used")
    if reset is None or reset <= now:
        return NONE
    if data.get("level") == ALL:
        return ALL
    if spent is not None and spent > allowance_at(reset, now):
        return ALLOWANCE
    return LOW_MEDIUM if data.get("level") == LOW_MEDIUM else NONE


def allowance(root: Path, now: float) -> float | None:
    """Return the allowed share now, None while no reading of the current window is known."""
    reset = _num(_read(root), "until")
    return allowance_at(reset, now) if reset is not None and reset > now else None


def until(root: Path, now: float | None = None) -> float | None:
    """Return when the hold lifts: the next day for `allowance` (given `now`), else the window's reset."""
    reset = _num(_read(root), "until")
    if reset is not None and now is not None and level(root, now) == ALLOWANCE:
        return reset - (DAYS - _day(reset, now)) * DAY
    return reset


def used(root: Path, now: float) -> float | None:
    """Return the last weekly reading the hold saw while it holds, else None."""
    return _num(_read(root), "used") if level(root, now) != NONE else None


def held(root: Path, now: float, priority: str) -> bool:
    """Say whether a card of `priority` may start no plan turn now."""
    found = level(root, now)
    return found in {ALL, ALLOWANCE} or (found == LOW_MEDIUM and priority != HIGH)


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
