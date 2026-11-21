"""T2465: a phone wait left by an earlier deploy no longer holds a deploy that failed for another reason."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from todoimpl.board import status as board_status
from todoimpl.board.state import RunState
from todoimpl.runner import shipfix
from todoimpl.runner.deploy import DeployFailedError
from todoimpl.umbrella import revive

if TYPE_CHECKING:
    from pathlib import Path

# Card 7808ee0a-0: both children first failed with the phone away (exit 30), then for these reasons.
DIRTY = "deploy: FAILED -- /home/kuhy/src/daily-limits has local changes"
GRADLE = (
    "FAILURE: Build failed with an exception.\n* What went wrong:\nA problem occurred (registered by plugin "
    "'com.android.internal.application').\nBUILD FAILED in 27s\nphone_deploy: flutter build failed (exit 34)"
)
LOGS = [(10, DIRTY), (34, GRADLE)]
MISSING = "deploy: FAILED -- phone 23181JEGR08034 is missing (desktop is deployed; plug it in and rerun)"


def _child(stage: str = "shipping") -> RunState:
    """Return an umbrella child that already waited once for the phone (exit 30, hours earlier)."""
    st = RunState(task_id="umbr0001-7", stage=stage, repo="kuhyx/daily-limits")
    st.extra.update(umbrella_round=5, phone_tries=1, phone_update={"since": 1.0, "tries": 1})
    return st


@pytest.mark.parametrize(("code", "tail"), LOGS)
def test_t2465_a_non_phone_deploy_failure_drops_the_old_phone_wait_and_gets_a_fix_turn(
    code: int, tail: str
) -> None:
    st = _child()
    line = shipfix.heal(st, DeployFailedError.build(code, tail), 100.0)
    assert line == f"deploy red, the session fixes it (1/{shipfix.MAX_DEPLOY_FIXES})"
    assert "phone_update" not in st.extra
    assert tail in str(st.extra["failure_tail"])


@pytest.mark.parametrize(("code", "tail"), LOGS)
def test_t2465_spent_fix_turns_need_kuhy_not_the_phone(code: int, tail: str) -> None:
    st = _child()
    st.extra["deploy_fixes"] = shipfix.MAX_DEPLOY_FIXES
    err = DeployFailedError.build(code, tail)
    with pytest.raises(DeployFailedError):
        shipfix.heal(st, err, 100.0)
    st.stage, st.error = "failed", err.text
    assert board_status._resting(st, live=False) == board_status.Status.NEEDS_YOU


@pytest.mark.parametrize(("code", "tail"), LOGS)
def test_t2465_a_child_stuck_in_the_old_phone_wait_is_revived_on_server_start(
    tmp_path: Path, code: int, tail: str
) -> None:
    st = _child("failed")
    st.error = DeployFailedError.build(code, tail).text
    st.extra["failed_stage"] = "shipping"
    assert revive.revive(st, tmp_path, 100.0) is True
    assert st.stage == "implement"
    assert st.error is None
    assert "phone_update" not in st.extra


def test_t2465_the_phone_away_still_waits_for_the_phone() -> None:
    st = _child()
    with pytest.raises(DeployFailedError):
        shipfix.heal(st, DeployFailedError.build(30, MISSING), 100.0)
    assert st.extra["phone_update"] == {"since": 100.0, "tries": 2}
