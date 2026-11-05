"""A store with a little of everything, so every panel returns non-empty tables.

Builds on :func:`tokfix_tokens.build` and the per-group row builders; the rows are
synthetic (no prompt, path or company text) and exist only to exercise response shapes.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import tokfix_detail as fd
import tokfix_estimator as fe
import tokfix_prefix as fp
import tokfix_prompt_cost as fpc
import tokfix_subagents as fs
import tokfix_token_classes as ft
import tokfix_tokens as fx

if TYPE_CHECKING:
    from pathlib import Path

HOOK = "time_cap.sh"


def _calls() -> list[tuple[object, ...]]:
    errors = ["exit_code", "time_cap", "rejected", "denied", "hook"]
    rows = [
        fd.call(sig=f"e{i}", is_error=1, error_kind=k, result_tokens=900 * (i + 1))
        for i, k in enumerate(errors)
    ]
    rows += [
        fd.call(name="mcp__todo__list", family="mcp:todo", target="list", sig="m", images=0),
        fd.call(name="Skill", family="Skill:x", target="x", sig="k"),
        fd.call(name="WebFetch", family="web", target="https://example.test", sig="w"),
        fd.call(name="Read", family="Read:file", target="/r/a.md", sig="r", result_tokens=50),
        fd.call(name="Read", family="Read:file", target="/r/a.md", sig="r", result_tokens=50, ts=fx.T0 + 9),
        fd.call(name="Read", family="Read:image", target="/r/p.png", sig="i", images=1),
        fd.call(key="s1/agent-a", model="claude-sonnet-5-5", sig="a"),
    ]
    return rows


def _marks() -> list[tuple[object, ...]]:
    return [
        fd.mark(kind="hook_run", tokens=40, retry_usd=0.0, create_usd=0.01, carry_usd=0.02),
        fd.mark(kind="hook_context", name="SessionStart", detail="ctx.sh", tokens=300, carry_usd=0.3),
        fd.mark(kind="hook_block", name="Stop", detail="gate.sh", retry_usd=0.4),
        fd.mark(kind="hook_error", detail=HOOK),
        fd.mark(kind="hook_msg", detail=HOOK),
        fd.mark(kind="api_error", name="overloaded", detail="529", count=2),
        fd.mark(kind="api_error", name="rate_limit", detail="429"),
        fd.mark(kind="interrupt", name="user", detail=""),
        fd.mark(kind="compaction", name="auto", count=1, tokens=150_000, extra=9000, duration_ms=30_000),
    ]


def rich(path: Path) -> Path:
    """Add rows for every panel to a fresh :func:`tokfix_tokens.build` store; return its path."""
    fx.build(path)
    fd.insert(path, calls=_calls(), marks=_marks(), turns=[fd.turn_detail(), fd.turn_detail(ts=fx.T0 + 3600)])
    ft.add(
        path,
        turns=[
            ft.turn(ts=fx.T0, cache_write=5000, input=10, output=20, usd=0.5),
            ft.turn(ts=fx.T0 + 10, cache_read=9000, input=10, output=20, usd=0.1),
            ft.turn(ts=fx.T0 + 20_000, cache_write=800, cache_read=0, usd=0.2),
        ],
        prompts=[("s1", 0, fx.T0, "p0", "synthetic prompt"), ("s1", 1, fx.T0 + 3600, "p1", "another one")],
    )
    fs.insert(
        path,
        links=[
            fs.link("s2/agent-b", usd=2.0),
            fs.link("s1/agent-c", model="claude-sonnet-5-5", description="Find y"),
        ],
        agent_calls=[fs.agent_call("s1", "a", fx.T0 + 60), fs.agent_call("s2", "b", fx.T0 + fx.DAY)],
    )
    fe.estimates(path, [("s1", 5), ("s2", 1)])
    fe.events(
        path,
        [
            ("task-size-miss", fx.T0, "split-ignored", "synthetic"),
            ("task-size-miss", fx.T0 + 1, "predicted-fits", ""),
        ],
    )
    fpc.prompts(path, [("s1", 2, fx.T0 + 5, "third prompt", 0.5, 0.1)])
    fp.sizes(path, [("/x/CLAUDE.md", fx.T0, 100, "git"), ("/x/CLAUDE.md", fx.T0 + 60, 120, "git")])
    fp.snapshot(path, "2026-09-25", fx.T0, 1234)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("INSERT INTO session_commits VALUES ('abc1', 'r', ?, 's1', 0)", (fx.T0,))
        conn.execute("INSERT INTO commit_verdicts VALUES ('abc1', 'r', ?, 10, 8, 'survived')", (fx.T0,))
        conn.commit()
    return path
