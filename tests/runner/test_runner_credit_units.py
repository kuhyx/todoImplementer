"""Units of the credit route: overage guard, post-turn pause, cost across routes, session across routes."""

import json
import time
from pathlib import Path
from typing import Any

import pytest
from creditfakes import enable_credits
from runnerfakes import Env
from todoimpl.board.state import RunState
from todoimpl.credits import marks, setting
from todoimpl.runner import files, guard, limits, turn, turncheck
from todoimpl.runner.stream import TurnResult

NOW = 1_793_880_000.0


def event(**info: Any) -> dict[str, Any]:
    return {"type": "rate_limit_event", "rate_limit_info": info}


def test_reset_is_the_latest_window_at_its_limit() -> None:
    windows = {
        "five_hour": {"status": "rejected", "resetsAt": NOW + 100, "utilization": 1.0},
        "seven_day": {"status": "allowed", "resetsAt": NOW + 9000, "utilization": 0.4},
        "other": {"status": "allowed", "resetsAt": NOW + 500, "utilization": 1.0},
        "old": {"status": "rejected", "resetsAt": NOW - 5, "utilization": 1.0},
    }
    assert guard.reset_of(event(unifiedWindows=windows, resetsAt=NOW + 7), NOW) == NOW + 500


def test_reset_falls_back_to_the_top_level_then_to_a_pause() -> None:
    assert guard.reset_of(event(rateLimitType="five_hour", resetsAt=NOW + 70), NOW) == NOW + 70
    paused = guard.reset_of(event(rateLimitType="overage", resetsAt=NOW + 70), NOW)
    assert paused == NOW + limits.FALLBACK_PAUSE  # an overage window's own reset is never used
    assert guard.reset_of({"rate_limit_info": 3}, NOW) == NOW + limits.FALLBACK_PAUSE
    assert (
        guard.reset_of(event(rateLimitType="five_hour", resetsAt=NOW - 1), NOW) == NOW + limits.FALLBACK_PAUSE
    )


def test_the_guard_acts_once_on_the_first_overage_line(tmp_path: Path) -> None:
    log: list[str] = []
    guarded = guard.OverageGuard(
        tmp_path,
        "abcd1234-0",
        lambda: log.append("stop"),
        lambda _text: log.append("announce"),
        lambda until: log.append(f"hit {until}"),
        lambda: NOW,
    )
    fine = event(status="allowed", isUsingOverage=False, rateLimitType="five_hour", resetsAt=NOW + 60)
    assert guarded.feed(json.dumps(fine)) == []
    line = json.dumps(
        event(status="allowed", isUsingOverage=True, rateLimitType="five_hour", resetsAt=NOW + 60)
    )
    out = guarded.feed(line)
    assert [a.kind for a in out] == ["error"]
    assert guarded.feed(line) == []  # sticky: acts once
    assert log == ["announce", f"hit {NOW + 60}", "stop"]
    assert limits.active_until(tmp_path, NOW) == NOW + 60
    alert = marks.active_alert(tmp_path, NOW)
    assert alert is not None
    assert "abcd1234-0" in alert["text"]


def result(
    *, error: bool = False, text: str = "ok", cost: float = 0.0, session: str | None = "s"
) -> TurnResult:
    return TurnResult(session_id=session, cost_usd=cost, text=text, is_error=error, finished=True)


def test_pause_after_a_plan_turn_reads_its_limit_and_writes_it(tmp_path: Path) -> None:
    st = RunState(task_id="t-0", stage="plan", extra={"route": "plan"})
    assert turncheck.pause_after(st, tmp_path, result(), NOW) is None
    assert (
        turncheck.pause_after(st, tmp_path, result(error=True, text="usage limit|1793955600"), NOW)
        == 1793955600.0
    )
    assert limits.active_until(tmp_path, NOW) == 1793955600.0


def test_pause_after_a_credit_turn_ignores_rate_limits_and_other_errors(tmp_path: Path) -> None:
    st = RunState(task_id="t-0", stage="plan", extra={"route": "credits"})
    assert (
        turncheck.pause_after(st, tmp_path, result(error=True, text="API Error: 429 rate_limit_error"), NOW)
        is None
    )
    assert (
        turncheck.pause_after(st, tmp_path, result(error=True, text="API Error: 529 overloaded"), NOW) is None
    )
    assert not (tmp_path / "limit-until").exists()


def test_credit_exhaustion_marks_until_the_limit_end_or_a_pause(tmp_path: Path) -> None:
    st = RunState(task_id="t-0", stage="plan", extra={"route": "credits"})
    broke = result(error=True, text="API Error: invalid x-api-key")
    assert turncheck.pause_after(st, tmp_path, broke, NOW) == NOW + limits.FALLBACK_PAUSE
    limits.write_until(tmp_path, NOW + 50)
    assert turncheck.pause_after(st, tmp_path, broke, NOW) == NOW + 50
    assert marks.exhausted(tmp_path, NOW)
    empty = result(error=True, text="Credit balance is too low")  # empty balance: off for good
    assert turncheck.pause_after(st, tmp_path, empty, NOW) == NOW + 50  # the plan limit holds the card
    assert setting.off() == ("balance too low", NOW)


def test_an_overage_hit_wins_and_is_consumed(tmp_path: Path) -> None:
    st = RunState(task_id="t-0", stage="plan", extra={"route": "plan", "overage_hit": NOW + 9})
    assert turncheck.pause_after(st, tmp_path, result(), NOW) == NOW + 9
    assert "overage_hit" not in st.extra
    assert turncheck.pause_after(st, tmp_path, result(), NOW) is None


def test_cost_is_cumulative_per_session_and_a_restart_counts_whole(tmp_path: Path) -> None:
    st = RunState(task_id="t-0", stage="plan")
    assert turn._turn_cost(st, result(cost=0.5)) == 0.5
    assert turn._turn_cost(st, result(cost=0.8)) == pytest.approx(0.3)
    assert turn._turn_cost(st, result(cost=0.2)) == 0.2  # below the last total: the counter restarted
    assert turn._turn_cost(st, result(cost=0.0)) == 0.0  # no information: nothing changes
    assert turn._turn_cost(st, result(cost=0.5)) == pytest.approx(0.3)
    assert turn._turn_cost(st, result(cost=0.7, session=None)) == 0.7


def test_route_of_a_turn_defaults_to_the_plan(tmp_path: Path) -> None:
    assert files.route_of(tmp_path, "s") == "plan"
    (tmp_path / "s.route").write_text("credits\n")
    assert files.route_of(tmp_path, "s") == "credits"
    (tmp_path / "s.route").write_text("bogus\n")
    assert files.route_of(tmp_path, "s") == "plan"


def env_for(world: Env, run_dir: Path) -> turn.TurnEnv:
    wt = run_dir / "wt"
    wt.mkdir(parents=True)
    return turn.TurnEnv(run_dir, wt, lambda _e: None, lambda _h: None, time.time)


@pytest.mark.parametrize("routes", [("plan", "credits"), ("credits", "plan")])
def test_the_session_id_carries_across_routes(
    world: Env, monkeypatch: pytest.MonkeyPatch, routes: tuple[str, str]
) -> None:
    enable_credits(monkeypatch)
    run_dir = world.root / "abcd1234-0"
    env = env_for(world, run_dir)
    st = RunState(task_id="abcd1234-0", stage="implement")
    first = turn.run_turn(env, st, "implement", lambda _s: "one", route=routes[0])
    second = turn.run_turn(env, st, "implement", lambda _s: "two", route=routes[1])
    one, two = world.calls()
    assert (one["via_sdk"], two["via_sdk"]) == tuple(r == "credits" for r in routes)
    assert one["resume"] is None
    assert two["resume"] == first.session_id == second.session_id
    assert st.sessions["implement"]["route"] == routes[1]
    assert st.extra["route"] == routes[1]
    saved = json.loads((run_dir / next(p.name for p in run_dir.glob("*.result.json"))).read_text())
    assert saved["route"] in routes
