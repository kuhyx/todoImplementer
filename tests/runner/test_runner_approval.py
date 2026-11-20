"""A `(kuhy)` criterion (kuhy judges or approves a deliverable) blocks Ship until he answered (T2362)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from runnerfakes import FakeClient
from todoimpl.prompts import PromptContext, build
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.live import settle
from todoimpl.runner.pipeline import Driver

PLAN = (
    "## Acceptance criteria\n"
    "C1. I open DOCS-email-owner.md, I see a Polish mail\n"
    "C2. (kuhy) kuhy approves the mail in the board ask, then it is sent\n"
)
ALL_TICKED = "- [x] C1: opened -> Polish mail\n- [x] C2: mail is ready to judge"


def stub(run_dir: Path, client: FakeClient | None = None) -> Any:
    """Return a Driver look-alike with a real run dir, where asks.json lives."""
    fake = SimpleNamespace(
        state=SimpleNamespace(extra={}, sessions={"live_check": {"session_id": "l"}}, task_id=""),
        item=SimpleNamespace(title="kalisz", repo="kuhyx/demo"),
        ctx=SimpleNamespace(client=client or FakeClient(), run_dir=run_dir),
        plan_md=lambda: PLAN,
        save=lambda: None,
    )
    return cast("Driver", fake)


def answered(run_dir: Path, **items: dict[str, Any]) -> None:
    """Write asks.json the way AskService does after kuhy's click (stamped now unless given)."""
    stamped = {key: {"at": time.time(), **record} for key, record in items.items()}
    (run_dir / "asks.json").write_text(json.dumps({"items": stamped}), encoding="utf-8")


def test_t2362_an_approval_from_an_earlier_cycle_does_not_count(tmp_path: Path) -> None:
    d = stub(tmp_path)
    (tmp_path / "plan.md").write_text(PLAN, encoding="utf-8")  # each cycle clears and rewrites the plan
    planned = (tmp_path / "plan.md").stat().st_mtime
    answered(tmp_path, c2={"state": "answered", "answer": "approve", "at": planned - 60})
    assert settle(d, ALL_TICKED) == "live_check"
    answered(tmp_path, c2={"state": "answered", "answer": "approve", "at": planned + 1})
    assert settle(d, ALL_TICKED) == "checks"


def test_t2362_session_ticking_kuhys_criterion_does_not_ship(tmp_path: Path) -> None:
    d = stub(tmp_path)
    assert settle(d, ALL_TICKED) == "live_check"  # back to the session: show kuhy the deliverable
    assert "C2" in str(d.state.extra["nudge"])
    with pytest.raises(NeedsYouError, match="C2"):
        settle(d, ALL_TICKED)


def test_t2362_open_or_deferred_kuhy_criterion_never_ships_partly(tmp_path: Path) -> None:
    client = FakeClient()
    d = stub(tmp_path, client)
    d.state.extra |= {"live_fixes": 1, "approval_nudges": 1}
    for report in ("- [x] C1: ok\n- [ ] C2: waits for kuhy", "- [x] C1: ok\n- [~] C2: after ship"):
        with pytest.raises(NeedsYouError, match="C2"):
            settle(d, report)
    assert client.added == []  # no follow-up note: kuhy's judgement is never deferred to a timer


def test_t2362_only_kuhys_approve_click_opens_the_gate(tmp_path: Path) -> None:
    d = stub(tmp_path)
    answered(tmp_path, c2={"state": "auto", "answer": "approve"})
    assert settle(d, ALL_TICKED) == "live_check"
    answered(tmp_path, c2={"state": "answered", "answer": "change"})  # his own answer: said plainly (T2376)
    with pytest.raises(NeedsYouError, match="you answered c2: change"):
        settle(d, ALL_TICKED)
    answered(tmp_path, c2={"state": "answered", "answer": "approve"})
    assert settle(d, ALL_TICKED) == "checks"
    assert "approval_nudges" not in d.state.extra


def test_t2362_plan_and_live_check_prompts_carry_the_kuhy_criterion(tmp_path: Path) -> None:
    ctx = PromptContext(title="t", body="", repo="r", worktree=tmp_path, run_dir=tmp_path)
    assert "`Cn. (kuhy) kuhy approves" in build("plan", ctx)
    live = build("live_check", ctx)
    assert "`(kuhy)` criterion is kuhy's, never yours to tick" in live
    assert "| *approve | change`" in live
    assert "never a `(kuhy)` criterion" in live  # the standing grant's "approve your own drafts" stops there


def test_t2376_kuhys_approval_counts_in_every_form_the_board_records(tmp_path: Path) -> None:
    d = stub(tmp_path)
    for record in (
        {"c2": {"state": "answered", "answer": "approve once the gaps are filled"}},
        {"c2": {"state": "approved"}},  # Approve on a screenshot c2
        {"verdict": {"state": "answered", "answer": "approve once the gaps are filled"}},  # 1c1ca49b-0's ask
    ):
        answered(tmp_path, **record)
        assert settle(d, ALL_TICKED) == "checks"


def test_t2376_an_answered_but_unapproved_criterion_is_needs_you_not_a_new_ask(tmp_path: Path) -> None:
    d = stub(tmp_path)
    answered(
        tmp_path, c2={"state": "rejected"}, verdict={"state": "answered", "answer": "revise (type notes)"}
    )
    with pytest.raises(NeedsYouError, match="C2 is not approved: you answered c2: rejected"):
        settle(d, ALL_TICKED)
    assert "nudge" not in d.state.extra
    assert "approval_nudges" not in d.state.extra


def test_t2376_an_approve_of_another_id_counts_only_for_a_sole_kuhy_criterion(tmp_path: Path) -> None:
    d = stub(tmp_path)
    d.plan_md = lambda: PLAN + "C3. (kuhy) kuhy approves the logo in the board ask\n"
    answered(tmp_path, verdict={"state": "answered", "answer": "approve"})
    assert settle(d, ALL_TICKED + "\n- [x] C3: logo") == "live_check"
    assert "C2, C3" in str(d.state.extra["nudge"])
