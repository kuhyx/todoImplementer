"""The board's view of the free credits fallback: setting, limit text, route badge, alert, manual work."""

import os
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from contract_lib import validate
from servicefakes import Rig
from todoimpl.apikey import cache
from todoimpl.apikey.keystatus import KeyStatus
from todoimpl.credits import marks

KEY = "sk-ant-api03-" + "x" * 30


@pytest.fixture
def ready(rig: Rig, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> Rig:
    """Credits usable (key, SDK python, cached ok) and an active plan limit."""
    Path(os.environ["TODOIMPL_APIKEY"]).write_text(KEY, encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_SDK_PYTHON", sys.executable)
    cache.put(KeyStatus("ok", date(2099, 1, 1), "fine"))
    rig.root.mkdir(parents=True, exist_ok=True)
    (rig.root / "limit-until").write_text(str(time.time() + 3600), encoding="utf-8")
    return rig


def test_toggle_is_stored_and_shown_by_the_server(ready: Rig) -> None:
    ready.note()
    assert ready.backend.board()["limit"]["credits"]["state"] == "ready"
    off = ready.backend.set_credits_fallback(enabled=False)
    assert off["state"] == "off"
    board = ready.backend.board()
    validate("board", board)
    assert board["limit"]["credits"] == off
    assert ready.backend.set_credits_fallback(enabled=True)["state"] == "ready"


def test_t1850_a_queued_run_is_not_paused_while_credits_take_over(ready: Rig) -> None:
    tid = ready.note()
    ready.run(tid, "implement")
    assert ready.card(tid)["status"] == "queued"
    ready.backend.set_credits_fallback(enabled=False)
    assert ready.card(tid)["status"] == "paused_limit"


def test_t1852_exhausted_credits_pause_the_card_with_the_reason(ready: Rig) -> None:
    tid = ready.note()
    ready.run(tid, "implement")
    marks.mark_exhausted(ready.root, time.time() + 3600, "Credit balance is too low")
    card = ready.card(tid)
    assert card["status"] == "paused_limit"
    assert card["current"].startswith("free API credits exhausted")


def test_card_route_is_the_latest_turns(ready: Rig) -> None:
    tid = ready.note()
    assert ready.card(tid)["route"] is None
    ready.run(tid, "implement", extra={"route": "credits"})
    assert ready.card(tid)["route"] == "credits"
    validate("board", ready.backend.board())


def test_t1853_overage_alert_rides_on_the_board_until_it_ends(rig: Rig) -> None:
    rig.note()
    assert "alert" not in rig.backend.board()
    marks.raise_alert(rig.root, "Overage guard: stopped", time.time() + 60)
    board = rig.backend.board()
    validate("board", board)
    assert board["alert"]["kind"] == "overage"
    assert board["alert"]["text"] == "Overage guard: stopped"
    marks.raise_alert(rig.root, "old", time.time() - 1)
    assert "alert" not in rig.backend.board()


def test_t1856_a_manual_work_card_is_human_work_with_a_disabled_start(rig: Rig) -> None:
    tid = rig.note(title="MANUAL WORK REQUIRED: rotate Claude API key")
    card = rig.card(tid)
    assert (card["assignee"], card["status"], card["column"]) == ("human", "yours", "backlog")
    (start,) = [a for a in card["actions"] if a["id"] == "start"]
    assert start["enabled"] is False
    assert start["reason"].startswith("MANUAL WORK REQUIRED")
    other = rig.card(rig.note(title="Manual work required: not exact caps"))
    assert other["assignee"] == "claude"
