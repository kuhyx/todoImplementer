# ruff: noqa: S108
"""build_board / build_task / repo_checker: payloads validate against the contracts."""

import json
import time
from pathlib import Path

import pytest
from board_helpers import LIMITED, NOW, STAGES, Note, ctx, run
from contract_lib import validate
from todoimpl.board import board
from todoimpl.board.card import build_card, current_line
from todoimpl.board.state import SpecQuestion
from todoimpl.board.status import Status
from todoimpl.board.types import Limit

FIXTURES = Path(__file__).parent.parent / "fixtures"


def notes() -> list[Note]:
    return [
        Note(id="aaaaaaaa-0", title="backlog", repo="beta"),
        Note(id="bbbbbbbb-0", title="running", repo="alpha"),
        Note(id="cccccccc-0", title="no repo", repo=None),
        Note(id="dddddddd-0", title="ask", repo="alpha"),
        Note(id="eeeeeeee-0", title="ready", repo="alpha"),
        Note(id="ffffffff-0", title="closed", repo="alpha", status="done"),
    ]


def runs() -> dict[str, object]:
    return {
        "bbbbbbbb-0": run(task_id="bbbbbbbb-0", stage="checks", session_id="s", worktree="/w"),
        "dddddddd-0": run(task_id="dddddddd-0", stage="spec_wait", spec_questions=[SpecQuestion("Q1", "t")]),
        "eeeeeeee-0": run(task_id="eeeeeeee-0", stage="gate", worktree="/w"),
    }


def test_board_groups_validates_and_counts() -> None:
    out = board.build_board(notes(), runs(), ctx(live=("bbbbbbbb-0",)), "abc1234")  # type: ignore[arg-type]
    validate("board", out)
    assert [t["title"] for t in out["tasks"]] == ["backlog", "no repo", "running", "ready", "ask", "closed"]
    assert [(c["id"], c["count"]) for c in out["columns"]] == [
        ("backlog", 2),
        ("running", 2),  # T2060: the card at the gate is shipping, not in a Ready column
        ("needs_you", 1),
        ("done", 1),
    ]
    assert out["repos"] == ["alpha", "beta"]
    assert out["slots"] == {"used": 1}
    assert out["build"] == "abc1234"
    assert out["generated_at"] == NOW


def test_no_cap_on_parallel_runs_every_start_stays_enabled() -> None:
    live = tuple(f"{i:08d}-0" for i in range(4))
    running = [Note(id=card, repo="alpha") for card in live]
    waiting = [Note(id=f"{i + 10:08d}-0", repo="alpha") for i in range(5)]
    states = {card: run(task_id=card, stage="implement", session_id="s", worktree="/w") for card in live}
    out = board.build_board([*running, *waiting], states, ctx(live=live), "b")
    validate("board", out)
    assert out["slots"] == {"used": 4}
    starts = [t["actions"][0] for t in out["tasks"] if t["status"] == "backlog"]
    assert len(starts) == 5
    assert all(a["id"] == "start" and a["enabled"] and a["reason"] is None for a in starts)


def test_board_under_a_limit_exposes_it() -> None:
    out = board.build_board([Note()], {}, ctx(limit=LIMITED), "b")
    validate("board", out)
    limit = {"active": True, "until": NOW + 3600, "credits": LIMITED.credits.to_dict()}
    assert out["limit"] == {**limit, "weekly_hold": "none", "weekly_used": None, "weekly_allowance": None}
    assert out["tasks"][0]["actions"][0]["enabled"] is False


def test_empty_board_validates() -> None:
    out = board.build_board([], {}, ctx(), "b")
    validate("board", out)
    assert out["tasks"] == []
    assert out["repos"] == []


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("limit", [Limit(), LIMITED])
def test_every_card_validates_and_has_one_status(stage: str, live: bool, limit: Limit) -> None:
    state = run(stage=stage, session_id="s", worktree="/w", error=None, resume_at=NOW + 60)
    card = build_card(Note(), state, ctx(live=("c59d2588-0",) if live else (), limit=limit))
    validate("common", card, "task_card")
    assert (card["needs"] is not None) == (card["status"] == "needs_you")
    assert (card["resumes_at"] is not None) == (card["status"] == "paused_limit")


def test_card_without_a_run_and_closed_note() -> None:
    card = build_card(Note(repo=None), None, ctx())
    validate("common", card, "task_card")
    assert (card["assignee"], card["stage"], card["status"], card["cost_usd"], card["updated"]) == (
        "human",
        None,
        "yours",
        0,
        None,
    )
    assert card["current"] == "yours: no repo on this note"
    assert build_card(Note(), None, ctx())["assignee"] == "claude"


def test_card_repo_missing_is_named_in_the_start_reason() -> None:
    card = build_card(Note(), None, ctx(missing="~/src/demo"))
    assert card["actions"][0]["reason"] == "repo ~/src/demo not found"


def test_resumes_at_falls_back_to_the_limit() -> None:
    card = build_card(Note(), run(stage="paused_limit"), ctx(limit=LIMITED))
    assert card["resumes_at"] == LIMITED.until
    assert "resumes" in card["current"]
    assert current_line(Status.PAUSED_LIMIT, run(), None, NOW) == "paused by the usage limit"


def test_t1214_a_run_waiting_to_retry_says_when_and_why() -> None:
    at = time.strftime("%H:%M", time.localtime(NOW))
    waiting = run(stage="paused_retry", resume_at=NOW, extra={"retry_reason": "offline"})
    assert current_line(Status.WORKING, waiting, None, NOW) == f"retrying at {at}: offline"
    assert current_line(Status.WORKING, run(stage="paused_retry"), None, NOW).endswith(": a failed turn")
    card = build_card(Note(), waiting, ctx())
    assert (card["status"], card["column"]) == ("working", "running")
    validate("state", waiting.to_dict())


def test_t2060_a_shipping_card_names_its_step() -> None:
    stepping = run(stage="shipping", extra={"ship_step": "pushing"})
    assert current_line(Status.SHIPPING, stepping, None, NOW) == "shipping: pushing"
    assert current_line(Status.SHIPPING, run(stage="shipping"), None, NOW) == "pushing and closing the note"


def test_current_lines() -> None:
    cases = [
        (Status.WORKING, run(stage="live_check"), "live_check"),
        (Status.WORKING, run(stage="implement"), "implement"),
        (Status.QUEUED, run(stage="plan"), "waiting to continue plan"),
        (Status.NEEDS_YOU, run(error="boom"), "boom"),
        (Status.BACKLOG, None, "not started"),
        (Status.YOURS, run(assignee="human"), "assigned to you"),
        (Status.DONE, None, "done"),
    ]
    for status, state, line in cases:
        assert current_line(status, state, None, NOW) == line


def test_task_payload_matches_contract_and_fixture_shape(tmp_path: Path) -> None:
    (tmp_path / "plan.md").write_text("# Plan\n", encoding="utf-8")
    state = run(
        stage="live_check",
        session_id="5f0e",
        worktree="/tmp/w",
        branch="b",
        skills_loaded=["x"],
        live_check={"report_md": "Ran demo.py; saw hello.", "shots": ["evidence/shot1.png"]},
        self_check=[{"criterion": "demo prints hello", "done": True}],
        checks={
            "passed": True,
            "ran_at": NOW,
            "results": [{"command": "make test", "exit": 0, "tail": "ok"}],
        },
        started_at=NOW - 10,
        spec_questions=[SpecQuestion("Q1", "Scope", "Which?", "demo.py", "demo.py")],
    )
    diff = {
        "files": [{"path": "demo.py", "added": 2, "removed": 0}],
        "patch": "diff --git",
        "truncated": False,
    }
    out = board.build_task(Note(), state, tmp_path, ctx(live=("c59d2588-0",)), diff)
    validate("task", out)
    assert out["plan_md"] == "# Plan\n"
    assert out["resume_command"] == "cd /tmp/w && claude --resume 5f0e"
    assert out["live_check"] == state.live_check
    assert out["stages"] == [{"stage": "live_check", "started": NOW - 10, "ended": None}]
    assert out["card"]["status"] == "working"
    fixture = json.loads((FIXTURES / "task.json").read_text(encoding="utf-8"))
    assert set(out) == set(fixture)


def test_task_payload_without_a_run_validates(tmp_path: Path) -> None:
    out = board.build_task(Note(), None, tmp_path / "none", ctx())
    validate("task", out)
    assert out["plan_md"] is None
    assert (out["stages"], out["questions"], out["self_check"], out["resume_command"]) == ([], [], [], None)
    assert (out["checks"], out["live_check"]) == (None, None)


def test_task_payload_uses_recorded_stage_history_and_without_start_time(tmp_path: Path) -> None:
    recorded = [{"stage": "plan", "started": 1.0, "ended": 2.0}]
    assert board.build_task(Note(), run(stages=recorded), tmp_path, ctx())["stages"] == recorded
    assert board.build_task(Note(), run(), tmp_path, ctx())["stages"][0]["started"] == NOW


def test_resume_command_needs_session_and_worktree() -> None:
    assert board.resume_command(None) is None
    assert board.resume_command(run(session_id="s")) is None
    assert board.resume_command(run(worktree="/w")) is None


def test_repo_checker(tmp_path: Path) -> None:
    (tmp_path / "ok" / ".git").mkdir(parents=True)
    check = board.repo_checker()
    assert check(None) is None
    assert check("ok") is None
    assert check("nope") is None  # a relative repo is found by origin or cloned by Start (T2079)
    assert check(str(tmp_path / "ok")) is None
    assert check(str(tmp_path / "nope")) == str(tmp_path / "nope")
    home = Path.home()
    assert check(str(home / "zzz-not-a-repo-xyz")) == "~/zzz-not-a-repo-xyz"
