"""A sub-agent's own work, which claude keeps out of the turn's stream (T2561).

claude copies a sub-agent's tool calls and results to the turn's stream, but not its thinking, its advisor
call or its text: card a0783cdb-0 (2026-11-27) showed only `tool_progress` heartbeats for 140 s while its
`web-fetch` sub-agent thought, waited 71 s on the advisor and wrote its report. Each sub-agent's transcript,
`<PROJECTS>/<cwd as a dir name>/<session>/subagents/agent-*.jsonl`, gets those lines as they come, with their
`timestamp`; its newest message line counts like the stream's (an unanswered advisor call included). The
session and cwd come from the stream's `system init` line. `PROJECTS` is the tests' seam (conftest).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .output import newest

PROJECTS = Path.home() / ".claude" / "projects"
HEAD = 1 << 20  # bytes of the init line read: it lists every tool, 8 KB today
UNSAFE = re.compile(r"[^A-Za-z0-9]")  # Claude Code names a project's dir by its cwd, every other char a dash


def _session(stream: Path) -> tuple[str, str] | None:
    """Return the turn's cwd and session id from the stream's first line, None when it names neither."""
    try:
        with stream.open("rb") as fh:
            row = json.loads(fh.readline(HEAD))
    except OSError, ValueError:
        return None
    cwd, sid = (row.get("cwd"), row.get("session_id")) if isinstance(row, dict) else (None, None)
    return (cwd, sid) if isinstance(cwd, str) and isinstance(sid, str) and sid else None


def until(stream: Path, start: float) -> float | None:
    """Return the newest work of the sub-agents whose transcript changed since `start`, None when none."""
    if (found := _session(stream)) is None:
        return None
    cwd, sid = found
    times: list[float] = []
    for path in (PROJECTS / UNSAFE.sub("-", cwd) / sid / "subagents").glob("agent-*.jsonl"):
        try:
            if path.stat().st_mtime < start:  # an earlier turn's sub-agent: never read again
                continue
        except OSError:
            continue
        if (at := newest(path)) is not None:
            times.append(at)
    return max(times, default=None)
