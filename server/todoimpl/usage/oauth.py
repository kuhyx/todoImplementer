"""Read-only plan usage from the endpoint Claude Code's /usage reads: no turn is spent, no token is printed.

The OAuth token belongs to the `claude` login (`$CLAUDE_CONFIG_DIR` or `~/.claude`); it is only read, never
refreshed here (the CLI refreshes it whenever it runs). An expired or missing token means "unknown".
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from todoimpl import atomic

URL = "https://api.anthropic.com/api/oauth/usage"
TIMEOUT = 15.0
FILE = "usage-probe.json"
Getter = Callable[[str, dict[str, str], float], object]


@dataclass(frozen=True)
class Window:
    """One plan window: `utilization` is a fraction (1.0 = full), `resets_at` an epoch."""

    utilization: float
    resets_at: float


@dataclass(frozen=True)
class Probe:
    """What the plan reported at `at`; a window the plan does not report is None."""

    at: float
    five_hour: Window | None
    seven_day: Window | None

    def blocked_until(self, now: float) -> float | None:
        """Latest reset among windows that are full and have not reset yet; None when the plan is usable."""
        windows = (self.five_hour, self.seven_day)
        ends = [w.resets_at for w in windows if w is not None and w.utilization >= 1 and w.resets_at > now]
        return max(ends) if ends else None


def _window(raw: object) -> Window | None:
    if not isinstance(raw, dict):
        return None
    used, resets = raw.get("utilization"), raw.get("resets_at")
    if not isinstance(used, int | float) or not isinstance(resets, str):
        return None
    try:
        return Window(used / 100, datetime.fromisoformat(resets).timestamp())
    except ValueError:
        return None


def parse(body: object, now: float) -> Probe | None:
    """Build a Probe from the endpoint's JSON (percent, ISO resets_at); None if not an object."""
    if not isinstance(body, dict):
        return None
    return Probe(now, _window(body.get("five_hour")), _window(body.get("seven_day")))


def http_get(url: str, headers: dict[str, str], timeout: float) -> object:
    """GET url and decode the JSON body."""
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - fixed https URL
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310
        return json.loads(reply.read())


def _token(now: float) -> str | None:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    path = (Path(base) if base else Path.home() / ".claude") / ".credentials.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    login = data.get("claudeAiOauth") if isinstance(data, dict) else None
    if not isinstance(login, dict):
        return None
    token, expires = login.get("accessToken"), login.get("expiresAt")
    fresh = isinstance(expires, int | float) and expires / 1000 > now
    return token if isinstance(token, str) and fresh else None


def fetch(now: float, getter: Getter = http_get) -> Probe | None:
    """Ask the plan for its real usage; None (unknown) on a missing/expired token or any failure."""
    token = _token(now)
    if token is None:
        return None
    headers = {"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"}
    try:
        return parse(getter(URL, headers, TIMEOUT), now)
    except OSError, ValueError:
        return None


def _dump(window: Window | None) -> dict[str, float] | None:
    return None if window is None else {"utilization": window.utilization, "resets_at": window.resets_at}


def save(root: Path, probe: Probe) -> None:
    """Store the newest probe next to the other run-root marks (atomic)."""
    root.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "at": probe.at,
        "five_hour": _dump(probe.five_hour),
        "seven_day": _dump(probe.seven_day),
    }
    atomic.write_text(root / FILE, json.dumps(data) + "\n")


def _stored(raw: object) -> Window | None:
    if not isinstance(raw, dict):
        return None
    used, resets = raw.get("utilization"), raw.get("resets_at")
    if not (isinstance(used, int | float) and isinstance(resets, int | float)):
        return None
    return Window(float(used), float(resets))


def load(root: Path) -> Probe | None:
    """Read the stored probe; unreadable or malformed counts as none."""
    try:
        raw = json.loads((root / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    at = raw.get("at") if isinstance(raw, dict) else None
    if not isinstance(at, int | float):
        return None
    return Probe(float(at), _stored(raw.get("five_hour")), _stored(raw.get("seven_day")))
