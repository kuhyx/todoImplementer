"""The free-model issue log: one JSON line per problem, in `<umbrella run dir>/free-issues.jsonl`.

The manager appends its own lines (prompts/umbrella.py); the server appends what it sees itself (gateway probe
failures). Cheap tiers of single notes reuse the same file format.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

FILE = "free-issues.jsonl"
SYMPTOM_MAX = 500


def path(run_dir: Path) -> Path:
    """Return the issue log of a run dir."""
    return run_dir / FILE


def append(  # noqa: PLR0913, PLR0917 - the fields of one log line
    run_dir: Path, ts: float, child: str, phase: str, symptom: str, action: str = "", *, fixed: bool = False,
    model: str | None = None,
) -> None:  # fmt: skip
    """Append one issue line the way the manager is told to write it."""
    line = {
        "ts": ts, "child": child, "phase": phase, "model": model,
        "symptom": symptom[:SYMPTOM_MAX], "action": action, "fixed": fixed,
    }  # fmt: skip
    atomic.append_line(path(run_dir), json.dumps(line))


def read_lines(run_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    """Return (raw line, parsed row) pairs; a line that is not a JSON object is skipped (hand-written)."""
    try:
        text = path(run_dir).read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        try:
            found = json.loads(line)
        except ValueError:
            continue
        if isinstance(found, dict):
            rows.append((line, found))
    return rows


def read(run_dir: Path) -> list[dict[str, Any]]:
    """Return the logged issues; a line that is not a JSON object is skipped (the manager writes by hand)."""
    return [row for _, row in read_lines(run_dir)]


def raw(run_dir: Path) -> str:
    """Return the log file as it is (empty when there is none)."""
    try:
        return path(run_dir).read_text(encoding="utf-8")
    except OSError:
        return ""


def counts(run_dir: Path) -> dict[str, int]:
    """Return the number of issues per child repo (`kuhyx/<repo>`)."""
    out: dict[str, int] = {}
    for row in read(run_dir):
        child = str(row.get("child", ""))
        out[child] = out.get(child, 0) + 1
    return out


def unlogged(run_dir: Path, repos: Iterable[str], since: float) -> list[str]:
    """Return the repos among `repos` with no issue line at or after `since` (a `fixed` child needs one)."""
    seen = {str(row.get("child", "")) for row in read(run_dir) if float(row.get("ts") or 0) >= since}
    return [repo for repo in repos if repo not in seen]


def coaching(run_dir: Path, repo: str, since: float) -> int:
    """Return the coaching lines (phase `prompt`) logged for `repo` at or after `since`."""
    return sum(
        1
        for row in read(run_dir)
        if row.get("child") == repo and row.get("phase") == "prompt" and float(row.get("ts") or 0) >= since
    )
