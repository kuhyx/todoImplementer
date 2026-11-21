"""kuhy's night (kuhy, 2026-11-21): 22:55-05:55 local time he sleeps (DOCS-phone.md "Night").

In that window the phone is locked out of the board (page and relay), pings wait for the morning and sessions
work without asking. `TODOIMPL_NIGHT` overrides the window as `HH:MM-HH:MM`; `off` (the tests' default) or
anything malformed means there is no night.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

WINDOW: Final = "22:55-05:55"
SHAPE: Final = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")


def window(env: Mapping[str, str]) -> tuple[time, time] | None:
    """Return the (start, end) of the night, or None when it is off or malformed."""
    match = SHAPE.match(env.get("TODOIMPL_NIGHT", WINDOW))
    if match is None:
        return None
    sh, sm, eh, em = (int(g) for g in match.groups())
    return time(sh, sm), time(eh, em)


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now().astimezone()


def is_night(now: datetime | None = None, env: Mapping[str, str] = os.environ) -> bool:
    """Tell whether `now` (local time, default the clock) falls in the night window."""
    span = window(env)
    if span is None:
        return False
    start, end = span
    clock = _now(now).time()
    if start <= end:
        return start <= clock < end
    return clock >= start or clock < end  # the window wraps midnight


def to_morning(now: datetime | None = None, env: Mapping[str, str] = os.environ) -> float:
    """Return the seconds until the night ends; 0 by day."""
    moment = _now(now)
    span = window(env)
    if span is None or not is_night(moment, env):
        return 0.0
    end = datetime.combine(moment.date(), span[1], moment.tzinfo)
    if end <= moment:
        end += timedelta(days=1)
    return (end - moment).total_seconds()
