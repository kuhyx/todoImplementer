import json
from pathlib import Path

from todoimpl.runner import session
from todoimpl.runner.session import Prior, TurnPlan


def test_plan_turn_resumes_a_recent_session() -> None:
    assert session.plan_turn(Prior("s1", 1000.0, None), now=1000.0 + 3599) == TurnPlan("s1", "")


def test_plan_turn_starts_fresh_after_an_idle_hour() -> None:
    assert session.plan_turn(Prior("s1", 1000.0, None), now=1000.0 + 3601) == TurnPlan(None, "idle")
    assert session.plan_turn(Prior("s1", 1000.0, "x"), now=1000.0 + 3601) == TurnPlan(None, "idle")


def test_plan_turn_resumes_a_killed_turn() -> None:
    assert session.plan_turn(Prior("s1", 1000.0, "tool Bash: make"), now=1001.0) == TurnPlan("s1", "killed")
    assert session.plan_turn(Prior(None, 0.0, "text: hi"), now=1.0) == TurnPlan(None, "killed")
    assert session.plan_turn(Prior(None, 0.0, None), now=1.0) == TurnPlan(None, "")
    assert session.plan_turn(None, now=1.0) == TurnPlan(None, "")


def test_prior_from_entry() -> None:
    assert session.prior_from({"session_id": "s", "last_turn_end": 7}) == Prior("s", 7.0, None)
    assert session.prior_from({"session_id": 3}) is None
    assert session.prior_from(None) is None


def test_lost_prior_reads_the_killed_stream(tmp_path: Path) -> None:
    stream = tmp_path / "implement-1.stream.jsonl"
    tool = {"type": "tool_use", "name": "Bash", "input": {"command": "make"}}
    lines = [
        {"type": "system", "subtype": "init", "session_id": "s9", "model": "m"},
        {"type": "assistant", "message": {"content": [tool]}},
    ]
    stream.write_text("".join(json.dumps(x) + "\n" for x in lines) + '{"torn', encoding="utf-8")
    prior = session.lost_prior(stream, {"session_id": "old", "last_turn_end": 1.0})
    assert prior.session_id == "s9"
    assert prior.lost == "tool Bash: make"
    assert prior.last_turn_end == stream.stat().st_mtime
    empty = tmp_path / "plan-1.stream.jsonl"
    empty.write_text("", encoding="utf-8")
    fallback = session.lost_prior(empty, {"session_id": "old", "last_turn_end": 1.0})
    assert (fallback.session_id, fallback.lost) == ("old", "nothing was recorded")
    assert session.lost_prior(empty, None).session_id is None


def test_handoff_summary_is_deterministic(tmp_path: Path) -> None:
    assert session.handoff_summary(tmp_path, "") == "No plan or reply was recorded yet."
    (tmp_path / "plan.md").write_text("## Acceptance criteria\n- a\n", encoding="utf-8")
    text = session.handoff_summary(tmp_path, "last reply")
    assert "## Acceptance criteria" in text
    assert "last reply" in text
