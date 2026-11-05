"""GET /api/usage: per-task cost, plan windows and limit state (contracts/usage.schema.json)."""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from todoimpl.usage.cost import session_costs
from todoimpl.usage.events import iter_events, stream_files
from todoimpl.usage.limits import limit_state

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

WINDOWS = ("five_hour", "seven_day")


def _window(raw: object) -> dict[str, Any] | None:
    """Contract window from a unifiedWindows entry (or top-level info); None when incomplete."""
    if not isinstance(raw, dict):
        return None
    used, resets, status = raw.get("utilization"), raw.get("resetsAt"), raw.get("status")
    if not (isinstance(used, int | float) and isinstance(resets, int | float) and isinstance(status, str)):
        return None
    return {"utilization": float(used), "resets_at": float(resets), "status": status}


def _fold_rate_limits(streams: list[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Latest known value per window and for overage, oldest stream (by mtime) first.

    Events omit parts of the picture, so each window keeps its own latest valid value.
    """
    windows: dict[str, Any] = dict.fromkeys(WINDOWS)
    overage: dict[str, Any] = {"status": "unknown", "using": False}
    for stream in sorted(streams, key=lambda p: (p.stat().st_mtime, p.name)):
        for event in iter_events(stream):
            info = event.get("rate_limit_info")
            if event.get("type") != "rate_limit_event" or not isinstance(info, dict):
                continue
            unified = info.get("unifiedWindows")
            for key in WINDOWS:
                raw = unified.get(key) if isinstance(unified, dict) else None
                if raw is None and info.get("rateLimitType") == key:
                    raw = info
                windows[key] = _window(raw) or windows[key]
            if isinstance(info.get("overageStatus"), str):
                overage["status"] = info["overageStatus"]
            if isinstance(info.get("isUsingOverage"), bool):
                overage["using"] = info["isUsingOverage"]
    return windows, overage


def usage_summary(
    root: Path, now: float | None = None, titles: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Everything the usage strip needs.

    Result events carry no timestamp, so a session's cost counts as "today" when
    its newest stream file was last written today (local time). `titles` maps item id to the note
    title (the run dir does not store it); unknown ids show the id.
    """
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).astimezone().date()
    per_task: list[dict[str, Any]] = []
    all_streams: list[Path] = []
    today_usd = 0.0
    for run_dir in sorted(root.glob("*/")):
        streams = stream_files(run_dir)
        if not streams:
            continue
        all_streams += streams
        costs = session_costs(streams)
        today_usd += sum(c for c, m in costs if datetime.fromtimestamp(m).astimezone().date() == today)
        per_task.append(
            {
                "id": run_dir.name,
                "title": (titles or {}).get(run_dir.name, run_dir.name),
                "cost_usd": sum(c for c, _ in costs),
            }
        )
    per_task.sort(key=lambda t: (-t["cost_usd"], t["id"]))
    windows, overage = _fold_rate_limits(all_streams)
    limit = limit_state(root)
    active = limit.active(now)
    return {
        "generated_at": now,
        **windows,
        "overage": overage,
        "limit": {
            "active": active,
            "until": limit.until if active else None,
            "credits_available": limit.credits,
        },
        "cost": {
            "today_usd": today_usd,
            "total_usd": sum(t["cost_usd"] for t in per_task),
            "per_task": per_task,
        },
    }
