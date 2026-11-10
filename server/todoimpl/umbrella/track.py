"""The tracking view of an umbrella run (contracts/track.schema.json, DOCS-tracking.md).

Pure functions over what is on disk: the umbrella's state, the child rows `view.rows` computes, the issue and
worker logs. The page shows the result as it is; nothing here is decided by the browser.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.board.umbrella import counts

from . import issues, workers
from .store import RECORD, child_dir
from .view import child_state

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

AT_REST = ("gate", "shipped", "failed", "cancelled")  # a child here has stopped its clock
LOG_RE = re.compile(r"worker-(\d+)\.log")
GROUP_LINES = 20
LOG_TAIL = 64 * 1024
STEPS = (("verdicts", "manager"), ("checks", "checks"))


def resting(st: RunState | None) -> dict[str, Any] | None:
    """Return why a run waits by itself (plan limit or a retry timer), None when it does not."""
    if st is None or st.stage not in ("paused_limit", "paused_retry"):
        return None
    kind = "limit" if st.stage == "paused_limit" else str(st.extra.get("retry_kind", "turn"))
    return {"kind": kind, "until": st.resume_at}


def latest_log(run_dir: Path, cid: str) -> Path | None:
    """Return the newest `worker-<round>.log` of a child, None when none was written."""
    found = [
        (int(m.group(1)), p)
        for p in child_dir(run_dir, cid).glob("worker-*.log")
        if (m := LOG_RE.fullmatch(p.name))
    ]
    return max(found, key=lambda pair: pair[0])[1] if found else None


def log_tail(run_dir: Path, cid: str) -> str | None:
    """Return the end of the child's newest worker log, None when there is none."""
    path = latest_log(run_dir, cid)
    if path is None:
        return None
    with path.open("rb") as handle:
        handle.seek(0, 2)
        handle.seek(max(0, handle.tell() - LOG_TAIL))
        return handle.read().decode("utf-8", errors="replace")


def _text(value: object) -> str:
    """Return a hand-written issue field as text, empty when it is not a string."""
    return value if isinstance(value, str) else ""


def _model(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _epoch(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _elapsed(child: RunState | None, now: float) -> float | None:
    if child is None or child.started_at is None:
        return None
    end = child.updated if child.stage in AT_REST else now
    return max(0.0, end - child.started_at)


def _kid(row: dict[str, Any], run_dir: Path, now: float, seen: dict[str, Any]) -> dict[str, Any]:
    child = child_state(run_dir, row["id"])
    repo = row["repo"]
    runs = [w for w in seen["workers"] if w.get("child") == repo]
    last = next((r for r in reversed(seen["issues"]) if r.get("child") == repo), None)
    return {
        **{k: row[k] for k in ("id", "repo", "title", "status", "stage", "round", "verdict", "free")},
        "elapsed": _elapsed(child, now), "issues": row["issues"],
        "last_issue": None if last is None else {
            "phase": _text(last.get("phase")), "model": _model(last.get("model")),
            "symptom": _text(last.get("symptom")), "ts": _epoch(last.get("ts")),
        },
        "resting": resting(child), "log": latest_log(run_dir, row["id"]) is not None,
        "attempts": len(runs), "killed": sum(bool(w.get("killed")) for w in runs), "error": row["error"],
    }  # fmt: skip


def issue_groups(run_dir: Path) -> dict[str, Any]:
    """Group the issue log by phase and model: counts, how many were fixed, the newest raw lines."""
    groups: dict[tuple[str, str | None], dict[str, Any]] = {}
    for raw, row in issues.read_lines(run_dir):
        key = (_text(row.get("phase")), _model(row.get("model")))
        group = groups.setdefault(
            key, {"phase": key[0], "model": key[1], "count": 0, "fixed": 0, "lines": []}
        )
        group["count"] += 1
        group["fixed"] += bool(row.get("fixed"))
        group["lines"] = [*group["lines"], raw][-GROUP_LINES:]
    found = sorted(groups.values(), key=lambda g: (-g["count"], g["phase"], str(g["model"])))
    return {"total": sum(g["count"] for g in found), "groups": found}


def eta(kids: list[dict[str, Any]], width: int) -> dict[str, Any]:
    """Estimate the time left: ceil(children left / width) times the median time a finished child took."""
    took = [
        k["elapsed"] for k in kids if k["status"] in ("done", "ready_to_ship") and k["elapsed"] is not None
    ]
    left = sum(k["status"] not in ("done", "ready_to_ship") for k in kids)
    running = sum(k["status"] in ("working", "queued", "shipping") for k in kids)
    wide = max(1, width, running)
    median = statistics.median(took) if took else None
    seconds = None if median is None else math.ceil(left / wide) * median
    return {"seconds": seconds, "done": len(kids) - left, "left": left, "median": median, "width": wide}


def _round(rec: dict[str, Any]) -> dict[str, Any] | None:
    cur = rec.get("current")
    if not cur:
        return None
    step = next((name for key, name in STEPS if cur.get(key) is None), "verdict")
    return {
        "n": cur["n"],
        "width": cur["width"],
        "started": cur.get("started"),
        "step": step,
        "ids": cur["ids"],
    }


ROW_KEYS = ("id", "verdict", "detail", "free", "checks", "ok")  # the contract's keys: nothing else passes


def _child(row: dict[str, Any], repos: dict[str, str]) -> dict[str, Any]:
    """Return one round row with the repo name added and only the contract's keys."""
    return {**{k: row.get(k) for k in ROW_KEYS}, "repo": repos.get(row["id"], row["id"])}


def _rounds(rec: dict[str, Any]) -> list[dict[str, Any]]:
    repos = {k["id"]: k["repo"] for k in rec.get("kids", [])}
    return [
        {
            "n": r["n"], "width": r["width"], "next": r["next"],
            "started": r.get("started"), "ended": r.get("ended"),
            "children": [_child(c, repos) for c in r["children"]],
        }
        for r in rec.get("rounds", [])
    ]  # fmt: skip


@dataclass(frozen=True)
class Run:
    """Which umbrella a track is of: its card id, title, board status and run dir."""

    card: str
    title: str
    status: str
    run_dir: Path


def build(run: Run, st: RunState, rows: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """Return the track object of the umbrella run `st` whose child rows are `rows`."""
    run_dir, rec = run.run_dir, st.extra.get(RECORD, {})
    seen = {"workers": workers.read(run_dir), "issues": issues.read(run_dir)}
    kids = [_kid(row, run_dir, now, seen) for row in rows]
    summary = counts(rows, rec)
    return {
        "id": run.card, "title": run.title, "at": now, "status": run.status, "stage": st.stage,
        "resting": resting(st),
        "counts": summary, "needs": sum(r["status"] == "needs_you" for r in rows), "round": _round(rec),
        "rounds": _rounds(rec), "kids": kids, "issues": issue_groups(run_dir),
        "eta": eta(kids, int(rec.get("width", 1))),
    }  # fmt: skip
