"""Keeps the newest reading of the free-model gateway; no request ever waits on the gateway.

A daemon thread (like `runner/limitprobe.LimitProbe`) reads it every `INTERVAL` seconds, each call under a 2 s
timeout, and `view()` returns the last reading at once. A section that fails is left out and named in `error`;
when nothing could be read the last good reading stays, flagged `down`, then `stale` by age.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from todoimpl.umbrella import workers

from . import snapshot
from .client import Client, GatewayError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

log = logging.getLogger("todoimpl.gateway")
INTERVAL = 30.0
STALE_AFTER = 3  # intervals
REDISCOVER = 30  # refreshes between full quota scans (quota records exist for a few providers only)
LOG_LIMIT = 300
MARGIN = 2.0  # seconds a call may fall outside its worker's window (clocks, queueing)


def ours_tokens(calls: object, windows: list[tuple[float, float]]) -> int | None:
    """Sum the tokens of recent gateway calls made while one of our free workers ran; None without workers."""
    if not windows:
        return None
    total = 0
    for call in calls if isinstance(calls, list) else []:
        at = snapshot.parse_time(call.get("timestamp")) if isinstance(call, dict) else None
        tokens = call.get("tokens") if isinstance(call, dict) else None
        if at is None or not isinstance(tokens, dict):
            continue
        if any(start - MARGIN <= at <= end + MARGIN for start, end in windows):
            total += int(snapshot._num(tokens.get("in")) + snapshot._num(tokens.get("out")))  # noqa: SLF001
    return total


class GatewayMonitor:
    """`refresh()` reads once, `start()` repeats it, `view()` returns the last reading (never blocks)."""

    def __init__(
        self,
        root: Path,
        *,
        client: Client | None = None,
        clock: Callable[[], float] = time.time,
        interval: float = INTERVAL,
    ) -> None:
        """`root` is the run root: the worker logs of today's umbrellas live below it."""
        self.root, self._client, self._clock, self._interval = root, client or Client(), clock, interval
        self._lock = threading.Lock()
        self._body: dict[str, Any] | None = None
        self._at: float | None = None
        self._error: str | None = None
        self._failed = False  # the newest read got nothing at all
        self._quota_ids: set[str] | None = None
        self._ticks = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _windows(self, now: float) -> list[tuple[float, float]]:
        midnight = datetime.fromtimestamp(now, UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        out = []
        for path in self.root.glob("*/" + workers.FILE):
            for row in workers.read(path.parent):
                start, end = row.get("start"), row.get("end")
                if (
                    isinstance(start, int | float)
                    and isinstance(end, int | float)
                    and end >= midnight.timestamp()
                ):
                    out.append((float(start), float(end)))
        return out

    def _quotas(self, connections: object) -> dict[str, Any]:
        """Ask the quota endpoint of every connection now and then, of the known ones in between."""
        rows = connections.get("connections") if isinstance(connections, dict) else None
        ids = [str(c["id"]) for c in rows or [] if isinstance(c, dict) and "id" in c]
        scan = self._quota_ids is None or self._ticks % REDISCOVER == 0
        found: dict[str, Any] = {}
        for conn_id in ids if scan else [i for i in ids if i in (self._quota_ids or ())]:
            try:
                answer = self._client.admin(f"/api/usage/{conn_id}")
            except GatewayError:
                continue  # HTTP 400: this provider reports no quota
            if isinstance(answer, dict) and isinstance(answer.get("quotas"), dict):
                found[conn_id] = answer
        self._quota_ids = set(found)
        return found

    def refresh(self) -> None:
        """Read the gateway once and store the result."""
        now = self._clock()
        raw: dict[str, Any] = {}
        errors: list[str] = []
        client = self._client
        sections: dict[str, Callable[[], Any]] = {
            "health": lambda: client.bearer("/api/v1/models/health"),
            "providers": lambda: client.admin("/api/providers"),
            "combos": lambda: client.admin("/api/combos"),
            "metrics": lambda: client.admin("/api/combos/metrics"),
            "analytics": lambda: client.admin("/api/usage/analytics?period=day"),
            "calls": lambda: client.admin(f"/api/usage/call-logs?limit={LOG_LIMIT}"),
        }
        for name, call in sections.items():
            try:
                raw[name] = call()
            except GatewayError as exc:
                errors.append(f"{name}: {exc}")
        if "providers" in raw:
            raw["quotas"] = self._quotas(raw["providers"])
        self._ticks += 1
        with self._lock:
            self._failed = len(errors) == len(sections)
            if self._failed:
                self._error = errors[0]
                return
            self._body = snapshot.build(raw, now, ours_tokens(raw.get("calls"), self._windows(now)))
            self._at, self._error = now, errors[0] if errors else None

    def view(self) -> dict[str, Any]:
        """Return the last reading with its state: ok, stale (old), down (the last read failed), unknown."""
        now = self._clock()
        with self._lock:
            body, at, error, failed = self._body, self._at, self._error, self._failed
        if body is None or at is None:
            return {
                **snapshot.build({}, now),
                "at": None,
                "state": "down" if failed else "unknown",
                "error": error,
            }
        old = now - at > STALE_AFTER * self._interval
        state = "down" if failed else "stale" if old else "ok"
        return {**body, "at": at, "state": state, "error": error}

    def _safe_refresh(self) -> None:
        try:
            self.refresh()
        except Exception:
            log.exception("gateway refresh crashed")

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._safe_refresh()
            self._stop.wait(self._interval)

    def start(self) -> None:
        """Run the loop in a daemon thread (idempotent); the first read happens off the startup path."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="gateway-monitor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the loop and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)
