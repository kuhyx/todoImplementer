from pathlib import Path

from todoimpl.runner import limits
from todoimpl.usage.limits import limit_state


def test_parse_event_reads_the_top_level_status_only() -> None:
    info = limits.parse_event(
        {
            "rate_limit_info": {
                "status": "allowed_warning",
                "resetsAt": 1793955600,
                "rateLimitType": "seven_day",
                "overageStatus": "rejected",
            }
        }
    )
    assert info is not None
    assert (info.status, info.resets_at, info.kind, info.overage_status) == (
        "allowed_warning",
        1793955600.0,
        "seven_day",
        "rejected",
    )
    assert not limits.blocking(info)
    assert limits.parse_event({"rate_limit_info": "x"}) is None
    odd = limits.parse_event({"rate_limit_info": {"resetsAt": True}})
    assert odd is not None
    assert (odd.status, odd.resets_at, odd.kind) == ("", None, None)


def test_blocking_needs_rejected_and_no_overage() -> None:
    rejected = limits.LimitInfo("rejected", 10.0, None, None, using_overage=False)
    assert limits.blocking(rejected)
    assert not limits.blocking(limits.LimitInfo("rejected", 10.0, None, None, using_overage=True))
    assert not limits.blocking(None)


def test_pause_until_from_event_text_or_fallback() -> None:
    now = 1000.0
    assert (
        limits.pause_until(limits.LimitInfo("rejected", 5000.0, None, None), "", is_error=True, now=now)
        == 5000.0
    )
    assert (
        limits.pause_until(limits.LimitInfo("rejected", None, None, None), "", is_error=True, now=now)
        == 2800.0
    )
    text = "Claude AI usage limit reached|1793955600"
    assert limits.pause_until(None, text, is_error=True, now=now) == 1793955600.0
    assert limits.pause_until(None, "You've hit your limit · resets 3pm", is_error=True, now=now) == 2800.0
    assert limits.pause_until(None, text, is_error=False, now=now) is None
    assert limits.pause_until(None, "boom", is_error=True, now=now) is None


def test_limit_files_round_trip_with_the_usage_reader(tmp_path: Path) -> None:
    root = tmp_path / "root"
    assert limits.active_until(root, 0.0) is None
    limits.write_until(root, 500.0)
    assert limits.active_until(root, 100.0) == 500.0
    assert limits.active_until(root, 600.0) is None
    assert not limits.credits_granted(root)
    limits.grant_credits(root)
    assert limits.credits_granted(root)
    assert limit_state(root).until == 500.0
    limits.clear(root)
    assert limit_state(root).until is None
    assert not limits.credits_granted(root)
    limits.clear(root)
