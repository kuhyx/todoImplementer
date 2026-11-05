"""A fake ``/api/tokens`` server on a free loopback port, and canned payloads.

Tests register canned ``(status, body)`` answers per path and read back the
requests the server saw (path + query), so the client is exercised over a
real socket rather than a mock of ``http.client``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlsplit

Answer = tuple[int, Any]


@dataclass
class Fake:
    """Routes and the log of requests."""

    url: str
    routes: dict[str, Answer] = field(default_factory=dict)
    seen: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def last(self) -> tuple[str, dict[str, str]]:
        return self.seen[-1]


def handler(fake: Fake) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
            fake.seen.append((parts.path, query))
            status, body = fake.routes.get(parts.path, (404, {"error": "nope"}))
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args: object) -> None:
            return

    return Handler


# --- canned payloads, shaped like the live API's -----------------------------
FILTERS = {"since": 1760000000.0, "until": 1760600000.0, "cwd": "", "scope": "all"}
OVERVIEW = {
    "filters": FILTERS,
    "tiles": {"usd": 1234.5, "usd_per_day": 41.1, "calls": 9000, "usd_per_call": 0.13},
    "daily": [{"day": "2026-10-17", "usd": 50.0, "calls": 10, "sub_share": 0.5}],
    "weekly": [{"week": "2026-W42", "usd": 300.0, "calls": 70}],
}
SESSION_ROW = {
    "key": "abc",
    "cwd": "/home/kuhy/src/x",
    "title": "fix | it",
    "usd": 12.5,
    "usd_sub": 2.0,
    "calls": 40,
    "prompts": 3,
    "subagents": 1,
    "active_s": 3700,
    "final_tag": "DONE",
}
SESSIONS = {"filters": FILTERS, "sessions": [SESSION_ROW, {**SESSION_ROW, "key": "b"}]}
DETAIL = {
    "session": SESSION_ROW,
    "prompts": [
        {
            "idx": 0,
            "usd": 10.0,
            "text": "do\nthings",
            "subagents": [{"usd": 2.0, "agent_type": "Explore", "description": "d"}],
            "tools": [{"name": "Bash", "calls": 3, "usd": 1.0, "carry_usd": 0.5}],
        },
        {"idx": 1, "usd": 2.5, "tools": [{"name": "Bash", "calls": 1, "usd": 2.0}]},
    ],
}
CONTEXT = {
    "filters": FILTERS,
    "files": [
        {
            "path": "/home/kuhy/.claude/CLAUDE.md",
            "kind": "claude-md",
            "standing": "always",
            "bytes": 9000,
            "tokens": 2250,
            "usd_per_day": 1.3,
            "warning": "over 250 lines: cap",
        },
        {"path": "/r/a.md", "kind": "rule", "bytes": 10, "usd_per_day": 0.1},
    ],
    "calls_per_day": 2905.0,
    "price_per_mtok": 0.2,
}
LEVERS = {
    "rows": [
        {"date": "2026-10-04", "status": "applied", "lever": "x", "actual": 0.8},
        {"date": "2026-10-05", "status": "proposed", "lever": "y"},
    ]
}
CELL = {"k": 1, "rate": 0.1, "low": 0.0, "high": 0.4}
AB = {
    "filters": FILTERS,
    "arms": {"opus": {"n": 3, "redo": CELL, "usd": {"mean": 1.0}}},
    "banner": {"level": "info", "text": "collecting"},
    "unjoined": 0,
}
EFFICIENCY = {
    "filtered_by": "date range only",
    "captions": {"done": "per DONE"},
    "done": [{"week": "2026-W42", "usd_per_done": 3.0, "done_share": 0.4}],
}
CARRY = {
    "filters": FILTERS,
    "caption": "Carry cost = ...",
    "families": [{"family": "git", "carry_usd": 4.0, "nested": [1]}],
    "hooks": [{"name": "spec_gate", "carry_usd": 1.0}],
    "_tables": {"families": {"rows": 30, "matched": 30, "returned": 1}},
}
ITEMS = {
    "filters": FILTERS,
    "items": [
        {"item": "abcd1234-0", "repo": "alpha", "stage": "implement", "sessions": 1, "calls": 3, "usd": 6.0}
    ],
    "repos": [{"repo": "alpha", "sessions": 2, "calls": 4, "usd": 10.0}],
    "stages": [{"stage": "implement", "sessions": 1, "calls": 3, "usd": 6.0}],
    "total_usd": 10.0,
    "_tables": {"items": {"rows": 1, "matched": 1, "returned": 1}},
}
