from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from todoimpl.usage import oauth, usage_summary

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

NOW = datetime(2026, 11, 5, 12, 0).timestamp()  # noqa: DTZ001
YESTERDAY = datetime(2026, 11, 4, 12, 0).timestamp()  # noqa: DTZ001


def test_empty_root_validates_against_the_contract(tmp_path: Path, usage_validator: Any) -> None:
    out = usage_summary(tmp_path / "missing", now=NOW)
    usage_validator.validate(out)
    assert out["five_hour"] is None
    assert out["overage"] == {"status": "unknown", "using": False}
    limit = {"active": False, "until": None, "credits": out["limit"]["credits"]}
    assert out["limit"] == {**limit, "weekly_hold": "none", "weekly_used": None}
    assert out["cost"] == {"today_usd": 0.0, "total_usd": 0.0, "per_task": []}


def test_costs_per_task_today_and_total(
    tmp_path: Path,
    write_stream: Callable[..., Path],
    usage_validator: Any,
    result: Callable[..., dict[str, Any]],
) -> None:
    write_stream(tmp_path / "aaaaaaaa-0", "plan", [result(0.5, "s-a")], YESTERDAY)
    write_stream(tmp_path / "aaaaaaaa-0", "impl", [result(1.0, "s-b")], NOW)
    write_stream(tmp_path / "bbbbbbbb-0", "plan", [result(3.0, "s-c")], NOW)
    write_stream(tmp_path / "cccccccc-0", "plan", [{"type": "assistant"}], NOW)
    (tmp_path / "dddddddd-0").mkdir()
    (tmp_path / "limit-until").write_text("0")
    out = usage_summary(tmp_path, now=NOW, titles={"aaaaaaaa-0": "Fix the thing"})
    usage_validator.validate(out)
    assert out["generated_at"] == NOW
    assert out["cost"] == {
        "today_usd": 4.0,
        "total_usd": 4.5,
        "per_task": [
            {"id": "bbbbbbbb-0", "title": "bbbbbbbb-0", "cost_usd": 3.0},
            {"id": "aaaaaaaa-0", "title": "Fix the thing", "cost_usd": 1.5},
            {"id": "cccccccc-0", "title": "cccccccc-0", "cost_usd": 0.0},
        ],
    }


def test_rate_limits_come_from_the_latest_events(
    tmp_path: Path,
    write_stream: Callable[..., Path],
    usage_validator: Any,
    rate: Callable[..., dict[str, Any]],
) -> None:
    older = rate(overageStatus="allowed", isUsingOverage=True)
    older["rate_limit_info"]["unifiedWindows"]["five_hour"]["utilization"] = 0.9
    newer = rate(overageStatus="rejected")
    newer["rate_limit_info"]["unifiedWindows"].pop("five_hour")
    write_stream(tmp_path / "aaaaaaaa-0", "plan", [older], YESTERDAY)
    write_stream(tmp_path / "bbbbbbbb-0", "plan", [newer, {"type": "rate_limit_event"}], NOW)
    out = usage_summary(tmp_path, now=NOW)
    usage_validator.validate(out)
    assert out["five_hour"] == {"utilization": 0.9, "resets_at": 1794000000.0, "status": "allowed"}
    assert out["seven_day"] == {"utilization": 0.77, "resets_at": 1794100000.0, "status": "allowed_warning"}
    assert out["overage"] == {"status": "rejected", "using": False}


def test_top_level_info_fills_a_window_without_unified_windows(
    tmp_path: Path, write_stream: Callable[..., Path], rate: Callable[..., dict[str, Any]]
) -> None:
    ev = rate("five_hour", utilization=0.4, resetsAt=1794200000, status="allowed")
    del ev["rate_limit_info"]["unifiedWindows"]
    bad = rate("seven_day", utilization="high")
    del bad["rate_limit_info"]["unifiedWindows"]
    other = rate("other_limit")
    del other["rate_limit_info"]["unifiedWindows"]
    write_stream(tmp_path / "aaaaaaaa-0", "plan", [ev, bad, other], NOW)
    out = usage_summary(tmp_path, now=NOW)
    assert out["five_hour"] == {"utilization": 0.4, "resets_at": 1794200000.0, "status": "allowed"}
    assert out["seven_day"] is None


def test_garbage_rate_info_is_ignored(tmp_path: Path, write_stream: Callable[..., Path]) -> None:
    ev = {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "overageStatus": 5,
            "isUsingOverage": "yes",
            "unifiedWindows": {"five_hour": "x"},
        },
    }
    write_stream(
        tmp_path / "aaaaaaaa-0", "plan", [ev, {"type": "rate_limit_event", "rate_limit_info": 3}], NOW
    )
    out = usage_summary(tmp_path, now=NOW)
    assert out["five_hour"] is None
    assert out["overage"] == {"status": "unknown", "using": False}


def test_active_limit_carries_the_credits_view(tmp_path: Path, usage_validator: Any) -> None:
    (tmp_path / "limit-until").write_text(str(NOW + 600))
    out = usage_summary(tmp_path, now=NOW)
    usage_validator.validate(out)
    assert out["limit"]["active"] is True
    assert out["limit"]["until"] == NOW + 600
    assert out["limit"]["credits"]["state"] == "unavailable"
    (tmp_path / "limit-until").write_text(str(NOW - 1))
    assert usage_summary(tmp_path, now=NOW)["limit"]["until"] is None


def test_default_now_is_the_wall_clock(tmp_path: Path) -> None:
    out = usage_summary(tmp_path)
    assert out["generated_at"] > NOW
    json.dumps(out)


def test_t1882_a_window_past_its_reset_is_not_shown(
    tmp_path: Path,
    write_stream: Callable[..., Path],
    rate: Callable[..., dict[str, Any]],
    usage_validator: Any,
) -> None:
    """The header kept "5 h 76% resets now" from a stream line written before the reset."""
    ev = rate()
    ev["rate_limit_info"]["unifiedWindows"]["five_hour"] = {
        "utilization": 0.76,
        "resetsAt": NOW - 60,
        "status": "allowed_warning",
    }
    write_stream(tmp_path / "aaaaaaaa-0", "plan", [ev], NOW)
    out = usage_summary(tmp_path, now=NOW)
    usage_validator.validate(out)
    assert out["five_hour"] is None
    assert out["seven_day"] is not None


def test_t1882_a_fresh_probe_replaces_the_stream_windows(
    tmp_path: Path,
    write_stream: Callable[..., Path],
    rate: Callable[..., dict[str, Any]],
    usage_validator: Any,
) -> None:
    write_stream(tmp_path / "aaaaaaaa-0", "plan", [rate()], NOW)
    oauth.save(tmp_path, oauth.Probe(NOW - 60, None, oauth.Window(0.03, NOW + 3 * 86400)))
    out = usage_summary(tmp_path, now=NOW)
    usage_validator.validate(out)
    assert out["five_hour"] is None
    assert out["seven_day"] == {"utilization": 0.03, "resets_at": NOW + 3 * 86400, "status": "allowed"}
    oauth.save(tmp_path, oauth.Probe(NOW - 60, oauth.Window(1.0, NOW + 60), None))
    assert usage_summary(tmp_path, now=NOW)["five_hour"]["status"] == "rejected"
    oauth.save(tmp_path, oauth.Probe(NOW - 4000, None, None))  # too old to trust: the stream shows again
    assert usage_summary(tmp_path, now=NOW)["seven_day"]["utilization"] == 0.77
