"""Renderers: payload -> markdown."""

from __future__ import annotations

from mcp_fixtures import (
    AB,
    CARRY,
    CONTEXT,
    DETAIL,
    EFFICIENCY,
    FILTERS,
    ITEMS,
    LEVERS,
    OVERVIEW,
    SESSIONS,
)
from todoimpl_mcp import panels, views


def test_overview() -> None:
    out = views.overview(OVERVIEW)
    assert "$1,234 total" in out
    assert "| 2026-10-17 | $50.00 | 10 |" in out
    assert "2026-W42" in out
    assert "list-price" in out


def test_period_shows_non_default_filters() -> None:
    payload = {"filters": {**FILTERS, "cwd": "/x", "scope": "sub"}}
    assert "cwd=/x scope=sub" in views.overview(payload)


def test_sessions() -> None:
    out = views.sessions(SESSIONS)
    assert "(2 rows)" in out
    assert "| abc | $12.50 | $2.00 | 40 | 3 | 1 | 1h01m | DONE | ~/src/x | fix / it |" in out


def test_session_detail() -> None:
    out = views.session_detail(DETAIL)
    assert "**fix / it** `abc`" in out
    assert "| 0 | $10.00 | - | - | - | do things |" in out
    assert "| $2.00 | Explore | - | - | d |" in out
    assert "| Bash | 4 | $3.00 | $0.50 |" in out
    assert out.endswith("#/s/abc")


def test_session_link_escapes_slash() -> None:
    assert views.session_link("a/agent-b").endswith("/s/a%2Fagent-b")


def test_grouped() -> None:
    out = views.grouped(CARRY, "families", 5, "Carry cost")
    assert "(1 of 30 rows)" in out
    assert "| git | $4.00 |" in out
    missing = views.grouped(CARRY, "nope", 5, "Carry cost")
    assert missing == "no `nope` table in Carry cost; tables: families, hooks"
    assert "tables: none" in views.grouped({}, "x", 0, "T")
    assert "(1 rows)" in views.grouped(CARRY, "hooks", 0, "Hooks")


def test_all_tables() -> None:
    out = views.all_tables(CARRY, "Hooks")
    assert "Carry cost = ..." in out
    assert "**families**" in out
    assert "**hooks**" in out
    assert "**filters**" not in out


def test_context_files() -> None:
    out = panels.context_files(CONTEXT, over_limit_only=False)
    assert "**Context files** (2;" in out
    assert "| ~/.claude/CLAUDE.md | always | - | 2,250 | $1.30 | over hard limit |" in out
    only = panels.context_files(CONTEXT, over_limit_only=True)
    assert "(1;" in only
    assert "/r/a.md" not in only


def test_file_link() -> None:
    assert panels.file_link("/a/b").endswith("#/f/%2Fa%2Fb")


def test_levers_filter() -> None:
    assert "(2 rows)" in panels.levers(LEVERS, "")
    out = panels.levers(LEVERS, "Applied")
    assert "(1 rows)" in out
    assert "| 2026-10-04 | applied |" in out


def test_ab_status() -> None:
    out = panels.ab_status(AB)
    assert "info: collecting" in out
    assert "| opus | 3 | 10% [0%-40%] k=1 | - | - | - | $1.00 | - |" in out
    assert "_panels" not in out
    assert "-: " in panels.ab_status({})
    assert "build" not in panels.ab_status(AB).lower()


def test_ab_status_reports_build_experiment_separately() -> None:
    build = {
        "arms": {"sonnet": {"n": 4}},
        "banner": {"level": "grey", "text": "A/B build agents: collecting (n=0)"},
        "unjoined": 2,
    }
    out = panels.ab_status({**AB, "build": build})
    judgment, _, rest = out.partition("**A/B build subagents**")
    assert "**A/B judgment subagents** (closed experiment)" in judgment
    assert "| opus | 3 |" in judgment
    assert "grey: A/B build agents: collecting (n=0)" in rest
    assert "| sonnet | 4 |" in rest
    assert "unjoined: 2" in rest


def test_efficiency() -> None:
    out = panels.efficiency(EFFICIENCY)
    assert "(date range only)" in out
    assert "**done**: per DONE" in out
    assert "| 2026-W42 | $3.00 | 40% |" in out
    assert "**commits**: \n_no rows_" in out


def test_items_lists_repos_stages_and_items() -> None:
    out = views.items(ITEMS)
    assert out.startswith("**todoImplementer cost ")
    assert "$10.00 total" in out
    assert "**repos** (1 of 1 rows)" in out or "**repos**" in out
    assert "| abcd1234-0 | alpha | implement | 1 | 3 | 6 |" in out or "abcd1234-0" in out
    assert out.endswith(views.NOTE)
