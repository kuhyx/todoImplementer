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
HEAD = 1 << 20  # bytes read for the init line: it lists every tool, 8 KB today
UNSAFE = re.compile(r"[^A-Za-z0-9]")  # Claude Code names a project's dir by its cwd, every other char a dash


def _init(line: bytes) -> tuple[str, str] | None:
    """Return the cwd and session id of a `system init` line, None for any other line."""
    try:
        row = json.loads(line)
    except ValueError:  # the head cut it, or claude is mid-write
        return None
    if not isinstance(row, dict) or (row.get("type"), row.get("subtype")) != ("system", "init"):
        return None
    cwd, sid = row.get("cwd"), row.get("session_id")
    return (cwd, sid) if isinstance(cwd, str) and isinstance(sid, str) and sid else None


def _session(stream: Path) -> tuple[str, str] | None:
    """Return the turn's cwd and session id from the stream's `system init` line in its first `HEAD` bytes.

    Not always the first line: claude may write a `system dev_intent` line before it (17 of 293 streams).
    """
    try:
        with stream.open("rb") as fh:
            head = fh.read(HEAD)
    except OSError:
        return None
    return next((found for line in head.splitlines() if (found := _init(line)) is not None), None)


def transcripts(stream: Path, start: float) -> list[Path]:
    """Return the turn's sub-agent transcripts changed since `start` (an earlier turn's are never read)."""
    if (found := _session(stream)) is None:
        return []
    cwd, sid = found
    paths: list[Path] = []
    for path in (PROJECTS / UNSAFE.sub("-", cwd) / sid / "subagents").glob("agent-*.jsonl"):
        try:
            if path.stat().st_mtime >= start:
                paths.append(path)
        except OSError:
            continue
    return paths


def until(stream: Path, start: float) -> float | None:
    """Return the newest work of the sub-agents whose transcript changed since `start`, None when none."""
    times = [at for path in transcripts(stream, start) if (at := newest(path)) is not None]
    return max(times, default=None)
