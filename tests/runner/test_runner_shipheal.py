"""T2340-T2343: Ship failures Claude can fix rest on the ladder or go back to the session, not to kuhy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from todoimpl.board.state import RunState
from todoimpl.runner import retry, shipfix, shipstage
from todoimpl.runner.deploy import DeployFailedError
from todoimpl.runner.deployline import NoDeployLineError
from todoimpl.runner.gate import GateRedError
from todoimpl.runner.shipfix import MAX_SHIP_FIXES

WAIT = "waiting for build lock held by bcf6a474-0 (pre-commit run --all-files) since 16:36:32; 1 ahead"
HOOK = "CI mirror (flutter clean, analyze, format check, test --coverage)......................."
NO_LINE = "pushed, not deployed: kuhyx/CV declares no deploy: command in CLAUDE.md"


def _child(**extra: Any) -> RunState:
    st = RunState(task_id="umbr0001-1", stage="shipping", repo="kuhyx/cv")
    st.extra.update(umbrella_round=1, **extra)
    return st


def _gate(code: int | None, tail: str) -> GateRedError:
    return GateRedError.build("ci-mirror", code, tail)


def test_t2340_a_gate_step_killed_while_it_only_waited_for_the_build_lock_is_requeued_without_end() -> None:
    st = _child()
    for _ in range(8):
        with pytest.raises(retry.RetryLaterError) as later:
            shipfix.heal(st, _gate(-15, f"{WAIT}\n"), 100.0)
        assert later.value.kind == "killed"
    assert "gate_kills" not in st.extra  # a wait is no kill: the step never ran
    assert "failure_tail" not in st.extra
    assert int(st.extra["gate_waits"]) == 8


def test_t2340_the_wait_only_reading_needs_nothing_but_the_wait_line() -> None:
    assert _gate(-15, f"{WAIT}\n\n").waited_only is True
    assert _gate(-15, f"{WAIT}\n{HOOK}").waited_only is False  # it got the lock and ran: OOM, a real kill
    assert _gate(1, WAIT).waited_only is False  # exit 1 is a red step, not a kill
    assert _gate(-15, "").waited_only is False


def test_t2341_a_gate_step_killed_mid_run_reruns_once_then_goes_to_the_session_to_shard_it() -> None:
    st = _child()
    first = _gate(-15, f"{WAIT}\n{HOOK}")
    assert first.killed
    assert first.text.startswith("Pre-push gate step ci-mirror is red (exit -15):")
    with pytest.raises(retry.RetryLaterError):
        shipfix.heal(st, first, 100.0)
    assert st.extra["gate_kills"] == 1
    line = shipfix.heal(st, _gate(-15, f"{WAIT}\n{HOOK}"), 200.0)
    assert line.startswith("gate step ci-mirror killed again, the session makes it fit (1/")
    assert st.extra["ship_fixes"] == 1
    assert st.extra["reship"] is True
    brief = str(st.extra["failure_tail"])
    assert "shard it finer" in brief
    assert "Pre-push gate step ci-mirror is red (exit -15)" in brief
    for _ in range(MAX_SHIP_FIXES - 1):
        shipfix.heal(st, _gate(-15, HOOK), 300.0)
    with pytest.raises(GateRedError):
        shipfix.heal(st, _gate(-15, HOOK), 400.0)


def test_t2341_a_red_gate_step_is_the_sessions_to_fix() -> None:
    st = _child()
    line = shipfix.heal(st, _gate(1, "test_x failed"), 100.0)
    assert line.startswith("gate step ci-mirror red, the session fixes it (1/")
    assert "test_x failed" in str(st.extra["failure_tail"])
    assert "Fix it yourself" in str(st.extra["failure_tail"])
    assert _gate(143, "x").killed is True
    assert _gate(None, "x").killed is False
    assert "timed out" in _gate(None, "x").text


def test_t2342_a_repo_with_no_deploy_line_goes_back_to_the_session_with_a_concrete_brief() -> None:
    st = _child()
    line = shipfix.heal(st, NoDeployLineError(NO_LINE), 100.0)
    assert line.startswith("no deploy line, the session adds one (1/")
    brief = str(st.extra["failure_tail"])
    assert NO_LINE in brief
    assert "- deploy: `<command>`" in brief
    assert "- deploy: none (<why>)" in brief
    assert st.extra["reship"] is True
    for _ in range(shipfix.MAX_DEPLOY_FIXES - 1):
        shipfix.heal(st, NoDeployLineError(NO_LINE), 100.0)
    with pytest.raises(NoDeployLineError) as stop:
        shipfix.heal(st, NoDeployLineError(NO_LINE), 100.0)
    assert stop.value.text.startswith(NO_LINE)
    assert "Retry" in stop.value.text  # what kuhy can do once the session's fix turns are spent


def test_t2343_an_umbrella_childs_red_deploy_gets_the_fix_turn_with_the_deploy_log() -> None:
    st = _child()
    line = shipfix.heal(st, DeployFailedError.build(34, "FAILURE: Build failed\nkotlin_version"), 100.0)
    assert line.startswith("deploy red, the session fixes it (1/")
    assert "kotlin_version" in str(st.extra["failure_tail"])
    assert "redeploy" in str(st.extra["failure_tail"])


def test_t2343_a_killed_deploy_is_retried_once_plainly_before_the_session_gets_it() -> None:
    st = _child()
    with pytest.raises(retry.RetryLaterError) as later:
        shipfix.heal(st, DeployFailedError.build(-15, "build.gradle"), 100.0)
    assert later.value.kind == "killed"
    assert (st.extra["deploy_kills"], "failure_tail" in st.extra) == (1, False)
    shipfix.heal(st, DeployFailedError.build(-15, "build.gradle"), 200.0)
    assert st.extra["deploy_fixes"] == 1


class _Driver:
    def __init__(self, tmp: Path, st: RunState) -> None:
        self.state, self.item = st, SimpleNamespace(body="x", parts=None)
        self.ctx = SimpleNamespace(run_dir=tmp, now=lambda: 50.0, client=None)
        self.lines: list[str] = []

    def activity(self, text: str) -> None:
        self.lines.append(text)


@pytest.mark.parametrize(
    "err",
    [_gate(1, "red"), NoDeployLineError(NO_LINE), DeployFailedError.build(34, "boom")],
)
def test_t2343_the_shipping_stage_sends_each_fixable_failure_back_to_implement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, err: Exception
) -> None:
    st = _child()
    st.checks = {"passed": True}

    def refuse(*_: object, **__: object) -> None:
        raise err

    monkeypatch.setattr(shipstage, "_ship_plan", lambda *_: SimpleNamespace())
    monkeypatch.setattr(shipstage, "ship", refuse)
    d = _Driver(tmp_path, st)
    assert shipstage.shipping(d) == "implement"  # type: ignore[arg-type]
    assert d.lines
    assert st.extra["reship"] is True


def test_t2406_a_deploy_that_says_busy_rerun_later_waits_on_the_ladder_not_for_kuhy() -> None:
    st = _child()
    busy = "deploy: tunedeck is playing; not interrupting it (exit 52, rerun later)"
    with pytest.raises(retry.RetryLaterError) as later:
        shipfix.heal(st, DeployFailedError.build(shipfix.BUSY_EXIT, busy), 100.0)
    assert "busy (exit 52)" in later.value.why
    assert ("deploy_fixes" in st.extra, "failure_tail" in st.extra) == (False, False)
    st.extra["retries"] = shipfix.MAX_DEPLOY_WAITS
    with pytest.raises(DeployFailedError):
        shipfix.heal(st, DeployFailedError.build(shipfix.BUSY_EXIT, busy), 200.0)
