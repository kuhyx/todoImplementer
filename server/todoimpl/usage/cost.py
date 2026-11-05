"""Dollar cost of a run, summed over its sessions.

A result event's `total_cost_usd` is cumulative for its session: a resumed turn reports the earlier
turns again (T401). So each session counts once, at its highest reported total.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.usage.events import iter_events, stream_files

if TYPE_CHECKING:
    from pathlib import Path


def session_costs(streams: list[Path]) -> list[tuple[float, float]]:
    """Return (cost_usd, last_written_epoch) per session found in the given stream files.

    A session may span files (a resume opens a new stream), so results merge by `session_id`.
    A result event without one is its own session. The epoch is the newest file holding the session.
    """
    best: dict[str | tuple[str, int], tuple[float, float]] = {}
    for stream in streams:
        mtime = stream.stat().st_mtime
        for number, event in enumerate(iter_events(stream)):
            cost = event.get("total_cost_usd")
            if event.get("type") != "result" or not isinstance(cost, int | float):
                continue
            sid = event.get("session_id")
            key = sid if isinstance(sid, str) and sid else (str(stream), number)
            seen_cost, seen_mtime = best.get(key, (0.0, 0.0))
            best[key] = (max(float(cost), seen_cost), max(mtime, seen_mtime))
    return list(best.values())


def task_cost(run_dir: Path) -> float:
    """USD spent by every session recorded in `<run_dir>/*.stream.jsonl`."""
    return sum(cost for cost, _ in session_costs(stream_files(run_dir)))
