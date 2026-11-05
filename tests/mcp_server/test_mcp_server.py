"""The tools end to end against the fake API, plus the schema budget."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer
from mcp_fixtures import (
    AB,
    CARRY,
    CONTEXT,
    DETAIL,
    EFFICIENCY,
    ITEMS,
    LEVERS,
    OVERVIEW,
    SESSIONS,
)
from todoimpl_mcp import client, server, smoke

if TYPE_CHECKING:
    import pytest
    from mcp_fixtures import Fake

P = "/api/tokens/panel/"
TOOLS = {
    "overview",
    "sessions",
    "session_detail",
    "carry_costs",
    "context_files",
    "optimization_prompt",
    "levers",
    "efficiency",
    "ab_status",
    "hooks",
    "anomalies",
    "items",
}
SCHEMA_BUDGET_CHARS = 6200  # ~1.5k tokens for all twelve tools


def test_tool_list_and_schema_budget() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == TOOLS
    size = len(json.dumps([t.model_dump(exclude_none=True) for t in tools]))
    assert size < SCHEMA_BUDGET_CHARS
    assert all(t.output_schema is None for t in tools)


def test_overview_window_and_json(fake: Fake) -> None:
    fake.routes[P + "overview"] = (200, OVERVIEW)
    assert "$1,234 total" in server.overview("2026-10-01..2026-10-07")
    assert fake.last()[1] == {"from": "2026-10-01", "to": "2026-10-07"}
    assert json.loads(server.overview(as_json=True)) == OVERVIEW


def test_sessions_sends_table_grammar(fake: Fake) -> None:
    fake.routes[P + "sessions"] = (200, {**SESSIONS, "_tables": {}})
    out = server.sessions("fix", "cwd=/x&final_tag==DONE", "-calls", 5)
    assert "| abc |" in out
    assert fake.last()[1] == {
        "cwd": "/x",
        "t.sessions.f.final_tag": "=DONE",
        "t.sessions.q": "fix",
        "t.sessions.sort": "-calls",
        "t.sessions.limit": "5",
    }


def test_sessions_local_fallback(fake: Fake) -> None:
    fake.routes[P + "sessions"] = (200, SESSIONS)
    out = server.sessions(limit=1)
    assert "(1 rows)" in out


def test_session_detail(fake: Fake) -> None:
    fake.routes["/api/tokens/session/abc"] = (200, DETAIL)
    assert "**fix / it**" in server.session_detail("abc")
    assert "HTTP 404: nope" in server.session_detail("zzz")


def test_down_message(down: None) -> None:
    assert server.overview().startswith(client.DOWN)


def test_carry_costs(fake: Fake) -> None:
    assert server.carry_costs() == "carry panel not built yet (TODO group D)"
    fake.routes[P + "carry"] = (200, CARRY)
    assert "| git | $4.00 |" in server.carry_costs("families", "7d", 3)
    assert fake.last()[1]["t.families.limit"] == "3"


def test_context_and_prompt(fake: Fake) -> None:
    fake.routes[P + "context"] = (200, CONTEXT)
    assert "(1;" in server.context_files(over_limit_only=True)
    assert server.optimization_prompt().startswith("Shrink these 1 Claude")
    assert "| /r/a.md | 10 |" in server.optimization_prompt(["a.md"])


def test_levers_efficiency_ab(fake: Fake) -> None:
    fake.routes[P + "levers"] = (200, LEVERS)
    fake.routes[P + "efficiency"] = (200, EFFICIENCY)
    fake.routes[P + "ab"] = (200, AB)
    assert "(1 rows)" in server.levers("proposed")
    assert "per DONE" in server.efficiency("7d")
    assert "collecting" in server.ab_status()


def test_hooks_prefers_own_panel(fake: Fake) -> None:
    fake.routes[P + "hooks"] = (200, {"fires": [{"hook": "h", "count": 3}]})
    assert "**fires**" in server.hooks()


def test_hooks_falls_back_to_carry(fake: Fake) -> None:
    assert server.hooks() == "hooks panel not built yet (TODO groups D/F)"
    fake.routes[P + "carry"] = (200, CARRY)
    assert "| spec_gate | $1.00 |" in server.hooks()


def test_hooks_reports_other_errors(fake: Fake) -> None:
    fake.routes[P + "hooks"] = (503, {"error": "no token store"})
    assert server.hooks() == "HTTP 503: no token store"


def test_anomalies(fake: Fake) -> None:
    assert server.anomalies() == "anomalies panel not built yet (TODO group N)"
    fake.routes[P + "anomalies"] = (200, {"spikes": [{"day": "d", "usd": 9.0}]})
    assert "| d | $9.00 |" in server.anomalies("7d")


def test_items_asks_for_the_window_and_row_limit(fake: Fake) -> None:
    fake.routes["/api/tokens/items"] = (200, ITEMS)
    out = server.items("7d", 5)
    assert "**todoImplementer cost" in out
    assert "$10.00 total" in out
    assert "| abcd1234-0 | alpha | implement |" in out
    assert fake.last()[0] == "/api/tokens/items"
    assert fake.last()[1]["t.items.limit"] == "5"
    assert json.loads(server.items(as_json=True)) == ITEMS


def test_items_reports_an_unavailable_run_side(fake: Fake) -> None:
    fake.routes["/api/tokens/items"] = (503, {"error": "session_items is not available"})
    assert server.items() == "HTTP 503: session_items is not available"


def test_module_main_guard_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(MCPServer, "run", lambda *_a, **_k: calls.append(True))
    monkeypatch.delitem(sys.modules, "todoimpl_mcp.server")
    runpy.run_module("todoimpl_mcp.server", run_name="__main__")
    assert calls == [True]


def test_smoke_module_main_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    monkeypatch.setattr(asyncio, "run", seen.append)
    monkeypatch.delitem(sys.modules, "todoimpl_mcp.smoke")
    runpy.run_module("todoimpl_mcp.smoke", run_name="__main__")
    assert len(seen) == 1
    seen[0].close()  # type: ignore[attr-defined]


def test_main_runs_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(server.mcp, "run", lambda: calls.append(True))
    server.main()
    assert calls == [True]


def test_smoke_over_real_stdio(
    fake: Fake, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server as Claude Code runs it: a subprocess speaking JSON-RPC."""
    monkeypatch.setenv("PYTHONPATH", str(Path(server.__file__).parents[1]))
    fake.routes[P + "overview"] = (200, OVERVIEW)
    asyncio.run(smoke.run([("overview", {"window": "7d"})]))
    out = capsys.readouterr().out
    assert "ALL" in out
    assert "$1,234 total" in out


def test_smoke_main(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    monkeypatch.setattr(smoke, "run", lambda calls: calls)
    monkeypatch.setattr(asyncio, "run", seen.append)
    smoke.main()
    assert seen == [smoke.CALLS]
