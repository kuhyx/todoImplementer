"""The API key status rides on /api/board, worded by the server, and the monitor is wired by build_backend."""

from datetime import date

from contract_lib import validate
from servicefakes import Rig
from todoimpl.apikey.keystatus import KeyStatus
from todoimpl.apikey.monitor import KeyMonitor


def _monitor(rig: Rig) -> KeyMonitor:
    monitor = rig.backend.key_monitor
    assert monitor is not None
    return monitor


def test_board_has_no_api_key_before_the_first_check(rig: Rig) -> None:
    rig.note()
    assert "api_key" not in rig.backend.board()


def test_board_carries_the_server_worded_status_and_stays_in_contract(rig: Rig) -> None:
    rig.note()
    monitor = _monitor(rig)
    monitor._check = lambda _today: KeyStatus("expired", date(2026, 11, 1), "expired on 2026-11-01")
    monitor._notify = lambda *_: True
    monitor.tick()
    board = rig.backend.board()
    validate("board", board)
    assert board["api_key"]["level"] == "error"
    assert "rotate_api_key.py" in board["api_key"]["text"]


def test_ok_status_is_level_ok(rig: Rig) -> None:
    rig.note()
    monitor = _monitor(rig)
    monitor._check = lambda _today: KeyStatus("ok", date(2026, 12, 1), "valid")
    monitor.tick()
    board = rig.backend.board()
    validate("board", board)
    assert board["api_key"]["level"] == "ok"


def test_a_created_task_refreshes_the_cache_at_once(rig: Rig) -> None:
    monitor = _monitor(rig)
    monitor._check = lambda _today: KeyStatus("missing", None, "no key")
    monitor._notify = lambda *_: True
    monitor.tick()
    rig.backend.cache.refresh()
    assert any(
        t["title"].startswith("MANUAL WORK REQUIRED: rotate Claude API key")
        for t in rig.backend.board()["tasks"]
    )
