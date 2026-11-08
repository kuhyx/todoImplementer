"""POST start carries the Auto-ship choice: `{}` keeps the stored one, `{auto_ship: bool}` sets it."""

from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, post

OPTION = {"id": "auto_ship", "label": "Auto-ship when checks pass", "enabled": True, "reason": None}


def _offer(live: Live, option: dict[str, Any]) -> None:
    start = next(a for a in live.backend.task_data["card"]["actions"] if a["id"] == "start")
    start["option"] = option


@pytest.mark.parametrize(
    ("body", "passed"), [({}, None), ({"auto_ship": True}, True), ({"auto_ship": False}, False)]
)
def test_start_passes_the_auto_ship_choice(live: Live, body: dict[str, Any], passed: bool | None) -> None:
    _offer(live, OPTION)
    validate("requests", body, "start")
    r = post(live, "start", body)
    assert r.status == 200, r.body
    assert live.backend.calls == [("start", live.backend.task_id, passed)]


@pytest.mark.parametrize("body", [{"auto_ship": "yes"}, {"auto_ship": True, "x": 1}, {"x": 1}])
def test_start_rejects_any_other_body(live: Live, body: dict[str, Any]) -> None:
    r = post(live, "start", body)
    assert r.status == 400
    assert r.json()["error"]["code"] == "bad_request"
    assert live.backend.calls == []


def test_auto_ship_needs_the_option_offered_and_enabled(live: Live) -> None:
    r = post(live, "start", {"auto_ship": True})
    assert r.status == 409
    assert r.json()["error"] == {"code": "disabled", "message": "Auto-ship is not offered here"}
    _offer(live, {**OPTION, "enabled": False, "reason": "the note has no done_check"})
    r = post(live, "start", {"auto_ship": True})
    assert r.json()["error"] == {"code": "disabled", "message": "the note has no done_check"}
    assert post(live, "start", {"auto_ship": False}).status == 200
    assert live.backend.calls == [("start", live.backend.task_id, False)]
